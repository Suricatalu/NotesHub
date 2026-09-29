# Sizing Derivation

## The One Formula

```
Effective font size = SVG nominal font size × (container width ÷ viewBox width)
Lower bound = 9.5px
```

Every breakpoint number can be traced back to this. None of them were picked by feel.

## Key Premise: The Page Lives Inside an iframe

`www/index.html` has a menu on the left, and an iframe loading the page on the right. **The iframe has its own viewport**, so media queries correctly respond to the iframe's width — but that width is not the browser window's width.

This is the biggest difference between this site and a typical website, and the reason the size ceiling is smaller than usual numbers.

## How Container Width Is Calculated

```
Container = iframe width − gutters on both sides − figure frame padding (− in-page TOC)
```

`gutter = clamp(16px, 4vw, 40px)`; `.fig-frame` padding is 10px at ≤480px, otherwise 16px; the in-page TOC is 200px + 40px gap, and only appears when the iframe is ≥ 1100px.

| iframe width | gutter×2 | padding×2 | TOC | container |
|---|---|---|---|---|
| 320 | 32 | 20 | — | **268** |
| 390 | 32 | 20 | — | 338 |
| 768 | 61 | 32 | — | 675 |
| 880 | 70 | 32 | — | 778 |
| 1100 | 80 | 32 | 240 | **748** |
| 1440 | 80 | 32 | 240 | 848 (limited to 828 by max-width 1180) |

The two bold values are the decision points. Note that **1100 is more constrained than 880** — the moment the in-page TOC appears, the content column actually gets narrower. So the ceiling for wide-variant diagrams is determined by 748, not by the largest window size.

## Why the In-Page TOC Breakpoint Is 1100

If set at 1000: the content column would only have 1000−80−240−32 = 648px left, compressing the wide diagram to 0.88×, turning a 10px font into 8.8px, falling below the lower bound.

If set at 1280: the range from 1100 to 1280 would waste available space, and that's exactly the most common iframe width range on laptops.

**1100 is the minimum value at which a 740-wide diagram still fits.** The layout serves the diagram, not the other way around.

## Three Sizing Strategies

### A. Scrolling 1:1 (viewBox ≤ 740)

```html
<div class="fig-frame fig-scroll">
  <svg viewBox="0 0 740 400" style="--fig-vb:740px" role="img" aria-label="...">
```

```css
.fig-scroll > svg { min-width: var(--fig-vb); }   /* never shrinks */
.fig-frame  svg   { max-width: var(--fig-vb); }   /* never grows */
```

Both min and max equal the viewBox width → always exactly 1:1, font size is WYSIWYG. If it doesn't fit, it scrolls horizontally, and add `<p class="scroll-hint">← On a narrow screen this diagram can be scrolled horizontally →</p>`.

**Scrolling beats scaling.** Readers can scroll, but they can't read a 4px font clearly no matter what. A single SVG with nothing to maintain — this strategy is sufficient for most diagrams.

#### ⚠️ The canvas width ceiling for the scrolling type is 740, not 900

These two numbers govern different things, and mixing them up produces diagrams that "pass every check, yet still scroll sideways on a desktop":

| Number | What it guarantees | What it does not guarantee |
|---|---|---|
| **900** | The font size won't break (scrolling 1:1 never scales down anyway) | **It does not guarantee the diagram fits** |
| **740** | **No scrolling is needed** at the most common laptop widths | — |

The derivation comes straight from the container table above: **at the breakpoint where the in-page table of contents appears (iframe 1100), the container is only 748**, so any diagram with `viewBox > 740` starts scrolling horizontally at exactly that width — which is the most common laptop range. The `> 900` line is only the boundary for "scrolling can no longer save it, dual variants are mandatory"; it is not a recommended value.

**Set the canvas width to 740 before you start drawing**, rather than drawing first and then checking whether it fits.

#### What to do when you exceed 740

Try these in order, and **do not skip ahead to dual variants**:

1. **Change the drawing direction** — side-by-side becomes stacked; 4 columns become 2 × 2; a left-right comparison becomes a top-bottom one. Most over-wide diagrams are over-wide because of the habit of drawing left to right, not because there is genuinely that much information.
2. **Lower the information density** — fold secondary fields into the main box as a single line; move explanatory text into the `figcaption`; don't state the same thing once on the diagram and again in the legend.
3. **Split it into two diagrams** — if steps 1 and 2 can't bring it down, that usually means the diagram was mixing two kinds of relationship to begin with (see "A diagram may carry only one edge semantic" in `diagrams.md`). Once split, both halves get narrower on their own.
4. Only if none of the above works, use dual variants (Strategy B).

**You may not shrink the font size to buy width.** The 9.5px floor is an accessibility limit, not a tunable parameter — `.t-mono` at 10.5px and `.t-tag` at 10px are already sitting right on it, with no room to go lower.

#### Common mistake: assuming "the desktop is wide enough, so it's fine"

At the widest viewport (iframe 1440) the container is 828, which makes an 880-wide diagram look like it's only slightly over. But **container width does not increase monotonically with viewport width** — at the 1100 breakpoint the in-page table of contents appears, and the container actually drops from 778 to 748. What looks like a perfect fit on your own large monitor will scroll on the reader's laptop.

### B. Dual Variant (viewBox > 900)

Use the narrow version for `iframe < 880px`, the wide version for `≥ 880px`:

```html
<svg class="only-wide"   viewBox="0 0 740 400" style="--fig-vb:740px" ...>
<svg class="only-narrow" viewBox="0 0 340 900" style="--fig-vb:340px" ...>
```

The two versions differ not just in orientation — **the font sizes differ too**:

| | Wide | Narrow |
|---|---|---|
| Title | `.t-title` 14px | `.n-title` 18px |
| Role | `.t-role` 11px | `.n-role` 14px |
| Monospace | `.t-mono` 10.5px | `.n-mono` 13px |

The narrow variant's container is only 268px while the viewBox is 340, giving a 0.79 scale factor, so the nominal font size has to be enlarged to compensate.

**Verification**

- Wide: `10 × (748 ÷ 740) → scale capped at 1.0` → 10.0px ✓
- Narrow: `13 × (268 ÷ 340) = 10.2px` ✓
- If the wide version used 812: `10 × (748 ÷ 812) = 9.2px` ✗ ← this is why the ceiling is 740

The narrow variant isn't just turning horizontal into vertical — **information density needs to be rearranged**: the wide version places key material in a separate box above the stage, the narrow version should fold it into the stage box as a single line.

### B-2. Between 740 and 900 (not recommended, but not forbidden)

When `viewBox` lands in 741–900 you can still use the scrolling type and the font size will be fine, but **it will scroll horizontally on a desktop**. Only do this when all three width-reduction measures above have been tried *and* scrolling genuinely doesn't hurt comprehension — for example a purely linear timeline, which readers were going to read left to right anyway. `[E]` emits a **WARN** (not a FAIL) for this range, as a reminder to go back and check you weren't just taking the easy way out.

### C. Fully Responsive at All Breakpoints (viewBox ≤ 420 and font size large enough)

A single SVG without `fig-scroll`. Verify that `smallest nominal font size × (268 ÷ viewBox width) ≥ 9.5`; at a width of 420 this requires a minimum font size of ≥ 14.9px. Most diagrams can't achieve this, so in practice even 420-wide diagrams use Strategy A.

## CSS Specificity Trap

The dual-variant hiding rule must be:

```css
.fig-frame svg.only-narrow { display: block; }   /* 0,2,1 ✓ */
```

Not:

```css
.only-narrow { display: none; }                  /* 0,1,0 ✗ */
```

Because `.fig-frame svg { display: block; }` has a specificity of (0,1,1), which will override a single class selector. **Specificity outranks source order, and also outranks media queries.**

Failure symptom: both variants render simultaneously, the narrow variant gets stretched to full width by `width:100%`, and the font size scales up more than double. No error message at all. The skeleton already has this right — don't change it; `[I]` will block it.

## Body Text RWD

- Line width capped at `68ch` (`--measure`)
- All font sizes use `clamp()` for fluid scaling, no breakpoint jumps
- Tables convert to cards at ≤780px, `<td>` must have `data-label`
- Glossary terms convert to a bottom drawer at ≤560px; anchored tooltips would inevitably get clipped on small screens

## After Making Changes

```bash
python3 .claude/skills/notes-to-html/scripts/validate_page.py www/pages/**/*.html
```

`[D]` checks whether `--fig-vb` matches the viewBox, `[E]` checks the worst-case effective font size, `[I]` checks variant switching. All three must pass.
