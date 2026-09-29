#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_chart.py -- data chart generator (line / bar / scatter)

Why not use a library like Chart.js:
  1. They draw at runtime, so validate_page.py cannot statically check whether axis labels,
     units, and sample sizes are all present.
  2. Their font-size and scaling behavior isn't governed by the --fig-vb rule, so they
     bypass the entire RWD guarantee.
  3. The resulting canvas has no text-equivalent description and cannot be searched.
This file outputs plain SVG, applying exactly the same tokens, font sizes, and
dual-variant rules as hand-drawn charts.

Usage:
    from make_chart import render_chart
    html = render_chart(json.load(open("data/boot-time.json")))

Or run directly:
    python3 scripts/make_chart.py data/boot-time.json > /tmp/fig.html
"""

import html as _html
import json
import math
import sys

# Data-series colors, cycled in order. Deliberately spans hue and brightness so
# readers with color blindness can still tell them apart; each series is also paired
# with a differently-shaped marker so it can be distinguished without relying on color.
SERIES_TOKENS = ["--dg-data", "--dg-verified", "--dg-key",
                 "--dg-hw", "--dg-fail", "--dg-neutral"]
MARKERS = ["circle", "square", "triangle", "diamond", "cross", "plus"]

# Geometry and font sizes for the two variants. The narrow variant's font size must be
# enlarged, because a 340 viewBox shrinks to 0.79x under a 268px container
# (see references/rwd.md).
VARIANTS = {
    "wide":   dict(w=720, h=430, ml=66, mr=18, mt=18, mb=64,
                   cls_axis="t-role", cls_tick="t-chip-v", cls_title="t-title"),
    "narrow": dict(w=340, h=430, ml=54, mr=12, mt=16, mb=76,
                   cls_axis="n-role", cls_tick="n-mono", cls_title="n-title"),
}


def esc(s):
    return _html.escape(str(s), quote=True)


# --------------------------------------------------------------------------
# Ticks: pick "human-readable" intervals (1 / 2 / 5 x 10^n), not something like 3.7143
# --------------------------------------------------------------------------
def nice_ticks(lo, hi, target=6, clamp_zero=False):
    if hi == lo:
        hi = lo + 1
    raw = (hi - lo) / target
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for m in (1, 2, 2.5, 5, 10):
        if raw / mag <= m:
            step = m * mag
            break
    else:
        step = 10 * mag
    start = math.floor(lo / step) * step
    end = math.ceil(hi / step) * step
    # When yZero is set, the axis floor must be exactly 0 -- padding must not push it into a negative tick
    if clamp_zero and start < 0:
        start = 0.0
    ticks, v = [], start
    while v <= end + step * 1e-9:
        ticks.append(round(v, 10))
        v += step
    return ticks, start, end


def fmt(v):
    if v == int(v):
        return str(int(v))
    return ("%.10g" % v)


def marker(kind, cx, cy, r, color):
    if kind == "square":
        return ('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="var(%s)"/>'
                % (cx - r, cy - r, 2 * r, 2 * r, color))
    if kind == "triangle":
        return ('<path d="M%.1f %.1f L%.1f %.1f L%.1f %.1f Z" fill="var(%s)"/>'
                % (cx, cy - r * 1.2, cx + r * 1.1, cy + r, cx - r * 1.1, cy + r, color))
    if kind == "diamond":
        return ('<path d="M%.1f %.1f L%.1f %.1f L%.1f %.1f L%.1f %.1f Z" fill="var(%s)"/>'
                % (cx, cy - r * 1.3, cx + r * 1.3, cy, cx, cy + r * 1.3, cx - r * 1.3, cy, color))
    if kind in ("cross", "plus"):
        d = r * 1.1
        p = ('<path d="M%.1f %.1f L%.1f %.1f M%.1f %.1f L%.1f %.1f" '
             'stroke="var(%s)" stroke-width="2.2" fill="none"/>')
        if kind == "cross":
            return p % (cx - d, cy - d, cx + d, cy + d, cx - d, cy + d, cx + d, cy - d, color)
        return p % (cx - d, cy, cx + d, cy, cx, cy - d, cx, cy + d, color)
    return '<circle cx="%.1f" cy="%.1f" r="%.1f" fill="var(%s)"/>' % (cx, cy, r, color)


# --------------------------------------------------------------------------
# SVG for a single variant
# --------------------------------------------------------------------------
def build_svg(spec, variant, extra_class):
    V = VARIANTS[variant]
    W, H = V["w"], V["h"]
    ml, mr, mt, mb = V["ml"], V["mr"], V["mt"], V["mb"]
    pw, ph = W - ml - mr, H - mt - mb
    kind = spec.get("type", "line")
    series = spec["series"]
    narrow = variant == "narrow"
    r = 5.0 if narrow else 3.8

    # ---- Y range. If it doesn't start from 0 by default, this must be explicitly declared in spec, to avoid unintentionally exaggerating differences ----
    vals = []
    for s in series:
        for p in s["points"]:
            e = p[2] if len(p) > 2 else 0
            vals += [p[1] - e, p[1] + e]
    lo, hi = min(vals), max(vals)
    zero = spec.get("yZero", True)
    if zero:
        lo = min(0, lo)
    pad = (hi - lo) * 0.08 or 1
    ticks, y0, y1 = nice_ticks(lo if zero and lo >= 0 else lo - pad,
                               hi + pad, clamp_zero=zero)

    def ypx(v):
        return mt + ph - (v - y0) / (y1 - y0) * ph

    # ---- X: categorical (bar) or numeric (line / scatter) ----
    cats = spec["x"].get("categories")
    if cats:
        n = len(cats)
        band = pw / n

        def xpx(i):
            return ml + band * (i + 0.5)
    else:
        xs = [p[0] for s in series for p in s["points"]]
        xlo, xhi = min(xs), max(xs)
        if xhi == xlo:
            xhi = xlo + 1

        def xpx(v):
            return ml + (v - xlo) / (xhi - xlo) * pw

    o = []
    a = o.append

    # ---- Gridlines and Y ticks ----
    for t in ticks:
        y = ypx(t)
        a('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--border)" '
          'stroke-width="1" stroke-dasharray="3 4"/>' % (ml, y, ml + pw, y))
        a('<text class="%s" x="%.1f" y="%.1f" text-anchor="end">%s</text>'
          % (V["cls_tick"], ml - 8, y + 4, esc(fmt(t))))

    # ---- Axis lines ----
    a('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--border-strong)" '
      'stroke-width="1.5"/>' % (ml, mt, ml, mt + ph))
    a('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--border-strong)" '
      'stroke-width="1.5"/>' % (ml, mt + ph, ml + pw, mt + ph))

    # ---- Axis labels (unit included, required) ----
    ylab = "%s (%s)" % (spec["y"]["label"], spec["y"]["unit"])
    a('<text class="%s" transform="translate(%.1f,%.1f) rotate(-90)" '
      'text-anchor="middle">%s</text>'
      % (V["cls_axis"], 14 if narrow else 16, mt + ph / 2, esc(ylab)))
    xlab = spec["x"]["label"]
    if spec["x"].get("unit"):
        xlab += " (%s)" % spec["x"]["unit"]
    a('<text class="%s" x="%.1f" y="%.1f" text-anchor="middle">%s</text>'
      % (V["cls_axis"], ml + pw / 2, H - (mb - 46 if narrow else mb - 40), esc(xlab)))

    # ---- Data ----
    if kind == "bar" and cats:
        ns = len(series)
        gw = band * 0.72
        bw = gw / ns
        for si, s in enumerate(series):
            col = SERIES_TOKENS[si % len(SERIES_TOKENS)]
            for i, p in enumerate(s["points"]):
                x = ml + band * i + (band - gw) / 2 + bw * si
                y = ypx(p[1])
                h = mt + ph - y
                a('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="2" '
                  'fill="var(%s)" fill-opacity=".78" stroke="var(%s)" stroke-width="1.2"/>'
                  % (x, y, bw * .88, max(h, 0.5), col, col))
                if len(p) > 2 and p[2]:
                    cx = x + bw * .44
                    a('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--text)" '
                      'stroke-width="1.2"/>' % (cx, ypx(p[1] - p[2]), cx, ypx(p[1] + p[2])))
                    for yy in (ypx(p[1] - p[2]), ypx(p[1] + p[2])):
                        a('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--text)" '
                          'stroke-width="1.2"/>' % (cx - 3.5, yy, cx + 3.5, yy))
    else:
        for si, s in enumerate(series):
            col = SERIES_TOKENS[si % len(SERIES_TOKENS)]
            mk = MARKERS[si % len(MARKERS)]
            pts = s["points"]
            if kind != "scatter":
                d = " ".join(
                    "%s%.1f %.1f" % ("M" if k == 0 else "L",
                                     xpx(p[0] if not cats else k), ypx(p[1]))
                    for k, p in enumerate(pts))
                a('<path d="%s" fill="none" stroke="var(%s)" stroke-width="%s" '
                  'stroke-linejoin="round"/>' % (d, col, 2.6 if narrow else 2))
            for k, p in enumerate(pts):
                cx = xpx(p[0] if not cats else k)
                cy = ypx(p[1])
                if len(p) > 2 and p[2]:
                    a('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(%s)" '
                      'stroke-width="1.2"/>' % (cx, ypx(p[1] - p[2]), cx, ypx(p[1] + p[2]), col))
                    for yy in (ypx(p[1] - p[2]), ypx(p[1] + p[2])):
                        a('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(%s)" '
                          'stroke-width="1.2"/>' % (cx - 3.5, yy, cx + 3.5, yy, col))
                a(marker(mk, cx, cy, r, col))

    # ---- X ticks ----
    if cats:
        rot = narrow or max(len(str(c)) for c in cats) > 6
        for i, c in enumerate(cats):
            x, y = xpx(i), mt + ph + (14 if not rot else 12)
            if rot:
                a('<text class="%s" transform="translate(%.1f,%.1f) rotate(-38)" '
                  'text-anchor="end">%s</text>' % (V["cls_tick"], x, y + 4, esc(c)))
            else:
                a('<text class="%s" x="%.1f" y="%.1f" text-anchor="middle">%s</text>'
                  % (V["cls_tick"], x, y + 4, esc(c)))
    else:
        xt, _, _ = nice_ticks(xlo, xhi, 5 if not narrow else 3)
        for t in xt:
            if t < xlo or t > xhi:
                continue
            a('<text class="%s" x="%.1f" y="%.1f" text-anchor="middle">%s</text>'
              % (V["cls_tick"], xpx(t), mt + ph + 18, esc(fmt(t))))

    body = "\n        ".join(o)
    # --fig-vb must be emitted by the generator. There's no build step to inject it afterwards,
    # and if it's missing, max-width fails to apply: the chart gets enlarged to the container
    # width, and the font size grows proportionally along with it.
    return ('<svg class="%s" viewBox="0 0 %d %d" style="--fig-vb:%dpx" '
            'role="img" aria-label="%s">\n        %s\n      </svg>'
            % (extra_class, W, H, W, esc(spec["title"]), body))


# --------------------------------------------------------------------------
# Data table (text-equivalent description) -- the chart's <details> must contain
# the raw data, not a prose description
# --------------------------------------------------------------------------
def build_table(spec):
    cats = spec["x"].get("categories")
    rows = []
    head = ["%s (%s)" % (spec["x"]["label"], spec["x"].get("unit") or "category")]
    for s in spec["series"]:
        head.append("%s (%s)" % (s["name"], spec["y"]["unit"]))
    n = max(len(s["points"]) for s in spec["series"])
    for i in range(n):
        r = [esc(cats[i]) if cats else esc(fmt(spec["series"][0]["points"][i][0]))]
        for s in spec["series"]:
            if i < len(s["points"]):
                p = s["points"][i]
                r.append("%s%s" % (fmt(p[1]),
                                   " ± %s" % fmt(p[2]) if len(p) > 2 and p[2] else ""))
            else:
                r.append("—")
        rows.append(r)
    th = "".join("<th>%s</th>" % esc(h) for h in head)
    tb = "".join("<tr>%s</tr>" % "".join(
        "<td data-label=\"%s\">%s</td>" % (esc(head[j]), c) for j, c in enumerate(r))
        for r in rows)
    return ('<div class="matrix"><table><thead><tr>%s</tr></thead>'
            '<tbody>%s</tbody></table></div>' % (th, tb))


# --------------------------------------------------------------------------
# Complete figure
# --------------------------------------------------------------------------
def render_chart(spec):
    for k in ("figNum", "title", "x", "y", "series", "method", "source"):
        if k not in spec:
            raise SystemExit("[chart] Missing required field: %s (see references/data-viz-and-math.md)" % k)
    if "unit" not in spec["y"]:
        raise SystemExit("[chart] Y axis must have a unit specified")

    legend = []
    for si, s in enumerate(spec["series"]):
        col = SERIES_TOKENS[si % len(SERIES_TOKENS)]
        legend.append('<i style="color:var(%s)"><span class="sw" '
                      'style="background:var(%s)"></span>%s</i>'
                      % (col, col, esc(s["name"])))
    if any(len(p) > 2 and p[2] for s in spec["series"] for p in s["points"]):
        legend.append('<i style="color:var(--text-muted)">error bars = %s</i>'
                      % esc(spec.get("errorMeaning", "not declared (must be filled in)")))

    ns = spec.get("n")
    nnote = ("sample size n = %s." % esc(ns)) if ns else ""
    baseline = "" if spec.get("yZero", True) else \
        "<strong>Note: the Y axis does not start at 0</strong>, so the visual gap is larger than the actual gap."

    return """  <figure data-chart="1">
    <div class="fig-head">
      <span class="fig-num">Figure %s</span>
      <span class="fig-title">%s</span>
    </div>
    <div class="fig-frame">
      %s
      %s
      <div class="legend">%s</div>
    </div>
    <figcaption>
      %s%s
      <p class="chart-method">Method: %s</p>
      <details>
        <summary>Expand raw data</summary>
        %s
        <p class="src">Source: %s</p>
      </details>
    </figcaption>
  </figure>""" % (
        esc(spec["figNum"]), esc(spec["title"]),
        build_svg(spec, "wide", "only-wide"),
        build_svg(spec, "narrow", "only-narrow"),
        "".join(legend),
        nnote, baseline,
        esc(spec["method"]),
        build_table(spec),
        esc(spec["source"]))


if __name__ == "__main__":
    print(render_chart(json.load(open(sys.argv[1], encoding="utf-8"))))
