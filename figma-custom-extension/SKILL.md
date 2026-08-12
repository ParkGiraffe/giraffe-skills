---
name: figma-custom-extension
description: >-
  Faithfully bring a Figma design into code via the Figma MCP: reliably extract
  the REAL vector/SVG of icons and other assets (never guessing from layer
  names or giving up on an empty export), convert raster assets to WebP, verify
  the result pixel-by-pixel against the Figma screenshot, and confirm responsive
  behavior with the user before laying out. Use this whenever you implement a
  Figma screen/component and need the actual art — back buttons,
  share/kebab/bookmark/verified badges, like hearts, social logos, avatars —
  especially when `download_assets` returns `export: null`, a node's children
  look empty, an svg export comes back implausibly huge, every icon is
  generically named `MO/Icon` / `Icon` / `Vector`, or you catch yourself about
  to substitute a "standard" icon by guessing. Also use it before writing layout
  code for a Figma frame, to decide fixed-vs-responsive sizing for button
  heights, padding, and gaps. Trigger on phrases like "implement this Figma
  design", "get the icons from Figma", "this svg export came back empty", "drill
  into the node until a real icon shows up", "make it match the design exactly",
  or any design-to-code task where visual fidelity matters.
---

# Extracting real icons/SVGs from Figma

## Why this exists

Figma MCP gives you three views of a node and they disagree about what's "there":

- `get_metadata` returns **structure only** — id, type, name, x/y/w/h. No art. And
  in most design systems every icon instance is named the same generic thing
  (`MO/Icon`, `Icon`, `Vector`). So from metadata alone you cannot tell a back
  arrow from a share node from a kebab. If you implement from metadata, you are
  **guessing from position**, and guesses are wrong often enough to matter
  (filled vs outline, share vs X-logo, a gradient verified badge vs a plain
  check).
- `download_assets` (svg) returns the **rendered vector** — the real thing — but
  it returns `export: null` for certain nodes, which looks like failure but
  usually means "look somewhere else," not "nothing here."
- `get_design_context` **resolves an instance to its master component** and hands
  back asset URLs. This is the escape hatch that recovers most `null` exports.

The job of this skill: never ship a guessed icon. Drill until you have the real
vector, or until you can prove the node is a deliberately empty placeholder.

## The core loop

For each icon/asset node you need, run this until you hit a terminal state:

1. **Try the direct export first.**
   `download_assets(nodeId, defaultFormat: "svg")`.
   - Non-null `export.url` with a **sane size** (an icon svg is ~1–5 KB) and an
     empty `rawImages` → download it and go to **Clean up** below. Done.
   - Non-null url but **`sizeBytes` is huge** (hundreds of KB to tens of MB) or
     **`rawImages` is non-empty** → this node is **image-based, not a vector
     icon** (an avatar/photo, or a logo with a photographic fill). The giant svg
     is the source bitmaps inlined as base64 — a trap, do not download it.
     Re-export as raster instead: `download_assets(nodeId, defaultFormat: "png",
defaultScale: 2)`, which yields a small clean PNG. (A 32px avatar is ~8 KB
     as PNG vs ~58 MB as svg.) Use that PNG, or grab a specific source photo from
     `rawImages` if you need the unmasked original.
   - `export: null` → go to step 2. Do **not** conclude "no icon" yet.

2. **Look at the node's own shape with `get_metadata(nodeId)`.** Decide which case you're in:
   - **Has children** (frames/vectors/instances nested inside) → the art lives in
     a child. Recurse: run this same loop on each child until a child yields a
     real vector. Prefer the child whose name/type looks like the glyph
     (`Vector`, `Icon`, `Ellipse`, `Star`, a `vector`/`boolean-operation` type).
   - **Leaf `instance`, no children listed** → metadata can't expand an instance,
     because the vector lives in the **master component**, not in this instance's
     subtree. That is exactly why the svg export was empty. Go to step 3.
   - **Leaf `frame`/`rectangle` with no children and no fills** → this is almost
     certainly a **deliberate empty placeholder** (e.g. a 10×10 reserved box for a
     badge that isn't drawn in this mock). This is a terminal state: report it as
     empty, do not fabricate an icon to fill it. (Confirm with a tiny screenshot
     if unsure — a placeholder renders blank.)

3. **Resolve the instance with `get_design_context(nodeId)`.** This is the key
   move people miss. It dereferences the component and returns reference code that
   embeds the asset as a URL constant (e.g. `const imgFoo = "https://…/asset/…"`).
   The art may be stored as an **image asset** (sometimes an SVG, sometimes a
   raster) rather than as inline paths — that storage choice is why `download_assets`
   svg came back null. Pull the asset URL out of the returned code and go to
   **Clean up**.

4. **Confirm the glyph visually when anything is still ambiguous.**
   `get_screenshot(nodeId, maxDimension: 96)`. Use this to verify identity
   (back vs forward chevron, filled vs outline) and to sanity-check that a
   recovered asset matches what's actually on screen. A blank/1×1 screenshot
   corroborates the "empty placeholder" verdict.

## Clean up (every downloaded asset)

`curl -o` the asset URL, then `file` it to learn the real format (an asset named
like an image can actually be SVG, and vice versa — trust `file`, not the name).

Exports of an **instance lifted out of its frame** carry junk you must strip
before reusing the path:

- a full-bleed background `<rect ... fill="#F5F5F5"/>`,
- one or more giant boundary `<path>`s with absurd coordinates (thousands, e.g.
  `M-521 -1099…`) and `fill="#E0E0E0"` / `fill-opacity="0.1"` — that's the design
  canvas border, not the icon,
- deeply nested wrapper `<g id="Frame …">` / `<rect width="375" height="812">`
  (the whole artboard).

The **actual icon is the innermost `<path>`/`<circle>`/`<g>`** with sane small
coordinates and the real stroke/fill. Keep that, its `viewBox`, and any
`<linearGradient>`/`<clipPath>` it references. Drop everything else. Preserve the
real colors and whether it's **filled or stroked** — that encodes state (a filled
heart = liked, a `#9CBEFF` filled bookmark = saved), which is design intent, not
noise.

## Raster assets become WebP

Vectors stay SVG. But when a node is genuinely image-based (avatars, photos,
raster logos — the `defaultFormat:"png"` branch above), **do not commit the
PNG**. Convert it to WebP: same visible quality at a fraction of the size (an
8.6 KB avatar PNG → ~1.4 KB WebP), which is what app/web bundles want.

```bash
cwebp -quiet -q 85 in.png -o out.webp     # cwebp present on this machine
# fallbacks if cwebp is missing:
ffmpeg -y -i in.png -c:v libwebp -quality 85 out.webp
npx --yes sharp-cli -i in.png -o out.webp -f webp -q 85
```

Export the PNG at 2× (or 3× for high-density) before converting so it stays
crisp, and keep the dimensions the design expects. Only rasters get converted —
never run an icon's SVG through this; an SVG scales for free.

## Implementation: wire the extracted art, never a look-alike

Extracting the real SVG is only half the job — the failure mode is extracting it
correctly and then, while writing the screen, reaching for an icon font
(`@expo/vector-icons`, `lucide`, `heroicons`, `react-icons`, FontAwesome,
Ionicons, Material) because it's "close enough" and one import away. It is never
close enough: the share glyph, the X logo, the back chevron's stroke width, the
filled-vs-outline state all differ, and the user spots it immediately. The whole
point of doing the extraction is defeated the moment you substitute.

Rule: **every icon in the implemented screen must come from the extracted Figma
vector** (rendered as an inline SVG component — e.g. `react-native-svg`,
`<svg>` — or a Code Connect-mapped component), reusing an existing component only
after confirming its path data matches. Do not introduce an icon-font glyph for
anything that exists in the design. If you cannot extract one (export keeps
failing) say so and ask — don't paper over it with a look-alike.

Build a small component per glyph from the cleaned path (keep the real
stroke/fill, viewBox, and any state variants like filled/outline), then reference
those everywhere instead of font glyphs. When you finish, grep the changed files
for the icon-font import names above — any hit on a screen you just built to match
a design is a substitution you need to replace.

**Before creating a new icon component, check whether the codebase already has it.**
Design systems reuse the same glyph across many screens; the code should mirror
that instead of growing a duplicate per feature. Search existing icon components
for one whose path data (or viewBox + visual) matches the extracted SVG — if it's
there, reuse it rather than writing a second copy. And when a glyph is (or will
be) used by more than one feature, put the component in the shared icon layer
(e.g. `shared/icons`, `shared/ui`) rather than inside one feature folder, so every
caller pulls the single source. A good rule: first use → colocate is fine; second
caller → lift it to shared and update both. This keeps one authoritative path per
glyph, so a later design tweak is a one-file change, not a hunt for clones.

## Audit every node's properties — don't eyeball

The repeated failure in design-to-code is implementing from a glance and getting
the small numbers wrong: header looked bold so you wrote `700` when it's `600`,
the input looked like a 12px radius when it's 8px, the placeholder is 16px not
14px, the gap band is `#fbfbfb` not `#f0f0f1`. Each is invisible alone and
glaring side-by-side. Eyeballing does not catch these; reading the node does.

So before (or alongside) implementing, **walk the whole node subtree and pull the
real properties for every visible node**, then build an inventory you verify
against. Use `get_metadata` for the tree, then `get_design_context` per node (it
returns font family/style/weight/size/lineHeight/letterSpacing, fills, radius,
padding, gap) and `get_variable_defs` to resolve the design-system tokens
(`MO/Title6`, `MO/Body5`, color tokens) once so you can map names→values.

For each node capture, as applicable:

- **Text**: font family, style/weight, size, lineHeight, letterSpacing, color.
- **Container/shape**: background/fill, border (color/width), corner radius,
  padding, item gap, width/height.
- **Icon/asset**: handled by the extraction loop above.

Write it down (a small per-node table keyed by node id + role), implement from
that table, and tick each property off. A property you never read is a property
you will get wrong — the goal is zero unverified values, not "looks about right".

**Token theme trap**: a token's _fallback default_ in `get_design_context` is not
always the rendered value. `bg-[var(--accent/bg2,#15171b)]` shows the dark
default, but on a light screen the variable resolves light (e.g. `#f7f7f7`). When
a token name or value looks theme-dependent (dark/light, accent), don't trust the
fallback — sample the actual pixel from a `get_screenshot` of that node and use
the rendered color.

## Verify against the screenshot (pixel-diff loop)

Extracting the "right" node is not the same as extracting the _correct_ art —
you can grab the wrong layer, miss an overlay, or get a color/stroke-width off
and not notice by eye, especially at 16–24 px. So prove each asset (and, once
built, each component) matches Figma instead of eyeballing it. This is a loop,
not a one-shot check:

1. **Reference**: `get_screenshot(nodeId, maxDimension: <node's longer side>)`
   and download the PNG. This is ground truth and defines the canonical size.
2. **Candidate**: your extracted/cleaned asset (svg or png) or a render of your
   implemented component at the same size.
3. **Diff**: run the bundled script (first use: `npm install` once in its dir):

   ```bash
   cd <skill>/scripts && npm install            # one time
   node <skill>/scripts/pixel-diff.mjs REF.png CANDIDATE.svg --threshold 0.02 --out diff.png
   ```

   It rasterizes both to the reference size on a common background and reports
   `mismatchPercent` + `pass` (exit 0/1), writing a `diff.png` that highlights
   the differing pixels. (`compare -metric AE` from ImageMagick works too if you
   have it; this machine doesn't, hence the script.)

4. **If it fails** (over threshold), the highlighted `diff.png` tells you _where_
   — wrong glyph, missing layer, color mismatch, stroke too thin/thick, wrong
   fill-vs-stroke state. Fix the extraction and **re-diff**. Loop until it passes.

Thresholds: anti-aliasing alone differs a handful of pixels, so a faithful icon
lands well under ~2% (a clean extraction is often 1 differing pixel ≈ 0.1%). A
wrong icon is unmistakable — tens of percent. Flatten both on the _same_
background before comparing so transparent edges don't dominate the count. Don't
chase 0% — sub-pixel AA noise is expected and meaningless.

**Pixel-diff is necessary but not sufficient — always finish with the node audit.**
A whole-screen diff can sit under threshold while individual properties are subtly
wrong: a weight 600 read as 700, a 12px radius that should be 8, a color from the
token's dark fallback (`#222`) instead of the theme-resolved value (`#000`), an
icon at 22px that should be 18, a 16px gap that should be 25. These hide inside an
"overall looks right" diff, and they're exactly what a meticulous reviewer flags
one by one. So after the capture comparison passes, **still run the per-node
property audit above to completion** — walk every node and confirm color, size,
font (family/weight/size/lineHeight), icon dimensions, component dimensions, and
spacing individually against the node's real values. Treat the audit, not the
pixel-diff, as the final gate. Resolve theme-dependent tokens with
`get_variable_defs` (it returns the values actually applied in this screen's mode,
e.g. `Neutral/Light8 = #000000`), not the inline fallback. The diff catches gross
mistakes fast; the audit catches the dozen small ones that get noticed later.

## Responsive: confirm the strategy before you build

Figma hands you one fixed frame (often 375 px wide), but most apps render
responsively. The fixed pixel values in the design are a _snapshot at one width_,
not a spec for every width — so committing them verbatim quietly bakes in a
single-width layout that breaks elsewhere, and that's expensive to redo. Before
writing any layout code, stop and confirm with the user rather than assuming:

- **Is this screen responsive, or a fixed/max width?** (And which breakpoints /
  target widths matter — phone only, phone+tablet, web?)
- **If responsive, how should the design's fixed values map?** Get explicit
  sign-off per category, because each has more than one reasonable answer:
  - **button heights / control sizes** — fixed px, a size scale/token, or fluid?
  - **padding & margins** — fixed, spacing-scale tokens, or clamp/`%`/viewport units?
  - **gaps between items** — fixed, token, or fluid?
  - **font sizes** — fixed, type scale, or fluid (`clamp()`)?
  - **the media/image block** — fixed aspect ratio that scales to width?

Offer concrete options (ideally tied to the project's existing token/spacing
system) and let the user pick — don't guess a strategy and refactor later. Once
confirmed, implement against that decision and still run the pixel-diff at the
design's reference width as a regression check.

## Report honestly

When you present results, make the provenance unmissable so a reviewer can trust
it:

- For each icon: node id, what it actually is, key spec (fill/stroke color,
  filled vs outline, viewBox), and **how you got it** (direct svg export / via
  child node / via `get_design_context` asset).
- Call out anything that is **not** a faithful extraction — an empty placeholder
  you skipped, or a node you could not resolve and had to substitute. A guessed
  substitute must be labeled as such, never blended in silently. The whole point
  is that the reader knows exactly which pixels are real Figma art and which are
  your judgement call.

## Quick reference

| Symptom                                                                       | Meaning                                                 | Action                                                     |
| ----------------------------------------------------------------------------- | ------------------------------------------------------- | ---------------------------------------------------------- |
| `download_assets` svg → non-null url, small size, no rawImages                | real vector                                             | download + clean                                           |
| `download_assets` svg → non-null url but huge `sizeBytes` / rawImages present | image-based node (avatar/photo), svg is inlined bitmaps | re-export `defaultFormat:"png"` scale 2, or use a rawImage |
| `download_assets` svg → `export: null`, node has children                     | art is in a child                                       | recurse into children                                      |
| `download_assets` svg → `export: null`, node is leaf instance                 | art is in master component / stored as asset            | `get_design_context`, pull asset URL                       |
| `download_assets` svg → `export: null`, leaf frame, no fills/children         | intentional empty placeholder                           | report empty, don't fabricate                              |
| identity unclear (which glyph? filled?)                                       | metadata is too coarse                                  | `get_screenshot maxDimension:96`                           |
| exported svg full of huge coords + `#F5F5F5`/`#E0E0E0`                        | canvas/border noise from lifting an instance            | strip to innermost path                                    |

## Anti-patterns

- Implementing icons straight from `get_metadata` names — they're generic; you're
  guessing.
- Treating `export: null` as "this node has no icon." It usually means "resolve
  the instance" or "recurse into children."
- Substituting a "standard" lucide/heroicon look-alike without saying so. If you
  genuinely cannot recover the art, extract everything you can and flag the gap.
- Pasting an exported instance SVG as-is, with the artboard rect and border path
  still in it.
- Downloading the giant svg for an image-based node instead of re-exporting PNG;
  or committing that PNG raw instead of converting it to WebP.
- Declaring a component "matches the design" by eye, without a pixel-diff against
  the Figma screenshot.
- Hardcoding the design's fixed px (button heights, padding, gaps) into a
  responsive layout without first confirming the sizing strategy with the user.

---

## Appendix: bundled scripts (scripts/)

First use: `cd scripts && npm install` (installs sharp, pixelmatch).

### scripts/package.json

```json
{
  "name": "figma-icon-extraction-scripts",
  "private": true,
  "type": "module",
  "dependencies": {
    "sharp": "^0.33.5",
    "pixelmatch": "^6.0.0"
  }
}
```

### scripts/pixel-diff.mjs

```js
import sharp from 'sharp';
import pixelmatch from 'pixelmatch';

const [, , refPath, candPath, ...rest] = process.argv;
if (!refPath || !candPath) {
  console.error('usage: node pixel-diff.mjs <reference> <candidate> [--threshold 0.02] [--out diff.png] [--bg #ffffff] [--pixelTol 0.1]');
  console.error('  reference: the Figma get_screenshot PNG of the node (defines the canonical size)');
  console.error('  candidate: your extracted asset or rendered component (svg or png)');
  console.error('  --threshold: max fraction of differing pixels to still pass (default 0.02 = 2%)');
  console.error('  --pixelTol:  per-pixel color tolerance passed to pixelmatch (default 0.1)');
  process.exit(2);
}

let threshold = 0.02;
let out = 'diff.png';
let bg = '#ffffff';
let pixelTol = 0.1;
for (let i = 0; i < rest.length; i++) {
  if (rest[i] === '--threshold') threshold = parseFloat(rest[++i]);
  else if (rest[i] === '--out') out = rest[++i];
  else if (rest[i] === '--bg') bg = rest[++i];
  else if (rest[i] === '--pixelTol') pixelTol = parseFloat(rest[++i]);
}

const refMeta = await sharp(refPath).metadata();
const W = refMeta.width;
const H = refMeta.height;

const normalize = (p) => sharp(p, { density: 384 }).resize(W, H, { fit: 'fill' }).flatten({ background: bg }).ensureAlpha().raw().toBuffer();

const [refBuf, candBuf] = await Promise.all([normalize(refPath), normalize(candPath)]);

const diff = Buffer.alloc(W * H * 4);
const mismatched = pixelmatch(refBuf, candBuf, diff, W, H, { threshold: pixelTol, includeAA: false });
const pct = mismatched / (W * H);
await sharp(diff, { raw: { width: W, height: H, channels: 4 } })
  .png()
  .toFile(out);

const pass = pct <= threshold;
console.log(
  JSON.stringify(
    {
      width: W,
      height: H,
      mismatchedPixels: mismatched,
      mismatchPercent: +(pct * 100).toFixed(3),
      thresholdPercent: +(threshold * 100).toFixed(3),
      pass,
      diffImage: out,
    },
    null,
    2,
  ),
);
process.exit(pass ? 0 : 1);
```
