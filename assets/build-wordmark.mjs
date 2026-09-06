/**
 * Draws "NIKHIL KOLLI" as a heavy geometric wordmark with real extruded depth.
 *
 *   node assets/build-wordmark.mjs
 *
 * The letters are hand-drawn skeletons stroked at display weight - 22 units on
 * a 100 cap, mitred joins, butt caps - not text. Nothing else is possible: no
 * web font loads inside an SVG that GitHub proxies through camo, so any <text>
 * falls back to whatever the viewer happens to have installed, and the mark
 * would look different on every machine.
 *
 * Structure, back to front:
 *   five extrude layers stepping down-right into a darkening indigo
 *   the face, in near-white
 *   a specular band, clipped to a moving rect, sweeping the face on a loop
 *
 * Two structural rules this file has to respect, both learned the hard way:
 *
 *  1. An element that carries a `transform` attribute must never be the element
 *     a CSS animation transforms - the CSS transform replaces the attribute
 *     outright rather than composing with it. Letters are therefore positioned
 *     on a static outer group and animated on an inner one.
 *
 *  2. Gradients must use gradientUnits="userSpaceOnUse". A vertical stem has a
 *     zero-width bounding box, and an objectBoundingBox gradient cannot resolve
 *     against that, so every stem silently fails to render.
 */
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

const NAME = "NIKHIL KOLLI";

/* ---------------------------------------------------------------- metrics */
const CAP = 100;      // cap height
const SW = 22;        // stroke weight
const TRACK = 8;      // gap between letter cells
const WORDGAP = 40;   // gap between the two words
const PAD = 24;       // margin around the mark

/** Extrusion: layers stepping down-right, each STEP further than the last. */
const DEPTH = 5;
const STEP = 2.6;

/** Letters rise in on a stagger, then the sweep loops forever. */
const RISE_MS = 620;
const RISE_STAGGER = 52;
const SWEEP_PERIOD = 4600;
const SWEEP_BAND = 150;

const THEMES = {
  dark: {
    face: "#F0F3F8",
    // Near the face first, falling away into shadow.
    ramp: ["#5B53DE", "#524AC9", "#4740AE", "#3B3591", "#2F2A74"],
    sweep: "#FFFFFF", sweepOp: 0.55,
  },
  light: {
    face: "#16181D",
    ramp: ["#8F84F0", "#7C70E4", "#6A5ED4", "#584CC0", "#4A3FAB"],
    // A white sweep would vanish; on a dark face a soft violet reads as sheen.
    sweep: "#C7D2FE", sweepOp: 0.5,
  },
};

/* -------------------------------------------------------------- glyph set */
/**
 * Skeletons on a 100 cap. Stroke centres are inset by SW/2 so the painted edge
 * lands on the cell bounds. The O is a true ellipse - a geometric sans wants a
 * circular bowl, not a polygon. Letters that turn a corner are single
 * polylines, so the mitre fills the join; two butt-capped paths meeting there
 * would leave a notch.
 */
const GLYPH = {
  N: { w: 62, p: [[[11, 100], [11, 0], [51, 100], [51, 0]]] },
  I: { w: 22, p: [[[11, 0], [11, 100]]] },
  K: { w: 64, p: [[[11, 0], [11, 100]], [[53, 0], [11, 52], [55, 100]]] },
  H: { w: 62, p: [[[11, 0], [11, 100]], [[51, 0], [51, 100]], [[11, 50], [51, 50]]] },
  L: { w: 62, p: [[[11, 0], [11, 100], [53, 100]]] },
  O: { w: 64, o: { cx: 32, cy: 50, rx: 21, ry: 39 } },
};

const r1 = (n) => Math.round(n * 10) / 10;
const dOf = (pts) => "M " + pts.map((p) => p.join(",")).join(" L ");

/* ------------------------------------------------------------------ build */
let cursor = PAD;
const placed = [];
for (const ch of NAME) {
  if (ch === " ") { cursor += WORDGAP; continue; }
  const g = GLYPH[ch];
  if (!g) throw new Error(`no glyph drawn for "${ch}"`);
  placed.push({ ch, g, x: cursor, i: placed.length });
  cursor += g.w + TRACK;
}

const INK_W = cursor - TRACK - PAD;
const REACH = DEPTH * STEP;                    // how far the extrusion runs
const W = r1(INK_W + PAD * 2 + REACH);
const H = r1(CAP + PAD * 2 + REACH);

/**
 * Positioning lives on the outer group, the rise animation on the inner one -
 * see rule 1 at the top of this file.
 */
function word() {
  return placed
    .map((it) => {
      const inner = it.g.o
        ? `<ellipse cx="${it.g.o.cx}" cy="${it.g.o.cy}" rx="${it.g.o.rx}" ry="${it.g.o.ry}"/>`
        : it.g.p.map((p) => `<path d="${dOf(p)}"/>`).join("");
      return `<g transform="translate(${r1(it.x)} ${PAD})"><g class="ltr l${it.i}">${inner}</g></g>`;
    })
    .join("");
}

function render(t) {
  const layers = t.ramp
    .map((col, i) => {
      const k = DEPTH - i;                     // furthest layer drawn first
      return `<g class="k" stroke="${col}" transform="translate(${r1(k * STEP)} ${r1(k * STEP)})">${word()}</g>`;
    })
    .join("\n  ");

  const riseCss = placed
    .map((it) => `.l${it.i}{animation-delay:${it.i * RISE_STAGGER}ms}`)
    .join("");

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${NAME}">
  <title>${NAME}</title>
  <defs>
    <clipPath id="band">
      <rect class="sweep" x="${-SWEEP_BAND}" y="0" width="${SWEEP_BAND}" height="${H}"/>
    </clipPath>
  </defs>
  <style>
    .k{fill:none;stroke-width:${SW};stroke-linecap:butt;stroke-linejoin:miter}
    .face{stroke:${t.face}}
    .shine{stroke:${t.sweep};opacity:${t.sweepOp}}
    .ltr{animation:rise ${RISE_MS}ms cubic-bezier(.2,.85,.3,1) both}
    @keyframes rise{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
    ${riseCss}
    /* The band moves, not the letters: translating the clipped group would
       carry its own clip along and nothing would appear to move. */
    .sweep{animation:sweep ${SWEEP_PERIOD}ms linear infinite}
    @keyframes sweep{
      0%{transform:translateX(0)}
      42%{transform:translateX(${r1(W + SWEEP_BAND)}px)}
      100%{transform:translateX(${r1(W + SWEEP_BAND)}px)}
    }
  </style>
  ${layers}
  <g class="k face">${word()}</g>
  <g class="k shine" clip-path="url(#band)">${word()}</g>
</svg>
`;
}

/**
 * An SVG served as image/svg+xml is parsed as XML, so a bare "<" or "&" in the
 * stylesheet is a parse error and the whole mark renders as a broken-image
 * icon - silently. Comparing rendered bytes does not catch it either, since two
 * broken-image icons compare equal.
 */
function validate(svg, name) {
  const style = svg.match(/<style>([\s\S]*?)<\/style>/);
  if (!style) throw new Error(`${name}: no style block`);
  const bad = style[1].match(/[<&]/g);
  if (bad) throw new Error(`${name}: ${bad.length} raw XML char(s) in CSS`);
  if (/gradientUnits="objectBoundingBox"/.test(svg))
    throw new Error(`${name}: objectBoundingBox gradient will drop vertical stems`);
}

for (const [name, t] of Object.entries(THEMES)) {
  const svg = render(t);
  validate(svg, `wordmark-${name}.svg`);
  writeFileSync(join(here, `wordmark-${name}.svg`), svg);
}

console.log(`viewBox 0 0 ${W} ${H}  |  cap ${CAP}, weight ${SW}, track ${TRACK}`);
console.log(`${placed.length} letters, ${DEPTH} extrude layers reaching ${r1(REACH)}`);
console.log(`rise ${RISE_MS}ms staggered ${RISE_STAGGER}ms, sweep loops ${SWEEP_PERIOD}ms`);
