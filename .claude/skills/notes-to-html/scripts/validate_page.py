#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_page.py -- strict validation checks for notes-to-html generated pages

    python3 .claude/skills/notes-to-html/scripts/validate_page.py www/pages/**/*.html
    python3 .claude/skills/notes-to-html/scripts/validate_page.py www/pages/xx.html --json

Uses only the python3 standard library, consistent with the constraints of src/www.py.
This script never touches manifest.json, and never writes any files.

Rationale: since there is no build step, every rule has to be followed by hand (by
humans and AI alike), and both will forget. Each check corresponds to a real mistake
that actually happened at some point.

  [A] SVG coordinates must not exceed the viewBox
  [B] Hardcoded color codes are forbidden inside SVG
  [C] Figure completeness (figure number / title / legend / caption / text equivalent / aria-label)
  [D] --fig-vb must equal the viewBox width      <- with no build step, this is the easiest to get wrong
  [E] Effective font size under the worst-case container width must be >= 9.5px;
      a scrolling-type viewBox > 740 emits a WARN
  [F] All internal anchors must be resolvable
  [G] Color contrast meets WCAG AA (for both dark and light themes)
  [H] SVG text must not overflow its bounding box (including CJK full-width characters)
  [I] CSS specificity for the dual-variant switch
  [J] Term cards correspond to the embedded glossary, and each entry has a source
  [K] Data chart information completeness
  [L] When a diagram has arrows, the legend must state what the arrows mean (FAIL)
  [M] MathML structure
  [N] Offline self-containment: must not reference any external resources    <- contract clause 1
  [O] Sources for this page: exist, resolve correctly, main file is marked  <- contract clause 2
  [P] iframe compatibility and forbidden items                             <- contract clauses 3 & 4
  [Q] No unfilled <<<...>>> placeholders left over from the skeleton
"""

import json
import os
import re
import sys
import unicodedata
from pathlib import Path

MIN_EFFECTIVE_PX = 9.5

# Placeholders in assets/page-template.html are written <<<like this>>> and every one of them
# must be replaced when a page is produced. The skeleton itself is not a page, so validating it
# as one would always fail [O]: its <<<...>>> source paths cannot resolve on the filesystem.
PLACEHOLDER = re.compile(r"<<<.*?>>>", re.S)
SKELETON_NAME = "page-template.html"

# Canvas width ceiling for the scrolling type. Above this it scrolls horizontally at the
# most common laptop widths (container 748).
SCROLL_MAX_W = 740

# The "worst-case container width" derived from the breakpoints in assets/page-template.html.
# The width here refers to the iframe's visual width, not the browser window -- the page lives
# inside an iframe in www/index.html, and the left-hand menu already eats into part of that width.
#
#   Narrow variant (iframe < 880): worst case iframe 320, gutter 16*2, figure frame padding 10*2 -> 268
#   Wide variant (iframe >= 880):
#       iframe 880  without in-page TOC: 880 - 35*2 - 16*2 = 778
#       iframe 1100 with in-page TOC:    1100 - 40*2 - (200+40) - 16*2 = 748  <- stricter
#   Scrolling type: always 1:1
WORST = {"narrow": 268, "wide": 748, "plain": 268}


class Report:
    def __init__(self):
        self.ok, self.warn, self.fail = [], [], []

    def O(self, c, m): self.ok.append((c, m))
    def W(self, c, m): self.warn.append((c, m))
    def F(self, c, m): self.fail.append((c, m))


def num(attrs, key):
    m = re.search(r'\b%s="([\-\d.]+)"' % key, attrs)
    return float(m.group(1)) if m else None


def is_skeleton(path: Path, html: str):
    """The skeleton is the file pages are copied from, not a page. Recognised by filename;
    a copy saved under any other name is deliberately treated as a real page."""
    return path.name == SKELETON_NAME and PLACEHOLDER.search(html) is not None


def check(path: Path, R: Report):
    html = path.read_text(encoding="utf-8")
    # Strip out style/script before extracting markup: a "<svg>" substring appearing inside a
    # CSS comment would cause the loose regex to start matching from within the comment, swallowing
    # the entire CSS block and silently invalidating the checks that follow.
    markup = re.sub(r'<(style|script)\b.*?</\1>', '', html, flags=re.S)
    svgs = re.findall(r"<svg\s[^>]*>.*?</svg>", markup, re.S)
    figures = re.findall(r"<figure\b.*?</figure>", markup, re.S)
    css_sizes = {k: float(v) for k, v in
                 re.findall(r'svg \.([a-z][\w\-]*)\s*\{[^}]*font-size:\s*([\d.]+)px', html)}

    # ---------------------------------------------------------------- [Q]
    # Nothing else catches these: an unreplaced <<<YYYY-MM-DD>>> or <<<Page title>>> renders
    # straight to the reader and every other check still passes.
    left = PLACEHOLDER.findall(markup)
    if left:
        shown = [re.sub(r"\s+", " ", x)[:48] for x in left[:5]]
        R.F("Q", "%d placeholder(s) from the skeleton were never filled in: %s%s"
                 % (len(left), ", ".join(shown), " ..." if len(left) > 5 else ""))
    else:
        R.O("Q", "No skeleton placeholders left unfilled")

    # ---------------------------------------------------------------- [N]
    ext = []
    for m in re.finditer(r'<(?:link|script|img|source|iframe)\b[^>]*\b(?:href|src)="([^"]+)"',
                         html, re.I):
        u = m.group(1)
        if re.match(r'(https?:)?//', u) or u.startswith("data:") is False and "://" in u:
            ext.append(u)
    for m in re.finditer(r'url\(\s*[\'"]?((?:https?:)?//[^)\'"]+)', html, re.I):
        ext.append(m.group(1))
    if re.search(r'@import\s+', html):
        ext.append("@import")
    if ext:
        R.F("N", "External resources are referenced, breaking the offline / single-file contract: %s" % sorted(set(ext))[:5])
    else:
        R.O("N", "Offline self-contained: no external CSS/JS/fonts/images")

    if re.search(r'<link\b[^>]*rel="stylesheet"', html, re.I):
        R.F("N", "An external stylesheet link exists; all styles must be inlined")
    if not re.search(r'<style\b', html):
        R.F("N", "The page has no inline <style>, so it cannot be rendered as a single file")

    # ---------------------------------------------------------------- [O]
    sec = re.search(r'<section class="sources"[^>]*>(.*?)</section>', markup, re.S)
    if not sec:
        R.F("O", "Missing the \"page sources\" section (contract clause 2)")
    else:
        hrefs = re.findall(r'<a\s[^>]*href="([^"]+)"', sec.group(1))
        hrefs = [h for h in hrefs if not h.startswith("#")]
        if not hrefs:
            R.F("O", "No links found in the sources section")
        else:
            missing = []
            for h in hrefs:
                target = (path.parent / h).resolve()
                if not target.exists():
                    missing.append(h)
            if missing:
                R.F("O", "%d source path(s) could not be found on the filesystem: %s"
                    % (len(missing), ", ".join(missing[:4])))
            else:
                R.O("O", "All %d source path(s) resolved successfully" % len(hrefs))
            if any(not h.endswith(".md") for h in hrefs):
                R.W("O", "The source list has non-.md item(s); confirm this is intentional")

        # One main file = one page: the source list should make clear which entry is the
        # primary source and which are merely supporting references. Without this marker,
        # readers cannot tell which md file the heading structure maps back to, and thus
        # cannot detect the regression where "this page actually merges several md files together".
        mains = re.findall(r'<li\b[^>]*\bdata-role="main"', sec.group(1))
        if len(mains) != 1:
            R.F("O", 'The sources section must mark exactly one main file (<li data-role="main">); '
                     "there are currently %d. For multiple main files, add more `main` entries in "
                     "www.conf and split into one page each"
                     % len(mains))
        else:
            first = re.search(r"<li\b[^>]*>", sec.group(1))
            if first and 'data-role="main"' not in first.group(0):
                R.W("O", "The main file is not the first item in the source list; consider moving it to the front")
            else:
                R.O("O", "The main file is marked as the first item in the source list")

        cites = re.findall(r'<sup class="cite"><a href="#([^"]+)"', markup)
        ids = set(re.findall(r'<li id="([^"]+)"', sec.group(1)))
        if not cites:
            R.W("O", "No inline source citations found in the text; readers cannot tell which note each passage comes from")
        else:
            bad = sorted(set(c for c in cites if c not in ids))
            if bad:
                R.F("O", "Inline source citation(s) point to non-existent entries: %s" % ", ".join(bad))
            else:
                R.O("O", "All %d inline source citation(s) resolved successfully" % len(cites))

    # ---------------------------------------------------------------- [P]
    # Mentioning manifest.json inside a comment is just explanatory text (the skeleton itself
    # says "must not read/write it"), and is not a violation; only check the parts that are
    # actually executed or linked to.
    live = re.sub(r'<!--.*?-->', '', html, flags=re.S)
    if "manifest.json" in live:
        R.F("P", "The page actually references manifest.json; the Skill must not read/write it (contract clause 3)")
    else:
        R.O("P", "manifest.json is not touched")
    if re.search(r'<base\b', html, re.I):
        R.F("P", "Uses <base>, which breaks relative paths inside an iframe")
    if "window.self !== window.top" not in html and "window.self!==window.top" not in html:
        R.W("P", "No iframe-context detection found; theme sync and opening external links in a new tab may fail")
    else:
        R.O("P", "Has iframe-context detection")
    if re.search(r'localStorage|sessionStorage', html):
        R.W("P", "Uses browser storage; behavior differs between file:// and iframe contexts, so avoid it")

    # ---------------------------------------------------------------- [A]
    for i, s in enumerate(svgs, 1):
        vb = re.search(r'viewBox="([\d.\s\-]+)"', s)
        if not vb:
            R.F("A", "SVG #%d is missing a viewBox" % i)
            continue
        vx, vy, vw, vh = (float(v) for v in vb.group(1).split())
        bad = []
        for m in re.finditer(r'<rect\b([^>]*)>', s):
            a = m.group(1)
            x, y, w, h = (num(a, k) for k in ("x", "y", "width", "height"))
            if None in (x, y, w, h):
                continue
            if x < vx - 1 or y < vy - 1 or x + w > vx + vw + 1 or y + h > vy + vh + 1:
                bad.append("rect(%g,%g)" % (x, y))
        for m in re.finditer(r'<line\b([^>]*)>', s):
            a = m.group(1)
            p = [num(a, k) for k in ("x1", "y1", "x2", "y2")]
            if None in p:
                continue
            for px, py in ((p[0], p[1]), (p[2], p[3])):
                if not (vx - 1 <= px <= vx + vw + 1 and vy - 1 <= py <= vy + vh + 1):
                    bad.append("line(%g,%g)" % (px, py))
        for m in re.finditer(r'<circle\b([^>]*)>', s):
            a = m.group(1)
            cx, cy, r = (num(a, k) for k in ("cx", "cy", "r"))
            if None in (cx, cy, r):
                continue
            if cx - r < vx - 1 or cy - r < vy - 1 or cx + r > vx + vw + 1 or cy + r > vy + vh + 1:
                bad.append("circle(%g,%g)" % (cx, cy))
        for m in re.finditer(r'<text\b([^>]*)>', s):
            a = m.group(1)
            x, y = num(a, "x"), num(a, "y")
            if x is None or y is None:
                continue
            if not (vx - 1 <= x <= vx + vw + 1 and vy - 1 <= y <= vy + vh + 1):
                bad.append("text(%g,%g)" % (x, y))
        for m in re.finditer(r'<path\b[^>]*\bd="([^"]+)"', s):
            ns = [float(n) for n in re.findall(r'-?\d+\.?\d*', m.group(1))]
            if max(ns, default=0) <= 10:
                continue
            for k in range(0, len(ns) - 1, 2):
                if not (vx - 2 <= ns[k] <= vx + vw + 2):
                    bad.append("path x=%g" % ns[k])
        if bad:
            R.F("A", "SVG #%d has %d element(s) exceeding the canvas: %s" % (i, len(bad), ", ".join(bad[:5])))
        else:
            R.O("A", "SVG #%d (%gx%g): all elements are within the canvas" % (i, vw, vh))

    # ---------------------------------------------------------------- [B]
    for i, s in enumerate(svgs, 1):
        hard = [h for h in re.findall(
            r'(?:fill|stroke)="(#[0-9a-fA-F]{3,8}|rgb\([^)]*\)|[a-z]+)"', s)
            if h not in ("none", "currentColor")]
        if hard:
            R.F("B", "SVG #%d has hardcoded color code(s) not using tokens: %s" % (i, sorted(set(hard))))
    if svgs and not any("[B]" == c for c, _ in R.fail):
        R.O("B", "All %d SVG(s) use design tokens for every color" % len(svgs))

    # ---------------------------------------------------------------- [C]
    REQ = {"figure number": r'class="fig-num"', "title": r'class="fig-title"',
           "legend": r'class="legend"', "caption": r'<figcaption',
           "text equivalent": r'<details', "aria-label": r'aria-label='}
    for i, f in enumerate(figures, 1):
        miss = [k for k, p in REQ.items() if not re.search(p, f)]
        if miss:
            R.F("C", "figure #%d is missing: %s" % (i, ", ".join(miss)))
        else:
            R.O("C", "figure #%d has all six required elements" % i)

    # ---------------------------------------------------------------- [D]
    for i, s in enumerate(svgs, 1):
        vb = re.search(r'viewBox="([\d.\s\-]+)"', s)
        fv = re.search(r'--fig-vb:\s*([\d.]+)px', s)
        if not vb:
            continue
        w = float(vb.group(1).split()[2])
        if not fv:
            R.F("D", "SVG #%d is missing style=\"--fig-vb:%gpx\"; "
                     "max-width will fail to apply and it will be enlarged to the container width" % (i, w))
        elif abs(float(fv.group(1)) - w) > 0.5:
            R.F("D", "SVG #%d --fig-vb=%s does not match the viewBox width %g" % (i, fv.group(1), w))
        else:
            R.O("D", "SVG #%d --fig-vb=%gpx matches the viewBox" % (i, w))

    # ---------------------------------------------------------------- [E]
    for i, s in enumerate(svgs, 1):
        vb = re.search(r'viewBox="([\d.\s\-]+)"', s)
        if not vb:
            continue
        w = float(vb.group(1).split()[2])
        used = set(re.findall(r'class="([a-z][\w\-]*)"', s))
        sizes = [css_sizes[c] for c in used if c in css_sizes]
        sizes += [float(x) for x in re.findall(r'font-size[:=]"?\s*([\d.]+)(?:px)?', s)]
        if not sizes:
            R.W("E", "SVG #%d: no font-size declaration found" % i)
            continue
        mf = min(sizes)
        frame = next((f for f in figures if s in f), "")
        if "fig-scroll" in frame:
            kind, cont = "scrolling 1:1", w
            # 900 guarantees the font size won't break, 740 guarantees no scrolling is needed --
            # they govern different things. At the breakpoint where the in-page TOC appears
            # (iframe 1100) the container is only 748; see references/rwd.md.
            if w > SCROLL_MAX_W:
                R.W("E", "SVG #%d scrolling type viewBox=%g > %g, will scroll horizontally at "
                         "iframe 1100 (container %g); try \"change direction -> reduce density -> "
                         "split the diagram\" before reaching for dual variants"
                         % (i, w, SCROLL_MAX_W, WORST["wide"]))
        elif 'only-wide' in s[:220]:
            kind, cont = "wide variant (iframe≥880)", WORST["wide"]
        elif 'only-narrow' in s[:220]:
            kind, cont = "narrow variant (iframe<880)", WORST["narrow"]
        else:
            kind, cont = "all breakpoints", WORST["plain"]
        scale = min(1.0, cont / w)
        eff = mf * scale
        tag = ("SVG #%d %s viewBox=%g min font-size=%gpx worst-case container=%gpx → scale %.2f, effective %.1fpx"
               % (i, kind, w, mf, cont, scale, eff))
        (R.O if eff >= MIN_EFFECTIVE_PX else R.F)("E", tag)

    # ---------------------------------------------------------------- [L]
    # Only required when the diagram actually has arrows. No edges, no edge semantics.
    # This only checks *that* something was written, not whether it was written correctly,
    # and it can't stop a relationship being expressed with a line that has no arrowhead.
    # Both "arrow" and the CJK equivalent count, so pages written in either language pass.
    ARROW_WORDS = ("arrow", "\u7bad\u982d")
    arrowed = [f for f in figures if "marker-end" in f]
    miss = []
    for f in arrowed:
        leg = re.search(r'<div class="legend">(.*?)</div>', f, re.S)
        text = (leg.group(1) if leg else "").lower()
        if not any(wd in text for wd in ARROW_WORDS):
            fn = re.search(r'fig-num">([^<]+)<', f)
            miss.append(fn.group(1).strip() if fn else "?")
    if miss:
        R.F("L", "%d diagram(s) have arrows but the legend does not say what the arrows mean: %s"
                 % (len(miss), ", ".join(miss)))
    elif arrowed:
        R.O("L", "%d diagram(s) with arrows all state the edge semantics in the legend" % len(arrowed))

    # ---------------------------------------------------------------- [F]
    anchors = set(re.findall(r'\bid="([^"]+)"', html))
    hrefs = set(re.findall(r'href="#([^"]+)"', html))
    broken = sorted(h for h in hrefs if h not in anchors)
    if broken:
        R.F("F", "In-page anchor(s) do not exist: %s" % ", ".join(broken))
    else:
        R.O("F", "All %d in-page anchor(s) resolved successfully" % len(hrefs))

    # ---------------------------------------------------------------- [G]
    def lum(h):
        h = h.lstrip('#')
        r, g, b = (int(h[k:k + 2], 16) / 255 for k in (0, 2, 4))
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + .055) / 1.055) ** 2.4
        return .2126 * f(r) + .7152 * f(g) + .0722 * f(b)

    def ratio(a, b):
        la, lb = lum(a), lum(b)
        return (max(la, lb) + .05) / (min(la, lb) + .05)

    # --text-faint used to require only 3.0 (treated as decorative text), but it is actually
    # used for svg .t-tag (10px) and svg .t-mono (10.5px) -- that is WCAG "body text", where the
    # threshold is 4.5. On top of that, SVG text sits on --dg-surface and code comments sit on
    # --bg-sunken, so checking against --bg alone misses those two backgrounds (in practice
    # --dg-surface is the first one to break).
    PAIRS = [("--text", "--bg", 4.5), ("--text-muted", "--bg", 4.5),
             ("--text-faint", "--bg", 4.5), ("--accent", "--bg", 4.5),
             ("--text-faint", "--dg-surface", 4.5), ("--text-muted", "--dg-surface", 4.5),
             ("--text-faint", "--bg-sunken", 4.5), ("--text-faint", "--bg-raised", 4.5),
             ("--dg-hw", "--dg-hw-bg", 3.0), ("--dg-verified", "--dg-verified-bg", 3.0),
             ("--dg-key", "--dg-key-bg", 3.0), ("--dg-fail", "--dg-fail-bg", 3.0),
             ("--dg-data", "--dg-data-bg", 3.0), ("--dg-neutral", "--dg-neutral-bg", 3.0)]
    for label, pat in (("dark", r':root,\s*\[data-theme="dark"\]\s*\{(.*?)\n\}'),
                       ("light", r'\[data-theme="light"\]\s*\{(.*?)\n\}')):
        blk = re.search(pat, html, re.S)
        if not blk:
            R.W("G", "Could not find the token block for the %s theme" % label)
            continue
        tk = dict(re.findall(r'(--[\w\-]+):\s*(#[0-9a-fA-F]{6})', blk.group(1)))
        bad = 0
        for fg, bg, need in PAIRS:
            if fg in tk and bg in tk:
                r = ratio(tk[fg], tk[bg])
                if r < need:
                    bad += 1
                    R.F("G", "%s %s on %s = %.2f:1, below the required %s" % (label, fg, bg, r, need))
        if not bad:
            R.O("G", "%s theme: all %d color contrast pair(s) meet the requirement" % (label, len(PAIRS)))

    # ---------------------------------------------------------------- [H]
    mono_cls = {k for k in css_sizes if re.search(r'svg \.%s\s*\{[^}]*font-mono' % k, html)}

    def est(t, fs, mono):
        w = 0.0
        for ch in t:
            if unicodedata.east_asian_width(ch) in ("W", "F"):
                w += 1.0
            elif mono:
                w += .6
            elif ch == ' ':
                w += .28
            elif ch in "iljI.,:;'`|":
                w += .30
            elif ch.isupper():
                w += .68
            else:
                w += .55
        return w * fs

    over = 0
    for si, s in enumerate(svgs, 1):
        rects = []
        for m in re.finditer(r'<rect\b([^>]*)>', s):
            a = m.group(1)
            v = [num(a, k) for k in ("x", "y", "width", "height")]
            if None not in v:
                rects.append(v)
        for m in re.finditer(r'<text\b([^>]*)>(.*?)</text>', s, re.S):
            a, txt = m.group(1), re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if not txt:
                continue
            x, y = num(a, "x"), num(a, "y")
            if x is None or y is None:
                continue
            cm = re.search(r'class="([a-z][\w\-]*)"', a)
            cls = cm.group(1) if cm else None
            fs = css_sizes.get(cls)
            im = re.search(r'font-size:\s*([\d.]+)px', a)
            if im:
                fs = float(im.group(1))
            if fs is None:
                continue
            w = est(txt, fs, cls in mono_cls)
            x0 = x - w / 2 if 'text-anchor="middle"' in a else x
            inside = [r for r in rects
                      if r[0] <= x <= r[0] + r[2] and r[1] <= y <= r[1] + r[3]]
            if not inside:
                continue
            bx, by, bw, bh = min(inside, key=lambda r: r[2] * r[3])
            if x0 < bx + 6 or x0 + w > bx + bw - 6:
                over += 1
                R.F("H", "SVG #%d text overflow: %r estimated width %.0f, box width %.0f" % (si, txt[:28], w, bw))
    if svgs and not over:
        R.O("H", "All SVG text stays within its bounding box (including CJK full-width estimation)")

    # ---------------------------------------------------------------- [I]
    def spec(sel):
        sel = re.sub(r'::[\w\-]+', ' ', sel)
        return (len(re.findall(r'#[\w\-]+', sel)),
                len(re.findall(r'\.[\w\-]+', sel)) + len(re.findall(r'\[[^\]]+\]', sel))
                + len(re.findall(r':(?!:)[\w\-]+', sel)),
                len(re.findall(r'(?:^|[\s>+~(])([a-zA-Z][\w\-]*)', sel)))

    VAR = ["only-narrow", "only-wide"]
    css = re.sub(r'/\*.*?\*/', '',
                 "\n".join(re.findall(r'<style[^>]*>(.*?)</style>', html, re.S)), flags=re.S)
    rules = []
    for m in re.finditer(r'([^{}@]+)\{([^{}]*)\}', css):
        sel, b = m.group(1).strip(), m.group(2)
        if 'display:' not in b.replace(' ', ''):
            continue
        for one in [x.strip() for x in sel.split(',') if x.strip()]:
            if 'svg' in one or any(v in one for v in VAR):
                rules.append((one, spec(one)))
    gen = [r for r in rules if not any(v in r[0] for v in VAR)]
    var = [r for r in rules if any(v in r[0] for v in VAR)]
    if var:
        g = max(gen, key=lambda r: r[1], default=None)
        v = min(var, key=lambda r: r[1])
        if g and g[1] >= v[1]:
            R.F("I", "Variant rule `%s` %s is not higher specificity than general rule `%s` %s → both variants will render at the same time"
                % (v[0], v[1], g[0], g[1]))
        else:
            R.O("I", "Variant-switch specificity %s > general svg rule %s" % (v[1], g[1] if g else "(none)"))
        for s in svgs:
            for vv in VAR:
                if 'class="%s"' % vv in s and 'aria-hidden' in s:
                    R.F("I", "Variant .%s is aria-hidden, making it invisible to assistive tech at the breakpoint it's responsible for" % vv)

    # ---------------------------------------------------------------- [J]
    gm = re.search(r'<script type="application/json" id="glossary-data">(.*?)</script>',
                   html, re.S)
    used = re.findall(r'data-term="([^"]+)"', html)
    if used and not gm:
        R.F("J", "Term markers exist but no embedded glossary data was found")
    elif gm:
        try:
            gl = json.loads(gm.group(1))
        except Exception as e:
            R.F("J", "Failed to parse glossary JSON: %s" % e)
            gl = {}
        gl = {k: v for k, v in gl.items() if not k.startswith("_")}
        missing = sorted(set(u for u in used if u not in gl))
        if missing:
            R.F("J", "The following data-term(s) were not found in the glossary: %s" % ", ".join(missing))
        elif used:
            R.O("J", "All %d term marker(s) resolved (out of %d definition(s) total)" % (len(used), len(gl)))
        nosrc = sorted(k for k, v in gl.items() if isinstance(v, dict) and not v.get("source"))
        if nosrc:
            R.F("J", "The following glossary entries are missing a source: %s" % ", ".join(nosrc))
        elif gl:
            R.O("J", "All glossary entries have a source noted")
        orphan = sorted(k for k in gl if k not in used)
        if orphan:
            R.W("J", "%d glossary entry/entries are unused; a single-file page should only keep the ones actually used: %s"
                % (len(orphan), ", ".join(orphan[:5])))
        badtag = re.findall(r'<(?!button)(\w+)[^>]*class="term"', html)
        if badtag:
            R.F("J", "Term markers must use <button>; found: %s" % sorted(set(badtag)))

    # ---------------------------------------------------------------- [K]
    charts = re.findall(r'<figure data-chart="1".*?</figure>', markup, re.S)
    for i, c in enumerate(charts, 1):
        p = []
        if not re.search(r'class="chart-method"', c):
            p.append("missing measurement method")
        if "<table" not in c:
            p.append("missing raw data table")
        if "Source:" not in c:
            p.append("missing data source")
        if 'class="only-wide"' not in c or 'class="only-narrow"' not in c:
            p.append("missing dual variants")
        if not re.search(r'\([^)]+\)', c):
            p.append("axis label appears to be missing a unit")
        if "error bars = not declared" in c:
            p.append("error-bar meaning left as the undeclared placeholder")
        if p:
            R.F("K", "Chart #%d: %s" % (i, ", ".join(p)))
        else:
            R.O("K", "Chart #%d has complete information" % i)

    # ---------------------------------------------------------------- [M]
    blocks = re.findall(r'<div class="math-block".*?</div>\s*</div>', markup, re.S)
    inline = re.findall(r'class="math-inline"', markup)
    if blocks or inline:
        if "<math" not in markup:
            R.F("M", "There is a math block but no <math>; MathML is required for offline rendering")
        else:
            R.O("M", "Math expressions use MathML (no external dependency)")
        if re.search(r'katex|mathjax', html, re.I):
            R.F("M", "KaTeX/MathJax detected, which breaks the offline / single-file contract; use MathML instead")
        ns = re.findall(r'<math\b([^>]*)>', markup)
        nons = [a for a in ns if 'xmlns=' not in a]
        if nons:
            R.W("M", "%d <math> element(s) are missing the xmlns attribute; some browsers will fail to render them" % len(nons))
        noscroll = [b for b in blocks if 'class="math-scroll"' not in b]
        if noscroll:
            R.F("M", "%d display equation(s) are not wrapped in .math-scroll; long formulas will widen the whole page" % len(noscroll))
        elif blocks:
            R.O("M", "All %d display equation(s) have their own horizontal-scroll container" % len(blocks))
        noid = [b for b in blocks if not re.search(r'id="eq-', b)]
        if noid:
            R.F("M", "%d display equation(s) are missing an id" % len(noid))
        secs = re.split(r'(?=<h2 )', markup)
        bad = [re.sub(r'<[^>]+>', '', (re.search(r'<h2[^>]*>(.*?)</h2>', s) or
                                       re.match(r'()', '')).group(1) if
                      re.search(r'<h2[^>]*>(.*?)</h2>', s) else "(unnamed)")
               for s in secs if 'class="math-block"' in s and 'class="symtab"' not in s]
        if bad:
            R.F("M", "The following heading(s) have display equations but no symbol table: %s" % ", ".join(bad))
        elif blocks:
            R.O("M", "All headings containing display equations include a symbol table")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(2)

    total_fail = 0
    results = {}
    for arg in args:
        p = Path(arg)
        if not p.exists():
            print("File not found: %s" % arg)
            total_fail += 1
            continue
        if is_skeleton(p, p.read_text(encoding="utf-8")):
            n_ph = len(PLACEHOLDER.findall(p.read_text(encoding="utf-8")))
            msg = ("%s is the skeleton, not a page (%d placeholder(s) to fill in) — "
                   "page checks skipped. Validate the page you produced from it instead."
                   % (p, n_ph))
            results[str(p)] = {"skeleton": True, "placeholders": n_ph,
                               "pass": 0, "warn": 0, "fail": 0,
                               "details": {"fail": [], "warn": []}}
            if not as_json:
                print(msg + "\n")
            continue
        R = Report()
        check(p, R)
        results[str(p)] = {
            "pass": len(R.ok), "warn": len(R.warn), "fail": len(R.fail),
            "details": {"fail": ["[%s] %s" % x for x in R.fail],
                        "warn": ["[%s] %s" % x for x in R.warn]},
        }
        total_fail += len(R.fail)
        if not as_json:
            print("%s  (%d SVG)" % (p, len(re.findall(
                r'<svg\s', re.sub(r'<(style|script)\b.*?</\1>', '',
                                  p.read_text(encoding='utf-8'), flags=re.S)))))
            print("=" * 80)
            for c, m in R.ok:
                print("  PASS  [%s] %s" % (c, m))
            for c, m in R.warn:
                print("  WARN  [%s] %s" % (c, m))
            for c, m in R.fail:
                print("  FAIL  [%s] %s" % (c, m))
            print("-" * 80)
            print("PASS %d   WARN %d   FAIL %d\n" % (len(R.ok), len(R.warn), len(R.fail)))

    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    sys.exit(1 if total_fail else 0)


if __name__ == "__main__":
    main()
