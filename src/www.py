#!/usr/bin/env python3
# www.py
# NotesHub presentation-layer state management tool: determines which pages need
# regeneration, backfills the manifest, and generates the sidebar menu.
#
#   status        Lists the status of every page (--json for Claude to consume,
#                 --stale-only lists only the ones that need work)
#
# One "main file" = one page. The number of md files matched by `main` in the
# conf is the number of pages; `refs` are just reference material used during
# translation.
#   plan <t>      Prints a page's main file, references, note, and output path
#                 (t = page id or section name)
#   commit <t>    Backfills the manifest after generation (recomputes all hashes)
#   accept-skill  Updates only skill_sha, without triggering regeneration
#   nav           Regenerates the www/index.html menu shell from www.conf
#
# Standard library only. The decision logic is deliberately zero-cost pure
# computation, so the LLM only spends effort on pages that truly need
# translation. See docs/www-plan.md for the design rationale.

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ─── Paths ─────────────────────────────────────────────────────────────────────

# WWW_ROOT can override the repo root, mainly for testing; defaults to the
# grandparent directory of this file
ROOT = Path(os.environ.get("WWW_ROOT", Path(__file__).resolve().parent.parent)).resolve()
CONF = ROOT / "src" / "www.conf"
WWW = ROOT / "www"
MANIFEST = WWW / "manifest.json"
SKILL_DIR = ROOT / ".claude" / "skills" / "notes-to-html"

# Things to ignore when computing skill_sha.
# This isn't just tidiness: the folder naturally contains macOS's .DS_Store
# and a make_chart.cpython-310.pyc left over from another machine — running
# the script once on a different machine produces a different pyc version,
# and without excluding these the whole site would spuriously turn STALE:skill.
SKILL_IGNORE_DIRS = {"__pycache__", ".git", ".mypy_cache", ".pytest_cache"}
SKILL_IGNORE_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
SKILL_IGNORE_SUFFIX = {".pyc", ".pyo", ".swp", ".swo", ".orig", ".rej"}

VALID_KEYS = {"title", "main", "refs", "group", "order", "note", "type", "href"}

# Parameter names that are easy to typo. Raise an error and point to the
# correct usage instead of silently ignoring it — these two names are
# intuitive, but their meaning doesn't match this tool's model, and just
# reporting "missing main" wouldn't reveal what's actually wrong.
REJECTED_KEYS = {
    "sources": "Sources must be split into main (the primary files to convert, "
    "one md = one standalone page) and refs (reference material used only "
    "during conversion, not turned into its own page)",
    "out": "The output path isn't specified in the conf — it's always "
    "pages/<section>/<md filename>.html. A section can produce multiple "
    "pages, and a single out string can't refer to all of them",
}

GLOB_CHARS = set("*?[")


class ConfError(Exception):
    pass


# ─── Hashing ─────────────────────────────────────────────────────────────────


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha_text(s):
    return sha_bytes(s.encode("utf-8"))


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def skill_sha():
    """Combined hash of the skill folder. Returns an empty string if the folder doesn't exist (not treated as an error)."""
    if not SKILL_DIR.is_dir():
        return ""
    parts = []
    for dirpath, dirnames, filenames in os.walk(SKILL_DIR):
        dirnames[:] = sorted(d for d in dirnames if d not in SKILL_IGNORE_DIRS)
        for name in sorted(filenames):
            if name in SKILL_IGNORE_NAMES:
                continue
            if Path(name).suffix in SKILL_IGNORE_SUFFIX:
                continue
            p = Path(dirpath) / name
            rel = p.relative_to(SKILL_DIR).as_posix()
            parts.append("%s\0%s" % (rel, sha_file(p)))
    return sha_text("\n".join(parts))


# ─── Conf parsing ──────────────────────────────────────────────────────────


class Section:
    def __init__(self, name, lineno):
        self.name = name
        self.lineno = lineno
        self.title = ""
        self.group = ""
        self.order = 50
        self.type = "page"
        self.href = ""
        self.note = ""
        self.main_patterns = []
        self.ref_patterns = []

    @property
    def is_page(self):
        return self.type == "page"


def heading_of(path):
    """Take the md's first H1 as the page title. Returns an empty string if none
    is found, and the caller falls back to the filename.

    Only scans the first 200 lines: a tech note's H1 is always near the top,
    and scanning the whole file across 1600 md files would waste I/O.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            prev = ""
            for i, raw in enumerate(f):
                if i > 200:
                    break
                line = raw.strip()
                m = re.match(r"^#\s+(.+?)\s*#*$", line)
                if m:
                    return m.group(1).strip()
                # setext style: the title is on the previous line, this line is a run of =
                if prev and re.match(r"^=+$", line):
                    return prev
                prev = line if line else ""
    except OSError:
        pass
    return ""


class Page:
    """One "main file" = one standalone page.

    This is the core constraint of the whole design: a page's heading
    structure is determined by its main md file, and refs are just
    supporting material used during translation. Merging multiple md files
    into one page would turn the heading structure into something the LLM
    makes up freely — it would look different on every regeneration and
    would no longer map back to the original notes.
    """

    def __init__(self, sec, main, refs, total):
        self.sec = sec
        self.main = main
        self.refs = [r for r in refs if r != main]
        self.stem = Path(main).stem
        self.id = "%s/%s" % (sec.name, self.stem)
        self.out = "pages/%s/%s.html" % (sec.name, self.stem)
        if total == 1:
            self.title = sec.title
        else:
            h = heading_of(ROOT / main)
            self.title = "%s · %s" % (sec.title, h or self.stem)

    @property
    def group(self):
        return self.sec.group

    @property
    def order(self):
        return self.sec.order

    @property
    def note(self):
        return self.sec.note

    @property
    def sources(self):
        return [self.main] + self.refs

    def spec_sha(self):
        """Hash of the title / note / main / refs patterns.

        refs deliberately uses the "raw pattern" rather than the expanded
        list: a glob matching one more reference file should report
        STALE:src (the source changed), not STALE:spec (the config
        changed). main, on the other hand, uses its expanded actual path,
        since it determines this page's identity.
        """
        blob = "\n".join(
            [
                "title=" + self.sec.title,
                "note=" + self.sec.note,
                "main=" + self.main,
                "refs=" + "\n".join(self.sec.ref_patterns),
            ]
        )
        return sha_text(blob)


def parse_conf(path=CONF):
    if not path.is_file():
        raise ConfError("Conf file not found: %s" % path)

    sections = []
    by_name = {}
    cur = None
    pending_key = None  # Supports line continuation: if a value isn't terminated, an indented next line is treated as a continuation

    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                pending_key = None
                continue

            m = re.match(r"^\[(.+)\]\s*$", line.strip())
            if m:
                name = m.group(1).strip()
                if name in by_name:
                    raise ConfError(
                        "Line %d: section [%s] is defined more than once (first defined at line %d)"
                        % (lineno, name, by_name[name].lineno)
                    )
                cur = Section(name, lineno)
                sections.append(cur)
                by_name[name] = cur
                pending_key = None
                continue

            m = re.match(r"^(\w+)\s*(\+?=)\s*(.*)$", line.strip())
            if m:
                key, op, val = m.group(1), m.group(2), m.group(3).strip()
                if cur is None:
                    raise ConfError("Line %d: %s appears before any [section]" % (lineno, key))
                if key in REJECTED_KEYS:
                    raise ConfError(
                        "Line %d: there is no such parameter %s. %s" % (lineno, key, REJECTED_KEYS[key])
                    )
                if key not in VALID_KEYS:
                    print("WARN: %s:%d unknown parameter: %s" % (path.name, lineno, key), file=sys.stderr)
                    pending_key = None
                    continue
                _assign(cur, key, val, op == "+=", lineno)
                pending_key = key
                continue

            # No = and not a section: if the previous line was a key that supports continuation, treat this as a continuation
            if pending_key and raw[:1] in (" ", "\t"):
                _assign(cur, pending_key, line.strip(), True, lineno)
                continue

            raise ConfError("Line %d: unable to parse: %s" % (lineno, line.strip()))

    for s in sections:
        _validate(s)
    return sections


def _assign(sec, key, val, append, lineno):
    if key in ("main", "refs"):
        items = [x.strip() for x in val.split(",") if x.strip()]
        bucket = "main_patterns" if key == "main" else "ref_patterns"
        if not append:
            setattr(sec, bucket, [])
        getattr(sec, bucket).extend(items)
    elif key == "note":
        # note continuation lines are joined with a space, without keeping newlines, so conf formatting doesn't affect the hash
        sec.note = (sec.note + " " + val).strip() if append and sec.note else val
    elif key == "order":
        try:
            sec.order = int(val)
        except ValueError:
            raise ConfError("Line %d: order must be an integer, got %r" % (lineno, val))
    else:
        setattr(sec, key, val)


def _check_paths(pats, sec, key):
    where = "[%s] (line %d)" % (sec.name, sec.lineno)
    for p in pats:
        if ".." in Path(p).parts or Path(p).is_absolute():
            raise ConfError("%s's %s must be a repo-relative path without ..: %s" % (where, key, p))


def _validate(sec):
    where = "[%s] (line %d)" % (sec.name, sec.lineno)
    if not sec.title:
        raise ConfError("%s is missing title" % where)
    if sec.type not in ("page", "link"):
        raise ConfError("%s's type must be page or link, got %r" % (where, sec.type))

    if sec.type == "link":
        if not sec.href:
            raise ConfError("%s type=link requires href" % where)
        if sec.main_patterns or sec.ref_patterns:
            raise ConfError("%s type=link should not have main or refs" % where)
        return

    if not sec.main_patterns:
        raise ConfError("%s is missing main (the primary files to convert)" % where)
    if sec.href:
        raise ConfError("%s type=page should not have href" % where)
    _check_paths(sec.main_patterns, sec, "main")
    _check_paths(sec.ref_patterns, sec, "refs")


# ─── Source expansion ──────────────────────────────────────────────────────────


def expand_patterns(pats, kind):
    """Expand a set of patterns. Returns (file list, problem list).

    There are only two kinds of problems: a literal path doesn't exist, or a
    glob matches nothing. Both mean the conf is wrong and generation can't
    proceed. A change in the number of glob matches isn't a problem — that's
    STALE:src.
    """
    found, problems = [], []
    for pat in pats:
        if GLOB_CHARS & set(pat):
            hits = sorted(p for p in ROOT.glob(pat) if p.is_file())
            if not hits:
                problems.append("%s glob matched nothing: %s" % (kind, pat))
            found.extend(hits)
        else:
            p = ROOT / pat
            if p.is_file():
                found.append(p)
            else:
                problems.append("%s file not found: %s" % (kind, pat))

    rels = sorted({p.resolve().relative_to(ROOT).as_posix() for p in found})
    return rels, problems


def pages_of(sec):
    """Expand a type=page section into a list of pages. Returns (pages, problems).

    The number of md files matched by main is the number of pages. refs
    don't generate pages of their own — they're just attached to each
    page's reference list.
    """
    mains, problems = expand_patterns(sec.main_patterns, "main")
    refs, ref_problems = expand_patterns(sec.ref_patterns, "refs")
    problems += ref_problems

    pages, seen = [], {}
    for m in mains:
        pg = Page(sec, m, refs, len(mains))
        if pg.id in seen:
            # Same-named md files in different directories collide into the
            # same page id and the same out path — the later one generated
            # would silently overwrite the former. Better to block it and
            # require a conf change.
            problems.append("Main file name collision (page id %s): %s and %s" % (pg.id, seen[pg.id], m))
            continue
        seen[pg.id] = m
        pages.append(pg)
    return pages, problems


def all_pages(sections):
    """All pages expanded from every type=page section, each with its own problems."""
    out = []
    for sec in sections:
        if not sec.is_page:
            continue
        pgs, problems = pages_of(sec)
        out.append((sec, pgs, problems))
    return out


# ─── Manifest ─────────────────────────────────────────────────────────────────


def load_manifest():
    if not MANIFEST.is_file():
        return {"version": 1, "pages": {}}
    with open(MANIFEST, encoding="utf-8") as f:
        m = json.load(f)
    m.setdefault("version", 1)
    m.setdefault("pages", {})
    return m


def save_manifest(m):
    WWW.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


# ─── Status evaluation ─────────────────────────────────────────────────────────────────


def _diff(kind, cur, old):
    """Compare the sha dict for one kind of source (main / refs) and return a human-readable description of the changes."""
    added = [s for s in cur if s not in old]
    removed = [s for s in old if s not in cur]
    changed = [s for s in cur if s in old and old[s] != sha_file(ROOT / s)]
    bits = []
    if changed:
        bits.append("%s %d file(s) content changed" % (kind, len(changed)))
    if added:
        bits.append("%s %d file(s) added" % (kind, len(added)))
    if removed:
        bits.append("%s %d file(s) removed" % (kind, len(removed)))
    return bits, {"changed": changed, "added": added, "removed": removed}


def evaluate(sections, manifest, cur_skill):
    """Returns (list of per-page status dicts, list of orphans).

    A type=page section expands into N rows (N = the number of md files matched by main).
    """
    rows = []
    declared_out = set()
    known_ids = set()

    for sec in sections:
        if not sec.is_page:
            rows.append(
                {
                    "page": sec.name,
                    "section": sec.name,
                    "title": sec.title,
                    "group": sec.group,
                    "order": sec.order,
                    "type": "link",
                    "status": "LINK",
                    "detail": sec.href,
                    "href": sec.href,
                }
            )
            continue

        pgs, problems = pages_of(sec)
        for pg in pgs:
            declared_out.add(pg.out)
            known_ids.add(pg.id)

        if problems:
            rows.append(
                {
                    "page": sec.name,
                    "section": sec.name,
                    "title": sec.title,
                    "group": sec.group,
                    "order": sec.order,
                    "type": "page",
                    "status": "MISSING:src",
                    "detail": "; ".join(problems),
                }
            )
            continue

        for pg in pgs:
            out_path = WWW / pg.out
            entry = manifest["pages"].get(pg.id)

            row = {
                "page": pg.id,
                "section": sec.name,
                "title": pg.title,
                "group": sec.group,
                "order": sec.order,
                "type": "page",
                "out": pg.out,
                "main": pg.main,
                "refs": pg.refs,
                "note": pg.note,
            }

            if entry is None:
                row["status"] = "NEW"
                row["detail"] = "no manifest record"
            elif not out_path.is_file():
                row["status"] = "NEW"
                row["detail"] = "output file does not exist"
            elif entry.get("out_sha") != sha_file(out_path):
                row["status"] = "DIRTY"
                row["detail"] = "output file was manually modified after generation"
            elif entry.get("skill_sha") != cur_skill:
                row["status"] = "STALE:skill"
                row["detail"] = "skill contents have changed"
            elif entry.get("spec_sha") != pg.spec_sha():
                row["status"] = "STALE:spec"
                row["detail"] = "conf's title / note / main / refs settings have changed"
            else:
                mb, md = _diff("main", {pg.main: None}, entry.get("main", {}))
                rb, rd = _diff("refs", {r: None for r in pg.refs}, entry.get("refs", {}))
                if mb or rb:
                    row["status"] = "STALE:src"
                    row["detail"] = ", ".join(mb + rb)
                    row["main_diff"] = md
                    row["refs_diff"] = rd
                else:
                    row["status"] = "OK"
                    row["detail"] = "1 main file + %d ref(s), %s" % (
                        len(pg.refs),
                        entry.get("generated_at", "?"),
                    )
            rows.append(row)

    orphans = []
    pages_dir = WWW / "pages"
    if pages_dir.is_dir():
        for p in sorted(pages_dir.rglob("*.html")):
            rel = p.relative_to(WWW).as_posix()
            if rel not in declared_out:
                orphans.append({"kind": "file", "path": rel})
    known = known_ids
    for name in sorted(manifest["pages"]):
        if name not in known:
            orphans.append({"kind": "manifest", "path": name})
    return rows, orphans


STALE_STATES = {"NEW", "STALE:src", "STALE:spec", "STALE:skill"}


# ─── Subcommands ───────────────────────────────────────────────────────────────────


def cmd_status(args):
    sections = parse_conf()
    manifest = load_manifest()
    cur_skill = skill_sha()
    rows, orphans = evaluate(sections, manifest, cur_skill)

    if args.stale_only:
        rows = [r for r in rows if r["status"] in STALE_STATES]

    if args.json:
        print(
            json.dumps(
                {
                    "root": str(ROOT),
                    "skill_sha": cur_skill,
                    "skill_dir_exists": SKILL_DIR.is_dir(),
                    "pages": rows,
                    "orphans": orphans,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if not cur_skill:
        print("WARN: skill folder not found %s, skill_sha computed as empty" % SKILL_DIR, file=sys.stderr)

    if not rows and not orphans:
        print("www.conf has no sections.")
        return 0

    cols = [
        ("GROUP", lambda r: r["group"] or "—"),
        ("PAGE", lambda r: r["page"]),
        ("STATUS", lambda r: r["status"]),
        ("DETAIL", lambda r: r.get("detail", "")),
    ]
    widths = [
        max(len(head), *(_w(fn(r)) for r in rows)) if rows else len(head)
        for head, fn in cols
    ]
    print("  ".join(_pad(h, w) for (h, _), w in zip(cols, widths)))
    print("  ".join("─" * w for w in widths))
    for r in rows:
        print("  ".join(_pad(fn(r), w) for (_, fn), w in zip(cols, widths)).rstrip())

    if orphans:
        print()
        for o in orphans:
            if o["kind"] == "file":
                print("ORPHAN  www/%s (not defined in conf)" % o["path"])
            else:
                print("ORPHAN  leftover manifest record: %s (removed from conf)" % o["path"])

    todo = [r for r in rows if r["status"] in STALE_STATES]
    problems = [r for r in rows if r["status"] in ("DIRTY", "MISSING:src")]
    print()
    print("%d page(s) need generation; %d page(s) need manual attention." % (len(todo), len(problems)))
    return 0


def _w(s):
    """CJK full-width characters count as two columns, so the table aligns."""
    import unicodedata

    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in str(s))


def _pad(s, w):
    return str(s) + " " * max(0, w - _w(s))


def resolve(sections, target):
    """target can be a page id (<section>/<filename>) or a section name.

    When given a section name, it expands to all pages under it — a
    section may have several main files. Returns (pages, problems); raises
    ConfError if not found.
    """
    by_name = {s.name: s for s in sections}
    sec = by_name.get(target)
    if sec is not None:
        if not sec.is_page:
            raise ConfError("[%s] is type=link, no generation needed." % target)
        return pages_of(sec)

    for s in sections:
        if not s.is_page:
            continue
        pgs, problems = pages_of(s)
        for pg in pgs:
            if pg.id == target:
                return [pg], problems

    ids = []
    for s in sections:
        if s.is_page:
            ids.extend(p.id for p in pages_of(s)[0])
        else:
            ids.append(s.name)
    raise ConfError("%s not found. Available pages:\n  %s" % (target, "\n  ".join(sorted(ids))))


def _page_plan(pg, problems):
    return {
        "page": pg.id,
        "section": pg.sec.name,
        "title": pg.title,
        "group": pg.group,
        "out": "www/" + pg.out,
        "note": pg.note,
        "main": pg.main,
        "refs": pg.refs,
        "problems": problems,
    }


def cmd_plan(args):
    sections = parse_conf()
    pages, problems = resolve(sections, args.target)

    if args.json:
        print(
            json.dumps(
                {"pages": [_page_plan(pg, problems) for pg in pages]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2 if problems else 0

    for i, pg in enumerate(pages):
        if i:
            print()
        print("page    : %s" % pg.id)
        print("title   : %s" % pg.title)
        print("group   : %s" % (pg.group or "—"))
        print("out     : www/%s" % pg.out)
        print("note    : %s" % (pg.note or "—"))
        print("main    : %s" % pg.main)
        print("          ↑ This page's headings follow this file — do not change their order or hierarchy")
        print("refs    : %d file(s) (reference only during translation, must not override main's structure)" % len(pg.refs))
        for r in pg.refs:
            print("  %s" % r)
    if not pages:
        print("This section currently has no main files.")
    if problems:
        print()
        for p in problems:
            print("Problem: %s" % p, file=sys.stderr)
        return 2
    return 0


def cmd_commit(args):
    sections = parse_conf()
    manifest = load_manifest()
    cur_skill = skill_sha()
    done, skipped = [], []

    if args.all:
        targets = []
        for sec, pgs, problems in all_pages(sections):
            for pg in pgs:
                targets.append((pg, problems))
    else:
        pages, problems = resolve(sections, args.target)
        targets = [(pg, problems) for pg in pages]
        if not targets:
            print("No matching page: %s" % args.target, file=sys.stderr)
            return 2

    for pg, problems in targets:
        if problems:
            msg = "; ".join(problems)
            if not args.all:
                print("Source has problems, not backfilled: %s" % msg, file=sys.stderr)
                return 2
            skipped.append((pg.id, msg))
            continue

        out_path = WWW / pg.out
        if not out_path.is_file():
            msg = "Output file does not exist: www/%s" % pg.out
            if not args.all:
                print(msg, file=sys.stderr)
                return 2
            skipped.append((pg.id, msg))
            continue

        manifest["pages"][pg.id] = {
            "out": pg.out,
            "out_sha": sha_file(out_path),
            "spec_sha": pg.spec_sha(),
            "skill_sha": cur_skill,
            "main": {pg.main: sha_file(ROOT / pg.main)},
            "refs": {r: sha_file(ROOT / r) for r in pg.refs},
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        done.append(pg.id)

    save_manifest(manifest)
    for name in done:
        print(
            "Backfilled manifest: %s (1 main file + %d ref(s))"
            % (name, len(manifest["pages"][name]["refs"]))
        )
    for name, msg in skipped:
        print("Skipped %s: %s" % (name, msg), file=sys.stderr)
    if not done:
        print("No pages were backfilled.", file=sys.stderr)
    return 0


def cmd_accept_skill(args):
    manifest = load_manifest()
    cur_skill = skill_sha()
    n = 0
    for name, entry in manifest["pages"].items():
        if entry.get("skill_sha") != cur_skill:
            entry["skill_sha"] = cur_skill
            n += 1
    save_manifest(manifest)
    print("Updated %d skill_sha record(s) to %s (regeneration not triggered)" % (n, cur_skill[:12] or "(empty)"))
    return 0


# ─── Menu shell ─────────────────────────────────────────────────────────────


def esc(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_nav(sections):
    """Group by `group`. The order of groups is determined by the minimum
    order within each group, ties broken by order of appearance in the conf.

    A type=page section expands into N menu items (N = the number of files
    matched by main), adjacent to each other and ordered by the main file's path.
    """
    groups, order_of, seq = {}, {}, {}
    for i, sec in enumerate(sections):
        g = sec.group or ""
        if g not in groups:
            groups[g] = []
            order_of[g] = sec.order
            seq[g] = i
        groups[g].append(sec)
        order_of[g] = min(order_of[g], sec.order)

    out = []
    n_pages = n_missing = 0
    ordered = sorted(groups, key=lambda g: (order_of[g], seq[g]))
    for gi, g in enumerate(ordered):
        secs = sorted(groups[g], key=lambda s: (s.order, s.name))
        lis = []
        for sec in secs:
            if sec.is_page:
                entries = [(p.id, p.out, p.title, True) for p in pages_of(sec)[0]]
            else:
                entries = [(sec.name, sec.href, sec.title, False)]
            for pid, href, title, is_page in entries:
                n_pages += 1
                if is_page:
                    missing = not (WWW / href).is_file()
                    badge = ' <span class="badge">Not generated</span>' if missing else ""
                else:
                    missing = not (WWW / href).resolve().is_file()
                    badge = (
                        ' <span class="badge">Broken link</span>'
                        if missing
                        else ' <span class="ext">↗</span>'
                    )
                if missing:
                    n_missing += 1
                lis.append(
                    '<li><a href="#/%s" data-sec="%s" data-href="%s"%s>%s%s</a></li>'
                    % (
                        esc(pid),
                        esc(pid),
                        esc(href),
                        ' data-missing="1"' if missing else "",
                        esc(title),
                        badge,
                    )
                )
        # Use the index as an id prefix: a pure-CJK group name would sanitize
        # to the same string of underscores, so two CJK groups would collide
        # on id, and toggling one would control another's list.
        gid = "g%d-%s" % (gi, re.sub(r"[^A-Za-z0-9_-]+", "-", g or "top").strip("-").lower())
        label = esc(g) if g else "Ungrouped"
        out.append(
            '<section class="grp" data-grp>\n'
            '<button class="grp-h" aria-expanded="true" aria-controls="%s">'
            '<span class="caret" aria-hidden="true">▾</span>%s'
            '<span class="count">%d</span></button>\n'
            '<ul id="%s">\n%s\n</ul>\n</section>'
            % (gid, label, len(lis), gid, "\n".join(lis))
        )
    return "\n".join(out), n_pages, n_missing


def cmd_nav(args):
    sections = parse_conf()
    nav_html, n_pages, n_missing = build_nav(sections)
    html = SHELL.replace("<<<NAV>>>", nav_html).replace("<<<COUNT>>>", str(n_pages))
    WWW.mkdir(parents=True, exist_ok=True)
    target = WWW / "index.html"
    old = target.read_text(encoding="utf-8") if target.is_file() else None
    target.write_text(html, encoding="utf-8")
    verb = "No change to" if old == html else "Updated"
    print("%s www/index.html (%d item(s))" % (verb, n_pages))
    if n_missing:
        print("%d of these items' files do not yet exist; the menu will mark them as not generated." % n_missing)
    return 0


# Menu shell. Deliberately has no generation timestamp, so re-running nav
# doesn't produce meaningless git diffs.
# Theme is controlled centrally by this shell; protocol is in
# .claude/skills/notes-to-html/assets/page-template.html:
#   page finishes loading, sends {type:'nt-ready'} → shell pushes back
#   {type:'nt-theme', theme:'dark'|'light'}
SHELL = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NotesHub Technical Notes</title>
<!-- Generated by python3 src/www.py nav, do not edit manually -->
<style>
:root {
  --sb: 264px;
  --bg: #0d1117; --bg-raised: #151b23; --bg-sunken: #090c10;
  --border: #262d36; --border-strong: #3a434f;
  --text: #e4e8ee; --text-muted: #9aa5b4; --text-faint: #6b7684;
  --accent: #58a6ff; --accent-soft: #1c3050;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC",
          "PingFang TC", "Microsoft JhengHei", sans-serif;
}
[data-theme="light"] {
  --bg: #ffffff; --bg-raised: #f6f8fa; --bg-sunken: #eef1f5;
  --border: #d5dae1; --border-strong: #aeb7c2;
  --text: #1c2128; --text-muted: #56606d; --text-faint: #79828f;
  --accent: #0550ae; --accent-soft: #dbeafe;
}
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body {
  display: grid; grid-template-columns: var(--sb) 1fr;
  background: var(--bg); color: var(--text);
  font: 15px/1.6 var(--font); -webkit-font-smoothing: antialiased;
}
body.sb-closed { --sb: 0px; }

/* ── sidebar ─────────────────────────────────────────────── */
#sb {
  grid-column: 1; min-width: 0; overflow: hidden auto;
  background: var(--bg-sunken); border-right: 1px solid var(--border);
  display: flex; flex-direction: column;
}
body.sb-closed #sb { border-right: 0; }
.brand {
  padding: 16px 18px 12px; border-bottom: 1px solid var(--border);
  position: sticky; top: 0; background: var(--bg-sunken); z-index: 2;
}
.brand b { display: block; font-size: 15px; letter-spacing: -.01em; }
.brand span { display: block; font-size: 11.5px; color: var(--text-faint); margin-top: 2px; }
.filter { padding: 12px 14px 8px; }
.filter input {
  width: 100%; padding: 7px 10px; font: inherit; font-size: 13px;
  color: var(--text); background: var(--bg-raised);
  border: 1px solid var(--border); border-radius: 7px;
}
.filter input:focus { outline: none; border-color: var(--accent); }
nav { padding: 0 8px 24px; }
.grp { margin-bottom: 2px; }
.grp-h {
  display: flex; align-items: center; gap: 6px; width: 100%;
  padding: 7px 8px; font: inherit; font-size: 11.5px; font-weight: 700;
  letter-spacing: .04em; text-transform: uppercase;
  color: var(--text-faint); background: none; border: 0;
  cursor: pointer; text-align: left; border-radius: 6px;
}
.grp-h:hover { color: var(--text-muted); background: var(--bg-raised); }
.caret { font-size: 9px; transition: transform .15s; }
.grp-h[aria-expanded="false"] .caret { transform: rotate(-90deg); }
.count { margin-left: auto; font-weight: 400; font-size: 11px; opacity: .7; }
.grp-h[aria-expanded="false"] + ul { display: none; }
nav ul { list-style: none; margin: 0 0 6px; padding: 0; }
nav a {
  display: block; padding: 7px 10px 7px 22px; border-radius: 7px;
  color: var(--text-muted); text-decoration: none; font-size: 13.5px;
  overflow-wrap: anywhere;
}
nav a:hover { background: var(--bg-raised); color: var(--text); }
nav a[aria-current="page"] {
  background: var(--accent-soft); color: var(--text); font-weight: 600;
  box-shadow: inset 2px 0 0 var(--accent);
}
nav a[data-missing] { color: var(--text-faint); }
.badge, .ext { font-size: 10.5px; color: var(--text-faint); }
.badge {
  padding: 1px 5px; margin-left: 4px; border-radius: 4px;
  border: 1px solid var(--border-strong); white-space: nowrap;
}

/* ── main ────────────────────────────────────────────────── */
#main { grid-column: 2; min-width: 0; display: flex; flex-direction: column; }
.bar {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; border-bottom: 1px solid var(--border);
  background: var(--bg-raised); flex: none;
}
.bar button, .bar a {
  font: inherit; font-size: 12.5px; padding: 5px 9px; border-radius: 7px;
  color: var(--text-muted); background: var(--bg);
  border: 1px solid var(--border); cursor: pointer; text-decoration: none;
  white-space: nowrap;
}
.bar button:hover, .bar a:hover { color: var(--text); border-color: var(--border-strong); }
#crumb {
  flex: 1; min-width: 0; font-size: 13px; color: var(--text-muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
#crumb b { color: var(--text); font-weight: 600; }
#view { flex: 1; width: 100%; border: 0; background: var(--bg); }
#hint {
  flex: 1; display: none; place-content: center; text-align: center;
  padding: 40px 24px; color: var(--text-muted);
}
body.empty #view { display: none; }
body.empty #hint { display: grid; }
#hint h1 { font-size: 1.3rem; color: var(--text); margin: 0 0 8px; }
#hint p { margin: 0 auto; max-width: 46ch; font-size: 14px; }
#hint code {
  font-size: .9em; padding: 1px 5px; border-radius: 4px;
  background: var(--bg-raised); border: 1px solid var(--border);
}
#scrim { display: none; }

/* ── Narrow screens: sidebar collapses into an overlay, giving the full
   width to the iframe ─────────────────────────────────────────
   Page chart sizes are validated against a "worst-case iframe width of
   320px" (see references/rwd.md) — the sidebar must not keep occupying
   space here, or the iframe would end up narrower than that assumption
   and chart text would fall below the readable minimum. */
@media (max-width: 860px) {
  body { grid-template-columns: 1fr; }
  #sb {
    position: fixed; inset: 0 auto 0 0; width: min(84vw, 300px); z-index: 30;
    transform: translateX(-100%); transition: transform .18s ease;
    border-right: 1px solid var(--border);
  }
  body.sb-open #sb { transform: none; }
  #main { grid-column: 1; }
  body.sb-open #scrim {
    display: block; position: fixed; inset: 0; z-index: 20;
    background: rgba(0,0,0,.5);
  }
  /* At this breakpoint the sidebar is already an overlay, --sb no longer affects layout, and the collapse button becomes inert */
  #openNew, #sbBtn { display: none; }
}
@media (min-width: 861px) { #menuBtn { display: none; } }
@media (prefers-reduced-motion: reduce) { #sb { transition: none; } }
</style>
</head>
<body class="empty">

<aside id="sb">
  <div class="brand">
    <b>NotesHub</b>
    <span><<<COUNT>>> technical notes</span>
  </div>
  <div class="filter">
    <input id="q" type="search" placeholder="Filter titles…" aria-label="Filter titles">
  </div>
  <nav id="nav">
<<<NAV>>>
  </nav>
</aside>

<div id="scrim"></div>

<div id="main">
  <div class="bar">
    <button id="menuBtn" type="button" aria-label="Toggle menu">☰</button>
    <button id="sbBtn" type="button" title="Collapse the menu for more content width">⇤</button>
    <span id="crumb">Select a note on the left</span>
    <a id="openNew" href="#" target="_blank" rel="noopener">↗ Open in new tab</a>
    <button id="themeBtn" type="button">☾ Dark</button>
  </div>
  <iframe id="view" title="Note content"></iframe>
  <div id="hint">
    <div>
      <h1>NotesHub Technical Notes</h1>
      <p>Pick a note from the menu on the left to get started. Pages are defined by
      <code>src/www.conf</code> and generated by the
      <code>notes-to-html</code> Skill; run
      <code>python3 src/www.py status</code> to see which ones need updating.</p>
    </div>
  </div>
</div>

<script>
(function () {
  'use strict';
  var root = document.documentElement, body = document.body;
  var view = document.getElementById('view');
  var crumb = document.getElementById('crumb');
  var openNew = document.getElementById('openNew');
  var links = Array.prototype.slice.call(document.querySelectorAll('#nav a[data-sec]'));

  /* ---- Theme: the shell is the sole controller -----------------
     The page inside the iframe hides its own toggle button and waits
     for this shell to postMessage.
     Protocol: page sends {type:'nt-ready'} → this replies {type:'nt-theme', theme:…}
  --------------------------------------------------------------- */
  var theme = null;
  try { theme = localStorage.getItem('nt-theme'); } catch (e) {}
  if (theme !== 'dark' && theme !== 'light') {
    theme = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }
  function pushTheme() {
    root.setAttribute('data-theme', theme);
    document.getElementById('themeBtn').textContent =
      theme === 'light' ? '☀ Light' : '☾ Dark';
    if (view.contentWindow) {
      try { view.contentWindow.postMessage({ type: 'nt-theme', theme: theme }, '*'); }
      catch (e) {}
    }
  }
  pushTheme();
  document.getElementById('themeBtn').addEventListener('click', function () {
    theme = theme === 'light' ? 'dark' : 'light';
    try { localStorage.setItem('nt-theme', theme); } catch (e) {}
    pushTheme();
  });
  window.addEventListener('message', function (e) {
    if (e.data && e.data.type === 'nt-ready') pushTheme();
  });
  view.addEventListener('load', pushTheme);

  /* ---- Hash routing: #/<section> ------------------------------ */
  function route() {
    var sec = decodeURIComponent((location.hash || '').replace(/^#\/?/, ''));
    var hit = null;
    for (var i = 0; i < links.length; i++) {
      var on = links[i].getAttribute('data-sec') === sec;
      if (on) hit = links[i];
      links[i].removeAttribute('aria-current');
    }
    if (!hit) {
      body.classList.add('empty');
      view.removeAttribute('src');
      crumb.textContent = sec ? 'Not found: "' + sec + '"' : 'Select a note on the left';
      openNew.removeAttribute('href');
      document.title = 'NotesHub Technical Notes';
      return;
    }
    hit.setAttribute('aria-current', 'page');
    var href = hit.getAttribute('data-href');
    var title = hit.textContent.replace(/\s*(Not generated|Broken link|↗)\s*$/, '').trim();
    document.title = title + ' · NotesHub';
    crumb.innerHTML = '';
    crumb.appendChild(document.createElement('b')).textContent = title;

    if (hit.hasAttribute('data-missing')) {
      body.classList.add('empty');
      view.removeAttribute('src');
      crumb.appendChild(document.createTextNode('  File does not exist, not yet generated'));
      openNew.removeAttribute('href');
    } else {
      body.classList.remove('empty');
      if (view.getAttribute('src') !== href) view.setAttribute('src', href);
      openNew.setAttribute('href', href);
    }
    /* Collapse the overlay after tapping on mobile */
    if (window.matchMedia('(max-width: 860px)').matches) body.classList.remove('sb-open');
    var li = hit.parentNode;
    if (li.scrollIntoView) li.scrollIntoView({ block: 'nearest' });
  }
  window.addEventListener('hashchange', route);

  /* ---- Group collapse ------------------------------------------ */
  Array.prototype.forEach.call(document.querySelectorAll('.grp-h'), function (h) {
    h.addEventListener('click', function () {
      h.setAttribute('aria-expanded', h.getAttribute('aria-expanded') === 'false');
    });
  });

  /* ---- Title filter --------------------------------------------- */
  document.getElementById('q').addEventListener('input', function (e) {
    var q = e.target.value.trim().toLowerCase();
    links.forEach(function (a) {
      var hit = !q || a.textContent.toLowerCase().indexOf(q) >= 0;
      a.parentNode.style.display = hit ? '' : 'none';
    });
    Array.prototype.forEach.call(document.querySelectorAll('[data-grp]'), function (g) {
      var any = Array.prototype.some.call(g.querySelectorAll('li'), function (li) {
        return li.style.display !== 'none';
      });
      g.style.display = any ? '' : 'none';
      if (q) g.querySelector('.grp-h').setAttribute('aria-expanded', 'true');
    });
  });

  /* ---- Menu toggle ------------------------------------------------ */
  document.getElementById('menuBtn').addEventListener('click', function () {
    body.classList.toggle('sb-open');
  });
  document.getElementById('scrim').addEventListener('click', function () {
    body.classList.remove('sb-open');
  });
  document.getElementById('sbBtn').addEventListener('click', function () {
    body.classList.toggle('sb-closed');
    this.textContent = body.classList.contains('sb-closed') ? '⇥' : '⇤';
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') body.classList.remove('sb-open');
    if (e.key === '/' && e.target === document.body) {
      e.preventDefault();
      document.getElementById('q').focus();
    }
  });

  route();
})();
</script>
</body>
</html>
"""


# ─── Entry point ─────────────────────────────────────────────────────────────


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="www.py", description="NotesHub presentation layer: status detection, manifest backfill, menu generation"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="List the status of every page")
    p.add_argument("--json", action="store_true", help="Output JSON")
    p.add_argument("--stale-only", action="store_true", help="List only pages that need generation")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("plan", help="Print a page's main file, references, and note")
    p.add_argument("target", help="Page id (<section>/<filename>) or section name (= all pages under that section)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("commit", help="Backfill the manifest after generation")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("target", nargs="?", help="Page id or section name")
    g.add_argument("--all", action="store_true", help="Backfill all pages whose output file already exists")
    p.set_defaults(fn=cmd_commit)

    p = sub.add_parser("accept-skill", help="Update only skill_sha, without triggering regeneration")
    p.set_defaults(fn=cmd_accept_skill)

    p = sub.add_parser("nav", help="Regenerate www/index.html")
    p.set_defaults(fn=cmd_nav)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except ConfError as e:
        print("Conf error: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
