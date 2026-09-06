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
 * Three layers, drawn in that order:
 *   base   unpowered copper, always visible
 *   power  the same runs lit, revealed left to right by stroke-dashoffset
 *   vias   pads, fading in just behind the power front
 *
 * Everything animates in CSS, deliberately. An earlier mark used SMIL for its
 * highlight and the reduced-motion guard could not switch it off, because
 * animation:none is a CSS property and does not reach SMIL. Keeping one
 * mechanism means one guard covers all of it.
 *
 * The looping pulse uses pathLength="100" so a single @keyframes drives runs of
 * every length; without it each run would need its own keyframes block.
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

/** Power-up: the front crosses the whole word in this long. */
const SWEEP_MS = 1500;
/** Trace units per ms once a run is lit, so long runs take longer. */
const RUN_SPEED = 0.58;

/** Idle pulse, once the board is up. */
const PULSE_PERIOD = 4200;
const PULSE_SPAN = 22;   // % of the period the pulse is travelling
const PULSE_STAGGER = 700;

const THEMES = {
  dark: {
    base: "#273040", trace: "#818CF8", viaFill: "#0D1117",
    pulse: "#A5F3FC", glow: true,
  },
  light: {
    base: "#D5DBE3", trace: "#5B4BD6", viaFill: "#FFFFFF",
    pulse: "#0E7490", glow: false,
  },
};

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
  // visible source rather than starting nowhere.
  const lead = 26;
  // Both leads sit on the baseline so the mark reads as one rail running
  // through it; entering low and leaving high looked like a stray stub.
  runs.unshift([[-lead, CELL_H], [0, CELL_H]]);
  runs.push([[width, CELL_H], [width + lead, CELL_H]]);
  return { runs, width, lead };
}

const { runs, width, lead } = layout();

// One via per distinct run endpoint - shared corners get a single pad.
const seen = new Set();
const vias = [];
for (const pts of runs) {
  for (const p of [pts[0], pts[pts.length - 1]]) {
    const k = p.join();
    if (!seen.has(k)) { seen.add(k); vias.push(p); }
  }
}

const span = width + lead;
const phase = (x) => ((x + lead) / span) * SWEEP_MS;

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
  x: -PAD - lead,
  y: -PAD,
  w: width + lead * 2 + PAD * 2,
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
    .map(
      ([x], i) =>
        `.v${i}{animation:pad 320ms ease-out ${r1(phase(x) + 110)}ms forwards}`
    )
    .join("\n    ");

  const base = plan.map((s) => `<path d="${s.d}"/>`).join("");
  const power = plan.map((s, i) => `<path class="t${i}" d="${s.d}"/>`).join("");
  const pulse = plan
    .map((s, i) => `<path class="u${i}" pathLength="100" d="${s.d}"/>`)
    .join("");
  const pads = vias
    .map(([x, y], i) => `<circle class="v${i}" cx="${x}" cy="${y}" r="${VIA_R}"/>`)
    .join("");

  const glow = t.glow
    ? `<filter id="glow" x="-30%" y="-70%" width="160%" height="240%">
      <feGaussianBlur stdDeviation="3" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>`
    : "";
  const glowAttr = t.glow ? ' filter="url(#glow)"' : "";

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${VB.x} ${VB.y} ${VB.w} ${VB.h}" width="${VB.w}" height="${VB.h}" role="img" aria-label="Nikhil Kolli">
  <title>Nikhil Kolli</title>
  <defs>${glow}</defs>
  <style>
    .l{fill:none;stroke-width:${TRACE_W};stroke-linecap:round;stroke-linejoin:round}
    .base{stroke:${t.base}}
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
    ${viaCss}
    @media (prefers-reduced-motion:reduce){
      path,circle{animation:none!important}
      .pwr path{stroke-dashoffset:0!important}
      .pls{display:none!important}
      .via circle{opacity:1!important}
    }
  </style>
  <g class="l base">${base}</g>
  <g class="l pwr"${glowAttr}>${power}</g>
  <g class="l pls">${pulse}</g>
  <g class="via">${pads}</g>
</svg>
`;
}

for (const [name, t] of Object.entries(THEMES)) {
  writeFileSync(join(here, `circuit-${name}.svg`), render(t));
}

const total = Math.max(...plan.map((s) => s.delay + s.dur));
console.log(`viewBox ${VB.x} ${VB.y} ${VB.w} ${VB.h}`);
console.log(`${plan.length} runs, ${vias.length} vias`);
console.log(`power-up ${(total / 1000).toFixed(2)}s, then a ${(PULSE_PERIOD / 1000).toFixed(1)}s pulse loop`);
