# Diagram Prototype Catalog

Technical diagrams fall into these 9 prototypes about 80% of the time. The worked examples below lean on systems and infrastructure work because that is where they were first written down, but the shapes are domain-neutral — a certificate chain, a CI promotion chain and a secure-boot chain are all Prototype 1. **Each time you draw a diagram, first pick a prototype, then fill in the required checklist item by item.**

The required checklist isn't a formatting check — it's a content check. If you can't fill in an item, it usually means you haven't actually understood that part yet — go back and check the source material; don't leave the cell blank.

---

## Common Rules (apply to all prototypes)

### ⭐ A Diagram May Carry Only One Edge Semantic

Before drawing, write out in **one sentence**:

```
The arrows in this diagram mean ______________
```

**If you can't write a single sentence, the diagram should be split in two.** This is the most common failure mode, and the hardest to spot yourself: the boxes are drawn beautifully and every arrow is a solid line, but one of them means "A produces B", another means "you copy B into C by hand", and a third means "the build picks C up at build time". Faced with three identical arrows, readers can only guess.

When a second kind of relationship genuinely must appear in the same diagram, **do both of these — neither one alone is enough**:

1. Change the line style (the second semantic is always dashed)
2. Spell out in the legend what each of the two means

A concrete way this goes wrong: three different relationships all drawn as solid arrows, and the reader concludes "the output = the union of those two sources" — when in fact several of the output's parts come from somewhere that isn't on the diagram at all. **The diagram ends up contradicting its own prose.** The fix is to split it into two diagrams (for instance, "runtime connection direction" and "file provenance map").

### The First Legend Item Must Be the Edge Semantic

`.legend` is not only for explaining colors. The order is fixed:

```html
<div class="legend">
  <i style="color:var(--dg-neutral)"><span class="sw"></span>Solid arrow = "this file is copied from / produced by"</i>
  <i style="color:var(--dg-verified)"><span class="sw"></span>Dashed arrow = "packaged at build time" (a different kind of relationship)</i>
  <i style="color:var(--dg-data)"><span class="sw"></span>…color meanings come after…</i>
</div>
```

Diagrams with no arrows (pure stacks, pure layouts, pure address spaces) obviously don't need this — no edges, no edge semantics. `[L]` only requires it when `marker-end` appears in the SVG — if there are arrows it is **mandatory, no exceptions, and it is a FAIL**. But it only checks *that* something was written, not whether it was written *correctly*, and it **cannot stop you from expressing a relationship with a line that has no arrowhead**. It is a floor, not a guarantee.

By contrast `[E]`'s width check is only a **WARN**, because that one has a legitimate exception (see Strategy B-2 in `rwd.md`): wrapping a single continuous long string would destroy the very thing the diagram is trying to show, so keeping such a diagram above 740 is correct — but the reason must be stated in the `figcaption`.

### Visual Vocabulary (fixed site-wide, must not be reinvented per article)

| Element | Meaning |
|---|---|
| Sharp-cornered thick frame (`stroke-width:2.5`, `rx=0`) | Immutable / trust anchor (hardware, a burned-in value, an offline root key) |
| Rounded frame (`rx=9`) | Mutable stage / writable component |
| Diamond | Decision point |
| Rounded capsule (`rx=20`) | Start/end state |
| Dashed frame | Out of scope, unverified, or fallback not enabled |
| **Solid arrow** | The **one** primary relationship this diagram declares (control transfer, data flow, provenance…) |
| **Dashed arrow** | The relationship **of a different nature** from the primary one (provides basis for, verification, retry, different timing) |
| Circled ✓ on a line | This handoff has been verified |
| Red dashed line | Failure path |

### Semantic Colors (use tokens only, never hardcode hex codes)

| Token | Purpose |
|---|---|
| `--dg-hw` | Immutable, root of trust, anything that cannot be changed after the fact |
| `--dg-verified` | Stage that has passed verification, success path |
| `--dg-key` | Keys, hashes, signature material, decision points |
| `--dg-fail` | Failure, rejection, rollback |
| `--dg-data` | Data, storage blocks, runtime verification |
| `--dg-neutral` | Unverified, out of scope, to be filled in |

### Small Text Inside an SVG Is "Body Text", Not Decorative Text

`.t-mono` at 10.5px and `.t-tag` at 10px are both far below WCAG's large-text threshold (24px, or 18.66px bold), so **the contrast requirement is 4.5:1, not 3:1**. And they sit on **`--dg-surface`** (the diagram frame background), not on `--bg` — the two have different luminance, so checking only against `--bg` misses diagrams entirely.

This is not hypothetical: a `--text-faint` value that passed against `--bg` measured under 4:1 on the diagram frame background, failing AA in **both themes across all four background colors**, and `[G]` let it through the whole time because it only required 3.0:1 for `--text-faint` (treating it as decorative text). The threshold and the background-color combinations in `[G]` have since been filled in.

**Don't darken text below AA for the sake of "visual hierarchy".** Hierarchy comes from the relative relationship between the three levels `--text` / `--text-muted` / `--text-faint`, and all three must meet the bar on their own.

### Every Diagram Must Have

- Figure number + one-sentence title (`.fig-head`)
- HTML legend (`.legend`, must be HTML so it can wrap automatically)
- `figcaption` pointing out **the part of this diagram most likely to be misread** (not restating text already on the diagram)
- `<details>` text-equivalent description: for accessibility, searchability, and copy-quotability
- `aria-label`
- Explicitly state **what is not covered**

---

## Prototype 1 · Chain of Trust / Stage Handoff Diagram

Used for: any chain where each stage's legitimacy rests on the previous stage having checked it — certificate chains, OAuth token exchange, signed artifacts promoted through CI stages, secure boot and attestation

**Required Checklist**

- [ ] What the starting point is, and why an attacker can't alter it (name the mechanism that makes it immutable: a burned-in fuse, an offline root key, a hardware module)
- [ ] Each stage's name + role + **the artifact it hands on** (a filename, an image digest, a token)
- [ ] **What key material** each stage uses to verify the next stage, and **where that material lives**
- [ ] Who verifies whom (arrow direction must not be ambiguous)
- [ ] Whether each handoff is actually verified (state explicitly if it isn't)
- [ ] What happens if verification fails (halt? retry? fall back?)
- [ ] The boundary between one-time verification and continuous runtime verification
- [ ] What this diagram does not cover

**Common Omission**: Only drawing "A → B → C" without showing where the keys come from — readers can't judge the actual strength of this chain.

---

## Prototype 2 · Layer Stack Diagram

Used for: any stack where an upper layer overrides or depends on a lower one — configuration precedence (defaults → file → env → flags), middleware and plugin chains, framework over runtime over OS, privilege rings, build-system layer stacking

**Required Checklist**

- [ ] The **owner** of each layer (upstream project / vendor / in-house)
- [ ] Whether the relationship between layers is **override** or **dependency** — the two behave nothing alike and are constantly confused
- [ ] Priority direction: which layer wins when two of them set the same thing
- [ ] Which layers can be modified, and which layers, if touched, block future upgrades
- [ ] Where the privilege or trust boundary sits, if the stack has one
- [ ] Version / compatibility constraints between layers

**Common Omission**: Drawing it as a plain stack without marking the "override direction" — readers can't tell who wins in a conflict.

---

## Prototype 3 · Storage Layout Diagram

Used for: anything where one fixed extent is carved up and each part plays by different rules — disk partitioning, A/B slots, the internal structure of a binary file format, an encrypted container, a database's tablespaces

**Required Checklist**

- [ ] Addresses, offsets or sizes (use actual numbers, not just "before"/"after")
- [ ] The format of each block, and which component reads it
- [ ] Writable vs. read-only
- [ ] The **coverage boundary** of encryption/integrity protection (draw it as a box, clearly marking what's outside the box)
- [ ] Redundancy relationships (which copy is currently active)
- [ ] Regions that don't belong to the main scheme must still be drawn, and clearly labeled as not belonging to it
- [ ] Which blocks get overwritten during an update

**Common Omission**: Conflating "signed" with "encrypted". These two things usually have different coverage — draw them separately.

---

## Prototype 4 · State Machine

Used for: update and rollback flows, retry and circuit-breaker logic, job / session / order lifecycles, service unit states, any policy driven by a counter

**Required Checklist**

- [ ] The initial state and all terminal states
- [ ] The **trigger condition** for each transition (not just "success/failure" — state who makes the determination)
- [ ] Counters and their limits (specific numbers, e.g. retry limit = 3)
- [ ] Who resets the counter, and when
- [ ] Dead ends (states you can enter but never leave) must be explicitly drawn, not just implied by the absence of an arrow
- [ ] What happens if the process dies mid-transition (power loss, crash, deploy)

**Common Omission**: Only drawing the happy path plus one failure branch, without drawing "retry limit exhausted" and "both sides failed".

---

## Prototype 5 · Sequence Diagram

Used for: authentication handshakes, request/response protocols, distributed transactions, download-and-apply flows, IPC

**Required Checklist**

- [ ] All participants (including passive ones — a key store, a third-party server, a queue)
- [ ] A summary of message content, not just "request"
- [ ] Which steps require network access, which can work offline
- [ ] Timeout and retry behavior
- [ ] At which step state is persisted (the crash-safe point)
- [ ] Trust assumptions: what basis each participant has for trusting the other

---

## Prototype 6 · Build / Pipeline Flow Diagram

Used for: build task graphs, CI/CD pipelines, signing and release flows, data and ETL pipelines

**Required Checklist**

- [ ] Inputs (source, config, external keys and credentials)
- [ ] The name of each task or stage, as it actually appears in the tooling
- [ ] The actual path or identifier of each output
- [ ] Which steps run on the **build machine**, which on the **target environment**, and which inside a **secret store / HSM**
- [ ] Where caching short-circuits the graph — and therefore which steps can be silently skipped
- [ ] Which steps are non-reproducible (timestamps, random keys, network fetches)

**Common Omission**: Not distinguishing build-time from run-time, leaving readers unclear about when keys are exposed to whom.

---

## Prototype 7 · Decision Matrix

Used for: comparing approach options

**Required Checklist**

- [ ] The **prerequisites** for each approach (hardware, platform, licence, team skill)
- [ ] Ongoing operational cost (who owns it, how hard it is to reverse later)
- [ ] Integration difficulty with the existing toolchain
- [ ] Scenarios where it doesn't apply (more valuable than "suitable scenario")
- [ ] At least one citation per row
- [ ] Must become cards on mobile (`.matrix` already handles this; remember to write `data-label` on `<td>`)

---

## Prototype 8 · Address / Range Map

Used for: one flat space carved into named ranges — physical or virtual memory layout, reserved-memory regions, IP/CIDR allocation, port or ID range assignment, shard key ranges

**Required Checklist**

- [ ] Range bounds (start/end, written the way the domain actually writes them — hex for memory, CIDR for networks)
- [ ] Size (give both the raw number and a human-readable unit)
- [ ] Who owns this range, and at which stage
- [ ] Access permissions or reachability constraints
- [ ] Where the range is declared (which config file, node path, or constant)
- [ ] Overlaps and aliasing must be drawn — they are the whole reason this diagram exists

---

## Prototype 9 · Composition / Provenance Diagram

Used for: "what sources is this artifact assembled from" — assembling a configuration directory, which packages stack up into an image, which certificates chain together, which fragments merge into a defconfig.

**This prototype is the one most often mis-drawn as a flowchart.** A flowchart asks "what happens next"; a provenance diagram asks "where did this item come from" — the direction is reversed, and mixing them makes readers assume there is a chronological order.

**Required checklist**

- [ ] **Every single** constituent part of the artifact is listed. Drawing only the main sources and omitting the rest is misleading
- [ ] Each item's origin is precise down to "which directory / which command", not just "generated by a tool"
- [ ] **How it is combined**: copied? concatenated? generated on the spot? (`cp` vs `cat` vs a tool that mints it) — these three are very different
- [ ] Items that **look like they should be included but don't actually come from here** must be explicitly marked (e.g. a same-named file that can't be used — leave it with no arrow on the diagram and explain it in the `figcaption`)
- [ ] Who picks the artifact up afterwards, and at what point (**use a different line style from the provenance relationship**, because that isn't a provenance relationship)
- [ ] What this diagram does not cover

**Common omission**: drawing two source directories as arrows converging on the artifact. Readers will conclude "artifact = the union of those two", when the truth is usually "there are also a third and fourth source that aren't on the diagram". **How to check**: count how many parts the artifact has, and how many incoming edges the diagram has. If they don't match, something is missing.

---

## Size Selection

Estimate the width before drawing, then decide the strategy per `rwd.md`. Because pages live inside an iframe, the available width is narrower than a typical website:

| Estimated viewBox width | Strategy |
|---|---|
| **≤ 740** | `fig-scroll` single SVG, fixed 1:1 ← **the default. Set the canvas width to 740 from the start** |
| 741–900 | Still 1:1, but **it will scroll horizontally on a laptop**; `[E]` emits a WARN. Confirm all three width-reduction measures were tried first |
| > 900 | Split into wide (≤ 740) + narrow (≤ 340) dual variants |

**740 is not 900.** 900 guarantees "the font size won't break"; 740 guarantees "no scrolling is needed" — at the breakpoint where the in-page table of contents appears (iframe 1100) the container is only 748. See `rwd.md` for the derivation.

The order for reducing width is fixed: **change direction → reduce density → split the diagram → only then build dual variants**. Nine times out of ten an over-wide diagram is over-wide because of the habit of drawing left to right, not because there is genuinely that much information. **Never shrink the font size to buy width** — the 9.5px floor is an accessibility limit.

In practice: **5 or fewer horizontal stages fit in a single 740-wide scrolling diagram** — no need to maintain two versions. Only build dual variants when there are many stages, or when a side-by-side structure exceeds three columns.

Every `<svg>` must carry its own `style="--fig-vb:<viewBox width>px"` — there's no build step to fill this in for you.

The narrow variant isn't just turning horizontal into vertical — the information density needs to be rearranged. The wide version places key material in a separate box above the stage; the narrow version should fold it into the stage box as a single line, and switch to the `.n-*` font-size classes.
