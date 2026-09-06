/**
 * Draws "NIKHIL KOLLI" as board routing and animates the board powering up.
 *
 *   node assets/build-circuit.mjs
 *
 * The letterforms are polylines constrained to 90 and 45 degrees, which is the
 * rule real trace routing works to - no arbitrary angles. Every run terminates
 * in a via, so junctions land where a board would actually put one. That
 * constraint is the whole idea: the mark is legible as a name and correct as a
 * layout, rather than a typeface with a circuit texture laid over it.
 *
 * Layers, drawn in that order:
 *   base   unpowered copper, always visible
 *   halo   wide translucent copies of the powered runs, standing in for a glow
 *   power  the runs lit, revealed left to right by stroke-dashoffset
 *   pulse  a signal running the traces once the board is up
 *   vias   pads, fading in just behind the power front
 *
 * Two deliberate choices here are both about rendering the same on any machine:
 *
 * 1. No SVG filters. The glow used to be an feGaussianBlur over the animated
 *    group, which is exactly the case renderers disagree on - a filtered group
 *    whose children animate has to re-run the filter every frame, and support
 *    for that inside an <img> is the least consistent thing in this file.
 *    Stacked translucent strokes approximate the falloff with plain geometry
 *    every renderer draws identically.
 *
 * 2. No SMIL, only CSS. One mechanism, so behaviour does not depend on which of
 *    the two a given renderer implements more completely inside an <img>.
 */
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

const WORD = "NIKHIL KOLLI";

/* ---------------------------------------------------------------- metrics */
const CELL_W = 50;   // letter box width
const CELL_H = 70;   // cap height
const ADVANCE = 72;  // letter pitch
const SPACE = 42;    // word gap
const PAD = 34;      // margin around the mark
const TRACE_W = 8;
const VIA_R = 6;
const LEAD = 26;     // power rail stub entering and leaving the mark

/** Power-up: the front crosses the whole word in this long. */
const SWEEP_MS = 1500;
/** Trace units per ms once a run is lit, so long runs take longer. */
const RUN_SPEED = 0.58;

/** Idle pulse, once the board is up. */
const PULSE_PERIOD = 4200;
const PULSE_SPAN = 22;   // % of the period the pulse is travelling
const PULSE_STAGGER = 700;

/**
 * Whether to hold the mark still for `prefers-reduced-motion: reduce`.
 *
 * Off by design. That query is answered by the OS, and inside an SVG loaded
 * through <img> it is read from the OS even when the surrounding page reports
 * otherwise - so honouring it left the mark frozen on any machine with Windows
 * animation effects switched off, which is a common default rather than
 * necessarily a request for stillness. Flip this to true to restore the guard;
 * nothing else needs changing.
 *
 * What makes that defensible rather than merely convenient: the motion here is
 * a thin line lighting up over 1.7s plus a low-contrast pulse. There is no
 * large-area movement, parallax, zoom or flashing - the patterns reduced motion
 * exists to suppress.
 */
const RESPECT_REDUCED_MOTION = false;

const THEMES = {
  dark: {
    base: "#273040", trace: "#818CF8", viaFill: "#0D1117",
    pulse: "#A5F3FC", halo: true,
  },
  light: {
    base: "#D5DBE3", trace: "#5B4BD6", viaFill: "#FFFFFF",
    pulse: "#0E7490", halo: false,
  },
};

/** Widening stroke, falling opacity - stands in for a blur. */
const HALO = [
  { grow: 18, opacity: 0.07 },
  { grow: 11, opacity: 0.1 },
  { grow: 5, opacity: 0.14 },
];

/* -------------------------------------------------------------- glyph set */
// 50x70 cell. Diagonals are true 45 degrees.
const TRACE = {
  N: [[[0, 70], [0, 0]], [[0, 0], [50, 50]], [[50, 0], [50, 70]]],
  I: [[[0, 0], [50, 0]], [[25, 0], [25, 70]], [[0, 70], [50, 70]]],
  K: [[[0, 0], [0, 70]], [[50, 0], [15, 35]], [[15, 35], [50, 70]], [[0, 35], [15, 35]]],
  H: [[[0, 0], [0, 70]], [[50, 0], [50, 70]], [[0, 35], [50, 35]]],
  L: [[[0, 0], [0, 70]], [[0, 70], [50, 70]]],
  O: [[[15, 0], [35, 0], [50, 15], [50, 55], [35, 70], [15, 70], [0, 55], [0, 15], [15, 0]]],
};

/* ------------------------------------------------------------------ build */
const r1 = (n) => Math.round(n * 10) / 10;
const dOf = (pts) => "M " + pts.map((p) => p.join(",")).join(" L ");
const lenOf = (pts) =>
  pts.slice(1).reduce((a, p, i) => a + Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]), 0);

function layout() {
  let x = 0;
  const runs = [];
  for (const ch of WORD) {
    if (ch === " ") { x += SPACE; continue; }
    const glyph = TRACE[ch];
    if (!glyph) throw new Error(`no routing defined for "${ch}"`);
    for (const pts of glyph) runs.push(pts.map(([px, py]) => [px + x, py]));
    x += ADVANCE;
  }
  const width = x - (ADVANCE - CELL_W);

  // Power arrives from off-mark and leaves at the far side, so the sweep has a
  // visible source. Both leads sit on the baseline so it reads as one rail
  // running through; entering low and leaving high looked like a stray stub.
  runs.unshift([[-LEAD, CELL_H], [0, CELL_H]]);
  runs.push([[width, CELL_H], [width + LEAD, CELL_H]]);
  return { runs, width };
}

const { runs, width } = layout();

// One via per distinct run endpoint - shared corners get a single pad.
const seen = new Set();
const vias = [];
for (const pts of runs) {
  for (const p of [pts[0], pts[pts.length - 1]]) {
    const k = p.join();
    if (!seen.has(k)) { seen.add(k); vias.push(p); }
  }
}

const span = width + LEAD;
const phase = (x) => ((x + LEAD) / span) * SWEEP_MS;

const plan = runs.map((pts) => {
  const len = lenOf(pts);
  return {
    d: dOf(pts),
    len,
    delay: phase(pts[0][0]),
    dur: Math.max(180, len / RUN_SPEED),
  };
});

const VB = {
  x: -PAD - LEAD,
  y: -PAD,
  w: width + LEAD * 2 + PAD * 2,
  h: CELL_H + PAD * 2,
};

function render(t) {
  const powerCss = plan
    .map(
      (s, i) =>
        `.t${i}{stroke-dasharray:${r1(s.len)};stroke-dashoffset:${r1(s.len)};` +
        `animation:up ${r1(s.dur)}ms cubic-bezier(.3,.7,.4,1) ${r1(s.delay)}ms forwards}`
    )
    .join("\n    ");

  // Phase only - one period for every run, so the pulse stays a single wave
  // crossing the board instead of drifting apart over time.
  const pulseCss = plan
    .map(
      (s, i) =>
        `.u${i}{animation:pulse ${PULSE_PERIOD}ms linear ` +
        `${r1(SWEEP_MS + 500 + (s.delay / SWEEP_MS) * PULSE_STAGGER)}ms infinite}`
    )
    .join("\n    ");

  const viaCss = vias
    .map(([x], i) => `.v${i}{animation:pad 320ms ease-out ${r1(phase(x) + 110)}ms forwards}`)
    .join("\n    ");

  const base = plan.map((s) => `<path d="${s.d}"/>`).join("");
  const power = plan.map((s, i) => `<path class="t${i}" d="${s.d}"/>`).join("");
  const pulse = plan.map((s, i) => `<path class="u${i}" pathLength="100" d="${s.d}"/>`).join("");
  const pads = vias
    .map(([x, y], i) => `<circle class="v${i}" cx="${x}" cy="${y}" r="${VIA_R}"/>`)
    .join("");

  // Halo layers reuse the power classes, so they light in lockstep for free.
  const haloCss = t.halo
    ? HALO.map(
        (h, i) => `.h${i}{stroke:${t.trace};stroke-width:${TRACE_W + h.grow};opacity:${h.opacity}}`
      ).join("\n    ")
    : "";
  const haloLayers = t.halo
    ? HALO.map((h, i) => `<g class="l h${i}">${power}</g>`).join("\n  ")
    : "";

  const guard = RESPECT_REDUCED_MOTION
    ? `
    @media (prefers-reduced-motion:reduce){
      path,circle{animation:none!important}
      .pwr path{stroke-dashoffset:0!important}
      .pls{display:none!important}
      .via circle{opacity:1!important}
    }`
    : `
    /* No prefers-reduced-motion guard, on purpose - see RESPECT_REDUCED_MOTION
       in the build script. Inside an img element that query reports the OS
       setting regardless of the host page, so honouring it froze the mark on
       any machine with Windows animation effects off. */`;

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${VB.x} ${VB.y} ${VB.w} ${VB.h}" width="${VB.w}" height="${VB.h}" role="img" aria-label="Nikhil Kolli">
  <title>Nikhil Kolli</title>
  <style>
    .l{fill:none;stroke-width:${TRACE_W};stroke-linecap:round;stroke-linejoin:round}
    .base{stroke:${t.base}}
    ${haloCss}
    .pwr{stroke:${t.trace}}
    .pls{stroke:${t.pulse};stroke-width:${TRACE_W - 3.5};stroke-dasharray:3 120;stroke-dashoffset:3;opacity:.85}
    .via{fill:${t.viaFill};stroke:${t.trace};stroke-width:3.4}
    /* opacity has to sit on the circles: opacity is not inherited, so hiding
       the group instead would leave the per-via fade-ins animating nothing. */
    .via circle{opacity:0}
    @keyframes up{to{stroke-dashoffset:0}}
    @keyframes pad{to{opacity:1}}
    @keyframes pulse{
      0%{stroke-dashoffset:3}
      ${PULSE_SPAN}%{stroke-dashoffset:-110}
      100%{stroke-dashoffset:-110}
    }
    ${powerCss}
    ${pulseCss}
    ${viaCss}${guard}
  </style>
  <g class="l base">${base}</g>
  ${haloLayers}
  <g class="l pwr">${power}</g>
  <g class="l pls">${pulse}</g>
  <g class="via">${pads}</g>
</svg>
`;
}

/**
 * An SVG served as image/svg+xml is parsed as XML, so a bare "<" or "&"
 * anywhere in the stylesheet is a parse error and the whole mark fails to
 * render - silently, as a broken-image icon. Writing "<img>" in a CSS comment
 * did exactly that once. Comparing rendered bytes did not catch it either,
 * because two identical broken-image icons compare equal.
 */
function validate(svg, name) {
  const style = svg.match(/<style>([\s\S]*?)<\/style>/);
  if (!style) throw new Error(`${name}: no style block`);
  const bad = style[1].match(/[<&]/g);
  if (bad) {
    const line = style[1].split(/\n/).find((l) => /[<&]/.test(l)).trim();
    throw new Error(`${name}: ${bad.length} raw XML char(s) in CSS -> ${line}`);
  }
}

for (const [name, t] of Object.entries(THEMES)) {
  const svg = render(t);
  validate(svg, `circuit-${name}.svg`);
  writeFileSync(join(here, `circuit-${name}.svg`), svg);
}

const total = Math.max(...plan.map((s) => s.delay + s.dur));
console.log(`viewBox ${VB.x} ${VB.y} ${VB.w} ${VB.h}`);
console.log(`${plan.length} runs, ${vias.length} vias`);
console.log(`power-up ${(total / 1000).toFixed(2)}s, then a ${(PULSE_PERIOD / 1000).toFixed(1)}s pulse loop`);
console.log(`reduced-motion guard: ${RESPECT_REDUCED_MOTION ? "on" : "off"}`);
