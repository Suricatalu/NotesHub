# www Presentation Layer — Design Notes

This document records the design trade-offs and rationale for the presentation layer. For operational steps, see [README.md](../README.md); for layout/style conventions, see [`.claude/skills/notes-to-html/SKILL.md`](../.claude/skills/notes-to-html/SKILL.md).

## 1. Problem to Solve

The synced markdown files are development notes — whatever domain you work in — and there are typically thousands of them. Plain text is unfriendly to "technical understanding" — it lacks architecture diagrams, flowcharts, and sequence diagrams, forcing readers to assemble the mental model themselves.

Hence a **presentation layer**: selected markdown files are translated — via Claude Code plus a front-end presentation Skill — into HTML that carries its own architecture/flow diagrams, centralized under `www/`, with a single entry page featuring a left-hand navigation menu for unified browsing.

The rsync sync layer under `src/` is completely independent of this layer. The relationship between the two layers:

```
External folder ──rsync──▶ mirror folders (per sources.conf) ──Claude+Skill──▶ www/pages/**/*.html
   (src/sources.*.conf)      (raw md files)          (src/www.conf)        ▲
                                                                        │
                                                            www/index.html (left-side menu shell)
```

Key property: **the presentation layer operates entirely within the repo**. Inputs are repo-relative-path markdown files, outputs are repo-relative-path HTML files, so neither `www.conf` nor the manifest **need per-machine profiles** — every machine shares the same copy, and results generated on one machine never need to be regenerated on another.

## 2. Decisions Already Made

| Item | Decision |
|------|------|
| Whether generated html should be committed to git | **Yes.** See "Why HTML is also under version control" below for the rationale |
| Page granularity | Determined by `main` in `src/www.conf`: **one main file = one html page, always 1:1**. `refs` are reference material used during translation and do not become separate pages. A `[section]` can have multiple `main` entries, producing multiple pages |
| Existing hand-written html | Hand-written pages scattered under `<mirror>/*/www/index.html` **stay exactly where they are**, and are only hooked into the menu via `type = link` |
| Diagram technology | Governed by the Skill; this layer only defines the Skill's location and contract |
| Tooling language | Presentation-layer tooling uses **python3 (standard library only)**; the sync layer stays in bash |

### Why HTML Is Also Under Version Control

The convention for build artifacts is to gitignore them, since they can be regenerated anytime. Here we do the opposite, because this artifact **costs money** to produce:

- Translating a single page is not cheap. Without version control, every machine would have to burn its own tokens regenerating the same page.
- `manifest.json` is committed alongside the pages so that state can actually be shared — a page generated on machine A shows up as `OK` (not `NEW`) when machine B runs `status`.
- The web server machine therefore needs nothing installed; a `git pull` gives it the complete site, with no need for python3 or Claude Code.

The cost is a larger repo and noisy HTML diffs. This is acceptable because the number of pages is manually curated and won't spiral out of control.

### Why One `main` Maps to Exactly One Page

Merging N markdown files under one topic into a single page creates an invisible failure mode:
**the page's heading structure becomes something the LLM is free to reassemble every time**. Regenerating the same page twice yields a different table of contents; a reader looking at some part of the page has no way to trace it back to a specific part of the original notes. This directly violates the core premise of the entire presentation layer —
"the reader assumes every sentence comes from those notes."

So the structure is dictated by the markdown itself: **the page's heading order and hierarchy are inherited from `main`, and the Skill must not add, remove, or reorder headings** —
the Skill's job is purely visual translation on top of the existing skeleton. `refs` are **corroborating evidence, not a source of content**:
they're for looking up terminology, filling in things `main` mentions but doesn't elaborate on, and getting values needed for diagrams. Their content may only enrich what already sits under an existing heading,
never justify adding a new one. Claude may still look things up online, but is bound by the same rule, and must clearly note in the text that such content did not come from the repo's notes.

A rule that's only written in a document but never checked is effectively not written, so there's a real guardrail: `validate_page.py`'s `[O]` check
verifies that "the sources block must contain exactly one `<li data-role="main">`." Attempting to merge pages will either result in no main file being marked,
or in two being marked — either way, it gets blocked.

### Why the Presentation-Layer Tooling Doesn't Use Bash

It needs to do three things bash is painful at: recursive glob expansion, sha256, and reading/writing JSON. There are also two real cross-platform pitfalls — macOS has no `sha256sum` (it's `shasum -a 256` instead), and macOS doesn't ship `jq` by default. python3 is available on both, its standard library covers everything, and it solves all of this in one go.

## 3. File Structure

```
NotesHub/
├── src/
│   ├── sync-notes.sh              # Sync layer, unrelated to the presentation layer
│   ├── sources.*.conf             # Sync layer, per-profile
│   ├── www.conf                   # Page definitions (single copy, no profiles, version-controlled)
│   └── www.py                     # Status check / manifest backfill / menu generation
├── www/                           # Presentation-layer output (version-controlled)
│   ├── index.html                 # Menu shell generated by www.py nav
│   ├── manifest.json              # Hash state backfilled by www.py commit
│   └── pages/
│       └── <section>/<md filename>.html  # Pages generated by Claude per the Skill, one main file = one page
├── .claude/
│   └── skills/
│       └── notes-to-html/         # Front-end presentation Skill
│           ├── SKILL.md           # Required: frontmatter + body instructions
│           ├── references/        # Optional: diagram, RWD, component, math conventions
│           ├── assets/            # Optional: page-template.html, glossary.json
│           └── scripts/           # Optional: validate_page.py, make_chart.py
└── docs/
    └── www-plan.md                # This document
```

### Why .gitignore Specifically Allows .claude/skills/

The Skill dictates the layout of every page; if it's not version-controlled, another machine won't see it and the generated style will become inconsistent. But everything else under `.claude/` is local machine configuration and shouldn't be version-controlled. Hence it's written to allow only `skills`:

```gitignore
# Claude Code (only skills are version-controlled; other local config is not)
.claude/*
!.claude/skills/
```

## 4. `src/www.conf` Specification

Follows the project's existing INI style so the two conf files read consistently.

### 4.1 Generated Pages (`type = page`, default)

**One main file = one page.** However many markdown files `main` matches, this section produces that many independent HTML pages.

```ini
[auth-design]
title    = Authentication design
group    = Architecture
order    = 10
main     = notes/auth/overview.md
main    += notes/auth/token-refresh.md
refs     = notes/auth/*.md
refs    += notes/storage/sessions.md
note     = Explain the concept first, then the provisioning flow; no need to expand every command line by line
```

Produces two pages:

```
www/pages/auth-design/overview.html
www/pages/auth-design/token-refresh.html
```

| Field | Required | Description |
|------|:----:|------|
| `title` | ✔ | Name shown in the menu. With a single `main`, this is the page title; with multiple, each page shows "`title` · that markdown file's first H1" |
| `main` | ✔ | The main file(s) to translate, repo-relative paths, glob supported (`*`, `**`). Use `main +=` to accumulate across multiple lines |
| `refs` | | Reference material, same syntax as `main`. Used only for cross-checking during translation, not turned into separate pages |
| `group` | | Menu group name. If omitted, the page is placed at the top level of the menu |
| `order` | | Sort order within the group, lower numbers first. Default `50`. Multiple pages from the same section stay adjacent |
| `note` | | Extra instructions for the Skill. **Included in the hash computation** — changing `note` makes every page in that section stale |
| `type` | | `page` (default) or `link` |

**The page id and output path are derived, not specified in the conf:**

```
page id       = <section>/<md filename (without .md)>
output path   = www/pages/<section>/<md filename>.html
```

The conf has no field to specify the output path directly, because one section can produce multiple pages and a single string can't refer to all of them. The cost is one extra directory level of depth per page — the page's relative path back to the repo root is `../../../`.

If `main` matches two markdown files with the same name (in different directories), the page id and output path collide, and whichever is generated later silently overwrites the earlier one. `www.py` blocks this by reporting the entire section as `MISSING:src`, requiring the conf to be fixed.

### 4.2 External Links (`type = link`)

Used to hook existing HTML that "stays where it is" into the menu, without participating in generation or hash checking:

```ini
[auth-legacy]
title = Auth notes (hand-written version)
group = Architecture
order = 90
type  = link
href  = ../notes/auth/www/index.html
```

`type = link` should not have `main` or `refs`.

### 4.3 Differences from the Existing Parser

`sync-notes.sh`'s parser follows a "later overwrites earlier" semantics. Here we add `+=` accumulation semantics, so `www.py` implements its own parser rather than sharing one.

## 5. The Mechanism for Avoiding Redundant Translation

This is the core of the entire design — **the decision is made entirely by zero-cost python3; only pages that genuinely need translation are handed to the LLM**.

### 5.1 Why Content Hash Instead of mtime

`rsync -a` preserves the source's mtime, but `git clone` / `git checkout` set the working-directory file's mtime to the current time. So the same content will almost certainly have a different mtime on different machines — mtime cannot be used as a basis for judgment at all. We use sha256 content hashing instead, which stays stable across machines and across clones.

### 5.2 `www/manifest.json`

```json
{
  "version": 1,
  "pages": {
    "auth-design/overview": {
      "out": "pages/auth-design/overview.html",
      "out_sha": "ab12…",
      "spec_sha": "cd34…",
      "skill_sha": "ef56…",
      "main": {
        "notes/auth/overview.md": "1122…"
      },
      "refs": {
        "notes/auth/token-refresh.md": "3344…",
        "notes/storage/sessions.md": "5566…"
      },
      "generated_at": "2026-08-13T16:00:00+08:00"
    }
  }
}
```

The manifest's key is the **page id** (`<section>/<md filename>`), not the section name.
`main` is always exactly one entry — this is the data-structure embodiment of "one main file, one page"; more than one entry means something is wrong somewhere.

- `spec_sha`: a normalized content hash of that page's conf entry (title / note / that page's `main` path / the raw `refs` pattern).
  `refs` deliberately uses the raw pattern rather than the expanded file list: if a glob newly matches an additional reference file, it should be reported as `STALE:src` (source changed),
  not `STALE:spec` (config changed)
- `skill_sha`: a combined hash of every file under `.claude/skills/notes-to-html/`
- `out_sha`: a hash of the generated html, used to detect "manually edited after generation"

The manifest **is version-controlled**, so state is shared across machines — a page generated on one machine won't be regenerated on another.

### 5.3 Status Determination

| Status | Condition | What Claude Should Do |
|------|------|-----------------|
| `OK` | All hashes match | Skip |
| `NEW` | Defined in conf but not recorded in the manifest, or the output file doesn't exist | Generate |
| `STALE:src` | The main file's or a reference's sha changed, or the files matched by a `refs` glob increased/decreased | Regenerate |
| `STALE:spec` | The page's title / note / main / refs settings in conf changed | Regenerate |
| `STALE:skill` | Skill content changed | Regenerate (layout revised) |
| `DIRTY` | `out_sha` mismatch → the html was manually edited after generation | **Stop and ask the user**; regenerating would overwrite the manual edit |
| `ORPHAN` | A file under `www/pages/` is not defined in conf | Report; the user decides whether to delete it |
| `MISSING:src` | The source markdown doesn't exist, the glob matched nothing, or main filenames collide | Report a conf error (the whole section is reported as one row; none of that section's pages can be generated) |

### 5.4 `src/www.py` Interface

```
python3 src/www.py status              # Human-readable table
python3 src/www.py status --json       # Structured output for Claude to consume
python3 src/www.py status --stale-only # List only pages that need attention
python3 src/www.py plan <page id>      # Print that page's main / refs / note, for Claude to read
python3 src/www.py plan <section>      # Same as above, but lists all pages under that section at once
python3 src/www.py commit <page id>    # Backfill the manifest after generation (recomputes all hashes)
python3 src/www.py accept-skill        # Update only skill_sha without triggering regeneration (use when the Skill changed an unrelated part)
python3 src/www.py nav                 # Regenerate the www/index.html menu from conf
```

**The manifest is always backfilled via `commit`; Claude never hand-writes the JSON.** Hand-writing it would get the hash wrong, and would also just waste tokens.

### 5.5 Actual Workflow

```bash
# 1. Sync the markdown files first (existing process)
bash src/sync-notes.sh

# 2. See which pages need attention
python3 src/www.py status
```

```
GROUP         PAGE                       STATUS     DETAIL
────────────  ─────────────────────────  ─────────  ──────────────────────────────────────────────────
Architecture  auth-design/overview       OK         1 main file + 3 ref(s), 2026-08-13T16:00:00+08:00
Architecture  auth-design/token-refresh  NEW        no manifest record
Operations    log-rotation/intro         STALE:src  main 1 file(s) content changed
Operations    log-rotation/setup         DIRTY      output file was manually modified after generation

ORPHAN  www/pages/old-topic/intro.html (not defined in conf)

2 page(s) need generation; 1 page(s) need manual attention.
```

One row = one page. Multiple main files under the same section are listed as multiple rows.

### 5.6 Prompts That Trigger Translation

Translation is **manually triggered by the user** — there is no schedule, no hook. Just open Claude Code at the repo root and describe what you want directly.

**Any request that generates or modifies HTML must mention `notes-to-html` in the sentence.** That's the Skill's name — mentioning it guarantees Claude will load the layout conventions; without it, Claude might infer the right Skill from its `description` on its own, but that's not guaranteed, and failing to load it means the page gets laid out however Claude sees fit and fails `validate_page.py`.
Requests that merely check status or run `www.py` don't need to mention it.

| Scenario | Prompt |
|------|--------|
| Handle everything pending in one go | `Following the notes-to-html Skill, generate or update all NEW and STALE pages` |
| Only do one page | `Use the notes-to-html Skill to generate the auth-design/overview page` |
| Just want to know what needs doing | `Run python3 src/www.py status and tell me which pages need to be regenerated; don't start generating yet` |
| Add a new topic and generate it | `Add a new section to src/www.conf: put intro and setup from notes/logging/ as main, use the whole directory as refs, title it "Log Rotation Setup", group it under System Operations, then generate it with the notes-to-html Skill` |
| Redo the whole site after a Skill revision | `The Skill's layout has changed, regenerate all STALE:skill pages using notes-to-html` |
| Skill only had comments changed | `I only changed the Skill's comments, just run python3 src/www.py accept-skill, no need to regenerate` |
| Handling DIRTY | `auth-design/overview is DIRTY, show me what was manually changed with git diff first, then I'll decide whether to overwrite it` |
| Partially modify an existing page | `Following notes-to-html, the "key wrapping flow" diagram on the auth-design/overview page is hard to understand — change it to a sequence diagram, don't touch anything else, and remember to commit when done` |

You can also invoke the Skill directly with the `/notes-to-html` slash command.

Claude's action sequence: `status --json` → run `plan` for each NEW/STALE **page** to get its main and refs →
read main (and needed refs) → generate html per the Skill, keeping the heading structure exactly as in main → run `validate_page.py` to verify →
run `commit <page id>` → finally run `nav` once.
`OK` pages never go to the LLM; `DIRTY` stops and asks; `ORPHAN` and `MISSING:src` are only reported.

### 5.7 Cost Considerations

Translation is the only place in the entire pipeline that spends tokens, and the unit cost isn't low — a page containing multiple hand-drawn inline SVGs
(around 60,000 characters) is fairly expensive. So the value of the decision mechanism isn't just "avoiding duplication" —
it's making cost proportional to **the actual amount of change**, rather than to the total number of pages.

Cost is proportional to the number of `main` entries; `refs` are just read for reference and cost much less per entry. So the correct way to write
"a topic wants to cover ten markdown files" is to pick two or three as `main` and put the rest entirely in `refs` —
not to hang all ten under `main` and produce ten pages.

Two other amplification factors to watch for: changing `note` once makes **every page** in that section `STALE:spec` simultaneously;
changing any file in the Skill folder makes **all** pages `STALE:skill`. Think it through before changing the layout,
or use `accept-skill` afterward to suppress it.

## 6. The Skill's Location and Contract

**Location**: `.claude/skills/notes-to-html/SKILL.md`

A Claude Code skill is "a folder plus a SKILL.md"; SKILL.md must begin with YAML frontmatter.
Longer content can be split out, with SKILL.md pointing to it and loading it only when needed, to save context. Directory names follow the conventions of the
[Agent Skills specification](https://agentskills.io/specification): `references/` holds documentation,
`assets/` holds templates and data files (`page-template.html`, `glossary.json`), and `scripts/` holds executable scripts.

frontmatter uses only the six fields recognized by the spec (`name`, `description`, `license`, `compatibility`,
`metadata`, `allowed-tools`), so the same SKILL.md can, besides Claude Code, also be uploaded to claude.ai or go through the Skills API without being rejected for an "Unexpected key."
The body of SKILL.md uses `${CLAUDE_SKILL_DIR}` to refer to its own install path, rather than hard-coding `.claude/skills/...`.

**The contract the Skill must follow** (everything else is left to the layout's own discretion):

1. Produce **a single, self-contained html file with its own styling**, with no dependency on external CSS/JS files. Rationale: every page can be opened on its own,
   sent to a colleague on its own, and won't have style conflicts inside the menu shell's iframe.
2. The page must have a "Sources for this page" block listing which markdown files were referenced, linked back via relative paths.
   **The main file must be marked as `<li data-role="main">`, and there can be only one per page** — readers need to be able to tell which file dictated the page's heading structure.
3. **The page's heading structure must be inherited from the `main` markdown file**: heading order and hierarchy follow the original text — no adding, removing, or merging headings.
   Heading text may be polished for readability, but must not change what it's about. `refs` and any online research may only enrich what already sits under an existing heading.
4. Do not modify `manifest.json` directly.
5. If external JS needs to be referenced (e.g. mermaid), it must be vendored into the repo or inlined, since offline browsing must work.

## 7. Front-End Menu and Deployment

### 7.1 Why Pointing nginx Directly at www/ Isn't Enough

nginx is just a static file server; pointing it at `www/` only gives you a directory listing or a single page — no left-hand navigation, menu state is completely lost after switching pages, and there's no grouping.

But this **doesn't require a back end**. A purely static menu shell can achieve it.

### 7.2 Design of the Menu Shell

`www/index.html` is generated from conf by `www.py nav`:

- Left sidebar: grouped by `group`, sorted by `order`, collapsible, with a purely front-end title filter box
- Right `<iframe>` loads `pages/**/*.html`
- **Menu data is inlined directly into index.html**, without using `fetch()` to read JSON — this way it even works when double-clicked open directly via `file://`, with no server required
- Hash routing: `index.html#/<section>/<md filename>`, so links are shareable, reload returns to the same page, and back/forward navigation work correctly

**Why iframe instead of fetch + innerHTML**: every page carries its own `<style>`; stuffing them into the same document would cause styles to contaminate each other. iframe provides natural isolation, and doesn't require compromising the "every page can be opened independently" property for the sake of the shell.

### 7.3 Deployment

Full configuration is in [nginx-noteshub.conf](nginx-noteshub.conf), applied as follows:

```bash
sudo cp docs/nginx-noteshub.conf /etc/nginx/sites-available/noteshub
sudo ln -sf /etc/nginx/sites-available/noteshub /etc/nginx/sites-enabled/noteshub
sudo nginx -t && sudo systemctl reload nginx
```

Four key decisions:

1. **`root` points at the repo root, not `www/`**. The menu needs to be able to link to the `<mirror>/*/www/index.html` files that stayed in place — those live outside `www/`.
2. **`.md` must be given `default_type text/plain`**. `.md` isn't in nginx's default mime.types, so it gets treated as `application/octet-stream` — meaning clicking a link in each page's "Sources for this page" block (Skill contract item 2) triggers a download instead of displaying the content.
   You can't use `types { text/plain md; }` — writing a `types` block at the server level completely overrides the mime.types inherited from the http level, breaking every other file extension along with it.
3. **HTML gets `Cache-Control: no-cache`**. Pages get regenerated, and a stale browser cache would make it look like the translation didn't take effect. `no-cache` means the browser revalidates every time it comes back; if the content hasn't changed it still gets a 304.
4. **`location ~ /\.` blocks dot-prefixed paths**, covering `.git/`, `.claude/`, and `src/.sync-profile`.

**Bound interface**: the default is `listen 8081` / `listen [::]:8081`, i.e. bound on all interfaces — any machine on the same subnet can reach the whole repo. For local-only access, change it to `listen 127.0.0.1:8081;` and remove the IPv6 line.

For a quick look, nginx isn't required:

```bash
python3 -m http.server 8080   # from the repo root, then open http://localhost:8080/www/
```

Double-clicking `www/index.html` (`file://`) also works, but theme syncing does not: the browser blocks cross-frame access under `file://`, so pages never receive the shell's `nt-theme` message and fall back to following the system color scheme.

## 8. A Few Non-Obvious Constraints

These were all discovered only by actually running into them during implementation — know them before changing related code:

| Constraint | Why |
|------|------|
| `skill_sha` must exclude `.DS_Store` and `__pycache__` | Otherwise running `make_chart.py` once on another machine, generating a `.pyc`, would make the entire site spuriously `STALE:skill` |
| At ≤860px the menu shell must turn the sidebar into an overlay and yield the full width | `validate_page.py`'s `[E]` check assumes a worst-case iframe width of 320px. If the sidebar doesn't yield, the iframe becomes narrower than the check assumes, and chart font size drops below the minimum **without the validator catching it** |
| The menu's group `id`s are prefixed with a sequence number | Purely non-ASCII (e.g. Chinese) `group` names collapse to the same run of underscores after sanitizing, so two different non-ASCII groups would collide on id — collapsing one would then also affect the other group's list |
| nginx must set the mime type for `.md` | Without it, every page's "Sources for this page" links trigger a download instead of displaying content, directly violating the intent of contract item 2 |
| Theme sync breaks under `file://` | The browser blocks cross-frame access, so pages never receive the shell's message. Acceptable, but must be documented so it isn't mistaken for a bug |

## 9. Things Not Done For Now

1. **PDF output**. HTML already satisfies browsing needs, while PDF requires an additional toolchain (installing weasyprint, or using headless browser printing). If done, it should be planned as adding a `formats = html,pdf` field to conf.
2. **Two-level grouping** (e.g. `group = System / Security Mechanisms`). Currently single-level; once the number of topics grows past a few dozen, two levels would make things easier to find.
3. **`www.conf` supporting profiles**. Not currently supported, since sources are all repo-relative paths and identical across every machine — unless some pages need to be generated only on a specific machine.
4. **Full-text search**. Currently only menu-title filtering is done. Cross-page full-text search would require generating an additional index at the `nav` stage.
