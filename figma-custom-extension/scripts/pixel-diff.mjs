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
