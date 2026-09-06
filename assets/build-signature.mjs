/**
 * Draws "Nikhil Kolli" as a hand-lettered signature and animates the pen
 * writing it.
 *
 *   node assets/build-signature.mjs
 *
 * Why the letterforms are hand-authored bezier data rather than <text>:
 *
 *  - No web font can load inside an SVG that GitHub proxies through camo, so
 *    font-family:cursive would resolve to whatever the viewer happens to have
 *    (Comic Sans on Windows, Apple Chancery on macOS). The mark has to carry
 *    its own outlines.
 *  - Even with a font, stroke-dashoffset on <text> traces the *outline* of the
 *    glyphs, not their skeleton, so it reads as a shape being filled in rather
 *    than a pen moving. Handwriting needs a centreline, which only a drawn
 *    path gives.
 *
 * Timing is measured, not guessed: each stroke is flattened to a polyline to
 * get its true length, and duration = length / PEN_SPEED. One constant speed
 * across long sweeps and short stems is what makes it read as writing rather
 * than as eight unrelated animations. The gaps between strokes are pen lifts.
 *
 * The strokes are also the pen order a person would actually use: each word in
 * one pass, the K's arm as a second stroke, then the three i-dots, then the
 * underline. Nothing here is drawn in an order a hand could not produce.
 */
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

/* ---------------------------------------------------------------- metrics --
 * The letterforms below are authored against these guides:
 *   baseline 120 · x-height top 64 · ascender/cap top 22 · loop tops ~5
 * Slant is applied once, to the whole group, so the guides stay upright and
 * the numbers stay readable.
 */
const SLANT_DEG = -6;
const STROKE_W = 6.5;
const PAD = 10;

/** User units per second. The single knob that sets how fast the hand moves. */
const PEN_SPEED = 950;

/** Default pen lift between strokes. */
const LIFT = 85;

const THEMES = {
  dark: { ink: "#E6EDF3", glow: "#C7D2FE", accent: "#818CF8", bg: "none" },
  light: { ink: "#1F2328", glow: "#5B4BD6", accent: "#5B4BD6", bg: "none" },
};

/* --------------------------------------------------------------- strokes --
 * Absolute M/C only — the length/bbox parser below understands nothing else,
 * and keeping the data to one command keeps it honest.
 */
const STROKES = [
  {
    name: "Nikhil",
    kind: "ink",
    d: `M 24,132
        C 33,112 46,62 58,26
        C 65,6 38,2 36,24
        C 33,50 35,90 45,120
        C 53,86 63,52 76,32
        C 84,19 93,24 91,46
        C 89,72 87,98 89,120
        C 94,110 101,101 108,94
        C 115,86 120,74 122,64
        C 124,84 126,104 128,120
        C 136,98 148,56 158,22
        C 166,4 138,0 136,22
        C 133,44 134,62 137,78
        C 147,72 160,62 157,75
        C 154,86 144,86 141,92
        C 148,104 157,114 167,120
        C 175,98 186,56 196,22
        C 204,4 176,0 174,22
        C 171,46 173,90 180,120
        C 186,96 196,64 207,64
        C 216,64 214,94 217,120
        C 223,106 229,82 231,64
        C 233,84 235,104 237,120
        C 245,98 256,56 266,22
        C 274,4 246,0 244,22
        C 241,46 243,90 251,120
        C 257,113 264,108 272,105`,
  },
  {
    name: "K stem",
    kind: "ink",
    pause: 150,
    d: `M 300,128
        C 310,106 326,58 338,22
        C 347,4 316,0 314,22
        C 311,50 313,88 318,120`,
  },
  {
    name: "K arm",
    kind: "ink",
    pause: 90,
    d: `M 366,26
        C 350,46 336,60 325,70
        C 338,74 348,82 342,93
        C 337,102 340,110 349,114
        C 356,117 364,119 374,120`,
  },
  {
    name: "olli",
    kind: "ink",
    pause: 95,
    d: `M 374,120
        C 380,104 388,66 400,64
        C 386,64 382,80 384,92
        C 386,108 402,112 408,98
        C 414,86 410,68 400,64
        C 407,65 412,69 416,74
        C 427,58 438,38 448,22
        C 456,4 428,0 426,22
        C 423,46 425,90 433,120
        C 443,98 456,56 466,22
        C 474,4 446,0 444,22
        C 441,46 443,90 451,120
        C 457,106 463,82 465,64
        C 467,84 469,104 471,120
        C 477,113 485,108 493,104`,
  },

  /* The dots come after both words, the way a hand goes back for them.
   * Each sits just left of its own minim rather than centred over it: both i's
   * in "Nikhil" are followed by a looped ascender, and a centred dot lands
   * inside that loop. Crowding the dot toward its own letter is also what a
   * hand does when the next letter is tall. */
  { name: "dot i1", kind: "ink", pause: 200, min: 90, d: `M 120,37 C 120.7,37.7 121.4,38.4 122,39` },
  { name: "dot i2", kind: "ink", pause: 95, min: 90, d: `M 229,37 C 229.7,37.7 230.4,38.4 231,39` },
  { name: "dot i3", kind: "ink", pause: 95, min: 90, d: `M 465,37 C 465.7,37.7 466.4,38.4 467,39` },

  {
    name: "swash",
    kind: "accent",
    pause: 170,
    ease: "cubic-bezier(.2,.6,.3,1)",
    d: `M 70,131
        C 38,134 48,149 92,158
        C 210,182 420,176 496,146`,
  },
];

/* ------------------------------------------------------------- geometry --- */

/** Absolute M/C only. Anything else is a typo, so fail loudly. */
function parse(d) {
  const t = d.trim().split(/[\s,]+/);
  const segs = [];
  let cur = null;
  for (let i = 0; i < t.length; ) {
    const cmd = t[i++];
    const num = () => {
      const v = Number(t[i++]);
      if (!Number.isFinite(v)) throw new Error(`bad number near "${t[i - 1]}"`);
      return v;
    };
    if (cmd === "M") {
      cur = [num(), num()];
    } else if (cmd === "C") {
      const c1 = [num(), num()];
      const c2 = [num(), num()];
      const p = [num(), num()];
      segs.push({ from: cur, c1, c2, to: p });
      cur = p;
    } else {
      throw new Error(`unsupported path command: ${cmd}`);
    }
  }
  return segs;
}

const cubic = (a, b, c, d, t) => {
  const u = 1 - t;
  return u * u * u * a + 3 * u * u * t * b + 3 * u * t * t * c + t * t * t * d;
};

/** Flatten to points. 48 samples/segment puts the length error well under 0.1%. */
function samples(d, n = 48) {
  const out = [];
  for (const s of parse(d)) {
    for (let i = 0; i <= n; i++) {
      const t = i / n;
      out.push([
        cubic(s.from[0], s.c1[0], s.c2[0], s.to[0], t),
        cubic(s.from[1], s.c1[1], s.c2[1], s.to[1], t),
      ]);
    }
  }
  return out;
}

function length(pts) {
  let L = 0;
  for (let i = 1; i < pts.length; i++) {
    L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
  }
  return L;
}

/* ----------------------------------------------------------------- build --- */

const tan = Math.tan((SLANT_DEG * Math.PI) / 180);
const r1 = (n) => Math.round(n * 10) / 10;

// Measure once; both themes share the geometry and the timing.
let cursor = 0;
const plan = STROKES.map((s, i) => {
  const pts = samples(s.d);
  const len = length(pts);
  const dur = Math.max(s.min ?? 0, (len / PEN_SPEED) * 1000);
  const delay = cursor + (i === 0 ? 0 : (s.pause ?? LIFT));
  cursor = delay + dur;
  return { ...s, pts, len, dur, delay, d: s.d.trim().replace(/\s+/g, " ") };
});

const TOTAL = cursor;

// viewBox is computed after the slant, so tuning SLANT_DEG never clips the mark.
const box = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
for (const s of plan) {
  for (const [x, y] of s.pts) {
    const sx = x + tan * y;
    if (sx < box.x0) box.x0 = sx;
    if (sx > box.x1) box.x1 = sx;
    if (y < box.y0) box.y0 = y;
    if (y > box.y1) box.y1 = y;
  }
}
const grow = STROKE_W / 2 + PAD;
const vb = {
  x: r1(box.x0 - grow),
  y: r1(box.y0 - grow),
  w: r1(box.x1 - box.x0 + grow * 2),
  h: r1(box.y1 - box.y0 + grow * 2),
};

/**
 * The shine rides the stroke as a gradient rather than a masked overlay, so it
 * follows the pen line exactly instead of a rectangle over the top of it. Pad
 * spread means the band only exists between x1 and x2 — everywhere else is
 * plain ink — so translating it far past the end buys a rest between sweeps.
 */
const SHINE_BAND = 170;
const SHINE_TRAVEL = Math.ceil(vb.w + SHINE_BAND) * 2.6;
const SHINE_DUR = 6.5;

function render(t) {
  const css = plan
    .map((s, i) => {
      // Hiding a stroke by offsetting a single-value dasharray leaves its round
      // linecap painting through the gap: harmless on a 1600-unit word, but the
      // i-dots are 2.4 units against a 6.5-wide stroke, so they sat on screen
      // from the first frame until their turn came 3.5s later. An explicit gap
      // wider than the cap, plus a start offset a full stroke-width clear of
      // the path, keeps every stroke genuinely invisible until it is drawn.
      const gap = r1(s.len + STROKE_W * 2);
      const from = r1(s.len + STROKE_W);
      return (
        `.k${i}{stroke-dasharray:${r1(s.len)} ${gap};stroke-dashoffset:${from};` +
        `animation:w ${r1(s.dur)}ms ${s.ease ?? "linear"} ${r1(s.delay)}ms forwards}`
      );
    })
    .join("\n    ");

  const paths = (kind) =>
    plan
      .map((s, i) => (s.kind === kind ? `      <path class="k${i}" d="${s.d}"/>` : null))
      .filter(Boolean)
      .join("\n");

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${vb.x} ${vb.y} ${vb.w} ${vb.h}" width="${vb.w}" height="${vb.h}" role="img" aria-label="Nikhil Kolli">
  <title>Nikhil Kolli</title>
  <defs>
    <linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="${r1(vb.x - SHINE_BAND)}" y1="0" x2="${r1(vb.x)}" y2="0">
      <stop offset="0" stop-color="${t.ink}"/>
      <stop offset="0.5" stop-color="${t.glow}"/>
      <stop offset="1" stop-color="${t.ink}"/>
      <animateTransform attributeName="gradientTransform" type="translate"
        from="0 0" to="${SHINE_TRAVEL} 0" dur="${SHINE_DUR}s"
        begin="${r1(TOTAL) / 1000}s" repeatCount="indefinite"/>
    </linearGradient>
  </defs>
  <style>
    @keyframes w{to{stroke-dashoffset:0}}
    ${css}
    @media (prefers-reduced-motion:reduce){
      path{animation:none!important;stroke-dashoffset:0!important}
    }
  </style>
  <g transform="skewX(${SLANT_DEG})" fill="none" stroke-width="${STROKE_W}" stroke-linecap="round" stroke-linejoin="round">
    <g stroke="url(#shine)">
${paths("ink")}
    </g>
    <g stroke="${t.accent}" stroke-width="${STROKE_W - 2}" opacity="0.9">
${paths("accent")}
    </g>
  </g>
</svg>
`;
}

for (const [name, t] of Object.entries(THEMES)) {
  writeFileSync(join(here, `signature-${name}.svg`), render(t));
}

console.log(`viewBox  ${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
console.log(`write    ${(TOTAL / 1000).toFixed(2)}s over ${plan.length} strokes @ ${PEN_SPEED}u/s\n`);
for (const s of plan) {
  console.log(
    `  ${s.name.padEnd(9)} len ${String(Math.round(s.len)).padStart(4)}  ` +
      `${String(Math.round(s.delay)).padStart(4)}ms +${String(Math.round(s.dur)).padStart(4)}ms`
  );
}

export { plan, vb, TOTAL, SLANT_DEG, STROKE_W, THEMES };
