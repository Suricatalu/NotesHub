# Page Components

Skeleton `page-template.html` already contains all styles — this only covers **when to use them and how to fill them in**.

---

## 1. Page Skeleton Order

**Header and footer are fixed; the middle follows `main`.** The header and footer are the frame present on every page (readers build cross-page reading intuition from consistent ordering); the content in the middle follows the headings of the `main` markdown file, carried over as-is — do not add, remove, or reorder those headings, and keep their original hierarchy (the precise rules are under "One Main File = One Page" in SKILL.md). Note that a "section" in `www.conf` is a different thing entirely: a named group of pages.

| Page part | Required | Description |
|---|:--:|---|
| `h1` | ✔ | Taken from `main`'s H1; can be polished for readability, but must convey the same meaning |
| `.meta` | ✔ | Update date, reading time, **verified platform** |
| `.lede` | ✔ | Two or three sentences that clearly state what problem this page solves |
| `.callout.scope` | ✔ | Two side-by-side columns: in scope / out of scope |
| **Headings from `main`** | ✔ | **Order and hierarchy follow the original.** Transformation happens *under* each heading: turn a process into a diagram, turn a comparison into a matrix |
| Common pitfalls | | Only include if `main` explicitly says "I got stuck here"; for each pitfall: symptom → cause → fix |
| **Sources for this page** | ✔ | Contract Rule 2, cannot be omitted. The main file is marked `data-role="main"` |

This table used to list a fixed order — "concepts / implementation / failure & recovery / decision matrix" — a holdover from the era when pages were merged from multiple notes, when the headings were essentially invented by the LLM itself. Now the headings are determined by `main`: if `main` has no "failure & recovery" heading, don't fabricate one out of thin air; if it puts implementation before concepts, follow that order.

**Decision matrices, glossary terms, data charts, and common pitfalls are all "components under a heading"** — place them under the corresponding heading of `main`; don't create a new heading just to fit them in.

### "What's not covered" matters more than "what's covered"

The biggest harm in a technical article isn't getting something wrong — it's letting the reader assume something was covered when it wasn't. The right-hand column needs at least three items, and they must be specific — "auth not covered" isn't enough; write "token refresh and session revocation not covered (see another page)".

If the source material doesn't mention something, this is the first place to put it.

### The "Verified Platform" Field

Must state the actual environment and versions the notes were validated against — whatever "platform" means in your domain (`Postgres 16 · Debian 12`, `i.MX8MP EVK · Scarthgap`, `Node 22 · AWS Lambda`).
Configuration values are rarely as portable as they look — without this field, readers have no way to judge whether a setting can be copied as-is.

---

## 2. Sources for This Page (Contract Rule 2)

```html
<section class="sources" id="sources">
  <h2>Sources for This Page</h2>
  <p>This page's heading structure is inherited from the "primary source" note; reference materials
     are only used for verification, supplementing terminology, and sourcing values.
     The content has been reorganized and visualized — it is not a verbatim copy of the original.</p>
  <ul class="srclist">
    <li id="src-1" data-role="main">
      <span class="srcbadge">Primary Source</span>
      <a href="../../../notes/auth/overview.md"
         target="_blank" rel="noopener">notes/auth/overview.md</a>
      <span class="srcnote">This page is the visualized version of this note</span>
    </li>
    <li id="src-2" data-role="ref">
      <span class="srcbadge">Reference</span>
      <a href="../../../notes/storage/sessions.md"
         target="_blank" rel="noopener">notes/storage/sessions.md</a>
      <span class="srcnote">The token lifetimes under "Session expiry" are sourced from here</span>
    </li>
  </ul>
</section>
```

Key points:

- **The main file must have exactly one `data-role="main"` entry, listed first.** This is Contract Rule 2, and `[O]` will block it: missing it, or having two, both FAIL. Each page maps to exactly one `main`; marking two means this page has merged two markdown files.
- **The `main` given by `plan` must be marked `data-role="main"`; `refs` are marked `data-role="ref"`.** The two roles are completely different — don't mix them up.
- **Relative paths are computed from the HTML file itself.** The output lands in `www/pages/<section>/<filename>.html`; to link to `notes/foo.md` the path is `../../../notes/foo.md`. `[O]` actually checks against the filesystem, so a wrong path will always be caught.
- **The link text should be the repo-relative path** (`notes/...`), so readers immediately know where the file is.
- **`srcnote` should describe what part of this page that note provided** — not just repeat the filename. References must state specifically "which part of this page it's used in"; if you can't state that, it means it isn't actually being used — don't list it.
- **Every `<li>` needs `id="src-N"`**, so inline citation markers can point to it.
- **The main file must always be listed; `refs` should only list the ones actually cited** — don't pad the list with unused references. Content researched online should also be listed (with the link text being the URL), and the body text should clearly indicate it's not from a repo note.

### Inline Source Citations

```html
Read from BootROM baked into the chip<sup class="cite"><a href="#src-1">1</a></sup>.
```

Attach it after a **factual claim**, so the reader knows which note the statement comes from. The number corresponds to `src-N`. Hovering or clicking jumps to the source list and highlights it.

Should be cited: specific values, default settings, variable names, "this mechanism behaves as...".
Should not be cited: judgments and recommendations (those are the transformer's opinion, not facts from the note).

---

## 3. Glossary Terms

### When to Use

All three conditions must be met:

1. Readers can't continue reading without understanding it
2. It appears 1–3 times on the page — not enough to warrant its own heading
3. Other pages will also use it

Core concepts that appear many times **should not** be turned into glossary terms — those should be properly explained in the body text, or given their own page.

### How to Write It

```html
<button class="term" type="button" data-term="idempotency">idempotent<span class="q" aria-hidden="true">?</span></button>
```

- Must be a `<button>` (`[J]` will block it) for keyboard accessibility
- Only mark the **first occurrence**
- The displayed text can differ from `data-term` (the markup says "eventually consistent", the entry is `eventual-consistency`)

### Where the Definition Lives

Definitions are **maintained only in `assets/glossary.json`**. Because each page is a self-contained single file, you must **copy** the entries you need into that page's `<script type="application/json" id="glossary-data">` — but do not write a separate definition within the page itself, otherwise the same term will read differently across different pages.

Each entry needs `term` / `def` / `why` / `source`. `source` is required (`[J]` will block it) — either a path to a note in this repo, or the spec / manual / paper the definition came from.

`why` is what distinguishes a glossary term from Wikipedia. If it's just a definition, the reader can look it up themselves; what you should write is "what aspect of this you need to know, in this context".

**A single-file page should only include the entries it actually uses.** Including everything would add tens of KB to every page, and `[J]` will warn about it.

---

## 4. Decision Matrix

```html
<div class="matrix">
  <table>
    <thead><tr><th>Approach</th><th>Prerequisite</th><th>Ongoing Cost</th><th>Suitable Scenario</th></tr></thead>
    <tbody>
      <tr>
        <td data-label="Approach">Signed artifacts verified at deploy time</td>
        <td data-label="Prerequisite">A key store the CI runner can reach</td>
        <td data-label="Ongoing Cost">Self-managed PKI; rotating the key means redeploying every consumer</td>
        <td data-label="Suitable Scenario">Default choice when artifacts cross a trust boundary</td>
      </tr>
    </tbody>
  </table>
</div>
```

**Every `<td>` must have `data-label`** — below 780px the table becomes cards, and this is what displays the column name.

Suggested columns: hardware prerequisites, key/state management cost, integration difficulty with existing toolchains, **scenarios where it doesn't apply** (more valuable than "suitable scenario").

---

## 5. Common Pitfalls

```html
<div class="pit">
  <h4>Pitfall 1 · One-line symptom</h4>
  <p>Why it happens (the mechanism-level cause, not "forgot to configure it")</p>
  <p class="fix">Fix: specific command or setting + <strong>how to verify it's fixed</strong></p>
</div>
```

"How to verify it's fixed" cannot be omitted. If you don't know whether the fix took effect, it's as good as not fixed.

Pitfalls are usually hidden in complaint-like sentences in the markdown ("I got stuck here", "later I realized") — actively dig for them during transformation.

---

## 6. Code Blocks

```html
<div class="code">
  <div class="bar"><span>config/deploy.conf</span><span>ini</span></div>
<pre><code><span class="c-cm"># comment</span>
<span class="c-var">VERIFY_SIGNATURES</span> = <span class="c-str">"1"</span>
</code></pre>
</div>
```

- `.bar` has the **file path** on the left (readers need to know where to paste it), and the language on the right
- Only three semantic classes: `.c-cm` comment, `.c-var` variable, `.c-str` string. Don't introduce a syntax highlighting library — that would violate the offline contract
- Only paste the necessary lines. Nobody wants to read an entire `.config` file pasted in full

---

## 7. Callouts

| class | Purpose |
|---|---|
| `.callout.scope` | Scope, one per page, fixed position |
| `.callout.warn` | The single easiest thing to get wrong, at most one or two per page |
| `.callout` (no modifier) | Supplementary notes |

Overusing `.warn` makes it lose its warning effect. Only use it for something at the level of "getting this wrong breaks the entire mechanism".

---

## 8. Theme and iframe

The skeleton's JS already handles this — don't modify it, but you need to know its behavior:

- **Opened standalone**: follows the system `prefers-color-scheme`, with a toggle button in the top-right corner
- **Inside an iframe**: the toggle button is hidden, controlled uniformly by the outer shell. When the page loads it sends `{ type: 'nt-ready' }` to `window.top`; upon receiving it, the shell replies with `{ type: 'nt-theme', theme: 'dark' | 'light' }`
- **When inside an iframe, all external links automatically get `target="_blank"`** to avoid navigating the iframe away

The outer shell (the `index.html` generated by `www.py nav`) needs to implement these two messages for the theme to stay consistent.
