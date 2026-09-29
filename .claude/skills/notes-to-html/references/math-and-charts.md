# Math Formulas and Data Charts

Both share the same constraint: **offline, single-file, no external resources**. This rules out KaTeX, MathJax, Chart.js, Plotly, D3, and mermaid — they either require bundled font files or a CDN.

---

# Part 1: Math Formulas (MathML)

## Why MathML

Native browser support (Chromium 109+, full support in Firefox and Safari), zero JS, zero font files, and screen-reader accessible. It's the only option that satisfies both the offline and single-file requirements.

`[M]` will block KaTeX / MathJax.

## Display Formula Structure

```html
<div class="math-block" id="eq-1">
  <div class="math-scroll">
    <math xmlns="http://www.w3.org/1998/Math/MathML" display="block">
      ...
    </math>
  </div>
  <div class="eqno">(1)</div>
</div>
```

All three components are required:

| Component | Why |
|---|---|
| `id="eq-N"` | So the body text can say "see equation (1)" |
| Wrapped in `.math-scroll` | **A long formula in a narrow iframe will stretch the whole page wide**, distorting every paragraph along with it. MathML doesn't wrap automatically |
| `xmlns` attribute | Without it, some browsers won't render it |

Inline formulas use `<span class="math-inline"><math xmlns="...">…</math></span>`.

## Common Syntax Quick Reference

### Fraction `S/B`

```xml
<mfrac><mi>S</mi><mi>B</mi></mfrac>
```

### Subscript / Superscript

```xml
<msub><mi>S</mi><mtext>hash</mtext></msub>
<msup><mi>k</mi><mi>i</mi></msup>
<msubsup><mi>x</mi><mn>0</mn><mn>2</mn></msubsup>
```

### Logarithm (subscript form)

```xml
<msub><mi>log</mi><mi>k</mi></msub><mo>&#x2061;</mo>
```

`&#x2061;` is function application, letting the layout engine know the argument follows `log`.

### Ceiling / Floor

```xml
<mo stretchy="true">&#x2308;</mo> … <mo stretchy="true">&#x2309;</mo>   <!-- ⌈ ⌉ -->
<mo stretchy="true">&#x230A;</mo> … <mo stretchy="true">&#x230B;</mo>   <!-- ⌊ ⌋ -->
```

### Summation

```xml
<munderover>
  <mo>&#x2211;</mo>
  <mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow>
  <mi>L</mi>
</munderover>
```

### Root

```xml
<msqrt><mi>x</mi></msqrt>
<mroot><mi>x</mi><mn>3</mn></mroot>
```

### Common Symbol Entities

| Symbol | Entity | Symbol | Entity |
|---|---|---|---|
| ≈ | `&#x2248;` | ≤ | `&#x2264;` |
| ≥ | `&#x2265;` | ≠ | `&#x2260;` |
| × | `&#xD7;` | ÷ | `&#xF7;` |
| − | `&#x2212;` (minus sign, not a hyphen) | ± | `&#xB1;` |
| → | `&#x2192;` | ∈ | `&#x2208;` |
| α β θ | `&#x3B1; &#x3B2; &#x3B8;` | ∞ | `&#x221E;` |

### Spacing

```xml
<mspace width="1.4em"/>
```

### Complete Example

```xml
<math xmlns="http://www.w3.org/1998/Math/MathML" display="block">
  <mi>L</mi><mo>=</mo>
  <mrow>
    <mo stretchy="true">&#x2308;</mo>
    <msub><mi>log</mi><mi>k</mi></msub><mo>&#x2061;</mo>
    <mo stretchy="true">(</mo><mfrac><mi>S</mi><mi>B</mi></mfrac><mo stretchy="true">)</mo>
    <mo stretchy="true">&#x2309;</mo>
  </mrow>
</math>
```

Typesetting convention: variables use `<mi>`, numbers use `<mn>`, operators use `<mo>`, plain-text subscripts use `<mtext>`. Getting this wrong won't break anything, but the italics and spacing will be off.

## Symbol Table Is Required

Every heading containing display formulas must have a `.symtab` (`[M]` will block otherwise):

```html
<div class="symtab">
  <table>
    <thead><tr><th>Symbol</th><th>Meaning</th><th>Unit</th><th>Value in This Example</th></tr></thead>
    <tbody>
      <tr><td data-label="Symbol">S</td><td data-label="Meaning">Size of the protected data region</td>
          <td data-label="Unit">byte</td><td data-label="Value in This Example">512 MiB</td></tr>
    </tbody>
  </table>
</div>
```

**The "Value in This Example" column is the key one.** A purely symbolic formula requires readers to substitute numbers themselves before it feels real; giving a typical value lets them grasp the order of magnitude at a glance.
Remember to write `data-label` on `<td>`.

## Every Formula Needs a Plain-Language Explanation Afterward

Not restating the symbols, but conveying the meaning:

> Tree height grows **logarithmically** with data volume, so the difference between 512 MiB and 8 GiB is only one level.

Although MathML can be read aloud by screen readers, the read-aloud experience for complex formulas is still poor — this plain-language sentence is a genuine accessibility compensation.

## When to Use a Formula

- **Use it**: when there's a derivation, a relationship between variables, or a need to substitute different values
- **Don't use it**: for a fixed number or ratio (just write "about 4 MiB" directly)
- **Don't use it**: to dress up basic arithmetic to look more sophisticated

If a page has more than 4–5 display formulas, it's usually really two pages.

---

# Part 2: Data Charts

## Use make_chart.py, Don't Draw by Hand

```bash
python3 .claude/skills/notes-to-html/scripts/make_chart.py spec.json
```

Outputs a complete `<figure>`, including wide/narrow dual variants, legend, raw data table, and `--fig-vb`. Paste it directly into the page.

Why not draw by hand: axis ticks, error bars, and font-size differences between the two variants are all easy to get wrong, and the generator forces you to fill in the required fields.

## Spec Format

```json
{
  "figNum": "4",
  "type": "bar",
  "title": "Request latency cost of each stage with signature verification enabled",
  "x": { "label": "Pipeline Stage", "categories": ["parse", "verify", "to response"] },
  "y": { "label": "Duration", "unit": "ms" },
  "yZero": true,
  "n": "20 runs per group",
  "errorMeaning": "±1 standard deviation",
  "method": "4 vCPU container, warm cache, 25 concurrent clients, measured with the built-in tracer",
  "source": "notes/perf/bench.md (measured in-house, not independently reproduced by a third party)",
  "series": [
    { "name": "Disabled", "points": [["a", 0, 0], ["b", 0, 0], ["c", 2180, 41]] },
    { "name": "Enabled",   "points": [["a", 38, 3], ["b", 121, 7], ["c", 2451, 58]] }
  ]
}
```

The third element of `points` is the error value, and it can be omitted. `type` supports `line` / `bar` / `scatter`.
`figNum` / `title` / `x` / `y` / `method` / `source` are required, `y.unit` is required — missing any of these fails immediately.

## Required Checklist

- [ ] Both axes have a **name and unit** (a number without a unit is meaningless)
- [ ] **Sample size n**, and how n was calculated (per group? total?)
- [ ] What the error bars represent (standard deviation? standard error? range? 95% CI?) — not stating this is the same as not drawing them
- [ ] **Measurement method**: hardware, software versions, environmental conditions, warm vs. cold start
- [ ] Data source, pointing to an md file within the repo
- [ ] Whether the Y axis starts at 0

## Y-Axis Truncation

`yZero: false` automatically appends "Note: Y axis does not start at 0, visual difference is larger than the actual difference" to the caption.

**Default to true always.** Only turn it off when the data's range of variation is far smaller than its absolute value (temperature, voltage), and even then you must explain why in the text. Truncating the Y axis is the most common way to mislead, even unintentionally.

## Colors and Shapes

Series colors are assigned in order from `--dg-data` → `--dg-verified` → `--dg-key` → `--dg-hw` → `--dg-fail` → `--dg-neutral`, and each series is also paired with a **differently shaped marker** (circle, square, triangle, diamond, X, cross).

Series should be distinguishable without relying on color — this is essential for readers with color vision deficiencies and for black-and-white printing.

## When Not to Draw a Chart

- Only two or three numbers → write them in the sentence
- Data is categorical rather than quantitative → use a table
- You want to express "is there a difference" rather than "how much difference" → one sentence plus a confidence interval
