/**
 * Draws "NIKHIL KOLLI" as board routing and animates the board powering up,
 * then rippling.
 *
 *   node assets/build-circuit.mjs
 *
 * The letterforms are polylines constrained to 90 and 45 degrees, which is the
 * rule real trace routing works to - no arbitrary angles. That constraint is
 * the whole idea: the mark is legible as a name and correct as a layout, rather
 * than a typeface with a circuit texture laid over it.
 *
 * Three things make it read as a board rather than a diagram, and all three sit
 * on the letterforms. An earlier attempt put detail *behind* the name instead -
 * background nets, a ground grid, silkscreen - and that was just clutter.
 *
 *  1. The traces are physical. A dark copy offset downward is the shadow they
 *     cast, a vertical gradient lights them from above, and a thin bright copy
 *     offset upward is the specular along the top edge. Together the strokes
 *     read as metal sitting proud of the substrate.
 *
 *  2. Pads go where something actually connects. One at every stroke end gave
 *     51 of them and the mark read as beads on a string. A junction is where
 *     two runs share an endpoint, or where one ends while another passes
 *     through - the T-joins, which endpoint-sharing alone misses entirely.
 *     That is 15 pads, in gold against the violet.
 *
 *  3. Real footprints sit inline in the strokes, genuinely splitting the run
 *     they sit on so the trace is interrupted the way a component interrupts a
 *     net, rather than being drawn on top of an unbroken line.
 *
 * Two deliberate choices are both about rendering the same on any machine:
 *
 *  - No SVG filters. The glow used to be an feGaussianBlur over the animated
 *    group, which is exactly the case renderers disagree on: a filtered group
 *    whose children animate has to re-run the filter every frame, and support
 *    for that inside an img element is the least consistent thing here.
 *    Gradients and offset strokes are plain geometry every renderer agrees on.
 *
 *  - No SMIL, only CSS, so behaviour does not depend on which of the two a
 *    given renderer implements more completely inside an img element. Only
 *    opacity and stroke-dashoffset animate - not the SVG `r` geometry property,
 *    which is a much newer thing for CSS to be allowed to touch.
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
const PAD_R = 7.4;   // junction pad radius
const DRILL_R = 3;   // via hole

/** How far the copper sits above its shadow, and the specular above that. */
const LIFT = 2.4;
const SPEC_RISE = 1.7;

/** Two pads closer than this merge into a blob, so only one is kept. */
const MIN_PAD_GAP = 20;

/** Gap a component opens in the trace it sits on. */
const PART_GAP = 22;
const PART_COUNT = 5;
const PART_KINDS = ["R", "C", "R", "D", "C"];

/** Power-up: the front crosses the whole word in this long. */
const SWEEP_MS = 1500;
/** Trace units per ms once a run is lit, so long runs take longer. */
const RUN_SPEED = 0.58;

/* ----------------------------------------------------------------- ripple */
const RIPPLE_PERIOD = 3800;
const RIPPLE_TRAVEL = 1100;
const RIPPLE_FLASH = 820;
const RIPPLE_GAP = 420;

/**
 * Whether to hold the mark still for `prefers-reduced-motion: reduce`.
 *
 * Off by design. That query is answered by the OS, and inside an SVG loaded
 * through an img element it is read from the OS even when the surrounding page
 * reports otherwise - so honouring it left the mark frozen on any machine with
 * Windows animation effects switched off, which is a common default rather than
 * necessarily a request for stillness. Flip this to true to restore the guard.
 *
 * What makes that defensible rather than merely convenient: the motion is a
 * thin line lighting up, then a low-contrast brightness wave with long quiet
 * gaps. No large-area movement, parallax, zoom or flashing.
 */
const RESPECT_REDUCED_MOTION = false;

const THEMES = {
  dark: {
    bg: "#0D1117",
    cuTop: "#C7D2FE", cuMid: "#818CF8", cuBot: "#4C51BF",
    shadow: "#080B11", shadowOp: 0.85,
    spec: "#EEF2FF", specOp: 0.5,
    goldTop: "#FDE68A", goldMid: "#D9A520", goldBot: "#946C0B",
    partBody: "#141A26", partEdge: "#A5B4FC",
    // Partial, not opaque: a solid white wave over flat violet read as a
    // highlight, but over the copper it just erases the metal underneath.
    ripple: "#EEF2FF", rippleOp: 0.62, rippleHalo: 0.2,
  },
  light: {
    bg: "#FFFFFF",
    cuTop: "#8B7DEC", cuMid: "#5B4BD6", cuBot: "#332A8F",
    // A black shadow on white reads as dirt; a cool grey reads as contact.
    shadow: "#AAB2C0", shadowOp: 0.55,
    spec: "#FFFFFF", specOp: 0.55,
    goldTop: "#F5C842", goldMid: "#C08A0E", goldBot: "#7A5606",
    partBody: "#E8EBF2", partEdge: "#5B4BD6",
    // On white a brighter ripple would read as fading out, so it goes deeper.
    ripple: "#1E1B4B", rippleOp: 0.5, rippleHalo: 0.12,
  },
};

const RIPPLE_HALO_GROW = 16;
const RIPPLE_GROW = 1.5;

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
const centroid = (pts) => [
  pts.reduce((a, p) => a + p[0], 0) / pts.length,
  pts.reduce((a, p) => a + p[1], 0) / pts.length,
];

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
  return { runs, width: x - (ADVANCE - CELL_W) };
}

const { runs: rawRuns, width } = layout();

/* -------------------------------------------------------------- junctions */
const eq = (a, b) => Math.abs(a[0] - b[0]) < 0.01 && Math.abs(a[1] - b[1]) < 0.01;

/** True when p lies strictly inside segment a-b, i.e. a T-join not an endpoint. */
function interior(p, a, b) {
  const cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]);
  if (Math.abs(cross) > 0.01) return false;
  const dot = (p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1]);
  const len2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2;
  return dot > 0.01 && dot < len2 - 0.01;
}

function findJunctions(list) {
  const seen = new Set();
  const ends = [];
  for (const pts of list)
    for (const p of [pts[0], pts[pts.length - 1]]) {
      const k = p.join();
      if (!seen.has(k)) { seen.add(k); ends.push(p); }
    }

  const hits = [];
  for (const p of ends) {
    let e = 0;
    let through = 0;
    for (const pts of list) {
      if (eq(pts[0], p) || eq(pts[pts.length - 1], p)) e++;
      for (let k = 1; k < pts.length; k++)
        if (interior(p, pts[k - 1], pts[k])) { through++; break; }
    }
    if (e >= 2 || (e >= 1 && through >= 1)) hits.push(p);
  }

  // Drop neighbours too close to sit as separate pads - the K's stem join and
  // arm join are 15 apart against a 14.8 pad, which renders as one blob.
  const kept = [];
  for (const p of hits)
    if (!kept.some((q) => Math.hypot(q[0] - p[0], q[1] - p[1]) < MIN_PAD_GAP)) kept.push(p);
  return kept;
}

const junctions = findJunctions(rawRuns);

/* ------------------------------------------------------------- components */
/**
 * Parts go on the long horizontal runs, spread evenly across the name, and
 * split the run they sit on so the trace is genuinely interrupted rather than
 * overdrawn. Junctions are found before this runs, so the new endpoints the
 * split creates are never mistaken for connection points.
 */
function placeParts(list) {
  const eligible = [];
  list.forEach((pts, i) => {
    if (pts.length !== 2) return;
    if (pts[0][1] !== pts[1][1]) return;
    if (Math.abs(pts[1][0] - pts[0][0]) < PART_GAP + 18) return;
    eligible.push(i);
  });

  const chosen = new Map();
  const n = Math.min(PART_COUNT, eligible.length);
  for (let k = 0; k < n; k++) {
    const idx = eligible[Math.round((k * (eligible.length - 1)) / Math.max(1, n - 1))];
    if (!chosen.has(idx)) chosen.set(idx, PART_KINDS[k % PART_KINDS.length]);
  }

  const out = [];
  const parts = [];
  list.forEach((pts, i) => {
    if (!chosen.has(i)) { out.push(pts); return; }
    const [[x0, y0], [x1]] = pts;
    const mid = (x0 + x1) / 2;
    const dir = Math.sign(x1 - x0);
    out.push([[x0, y0], [r1(mid - (PART_GAP / 2) * dir), y0]]);
    out.push([[r1(mid + (PART_GAP / 2) * dir), y0], [x1, y0]]);
    parts.push({ x: r1(mid), y: y0, kind: chosen.get(i) });
  });
  return { runs: out, parts };
}

const { runs, parts } = placeParts(rawRuns);

/* ----------------------------------------------------------------- timing */
const phase = (x) => (x / width) * SWEEP_MS;

const plan = runs.map((pts) => {
  const len = lenOf(pts);
  return {
    d: dOf(pts),
    len,
    at: centroid(pts),
    delay: phase(pts[0][0]),
    dur: Math.max(180, len / RUN_SPEED),
  };
});

const POWER_END = Math.max(...plan.map((s) => s.delay + s.dur));

// The ripple radiates from the mark's bottom-left, where the power-up sweep
// also begins, so the two motions read as coming from the same place.
const ORIGIN = [0, CELL_H];
const distFrom = ([x, y]) => Math.hypot(x - ORIGIN[0], y - ORIGIN[1]);
const MAX_DIST = Math.max(
  ...plan.map((s) => distFrom(s.at)),
  ...junctions.map((v) => distFrom(v))
);
const rippleAt = (pt) =>
  POWER_END + RIPPLE_GAP + (distFrom(pt) / MAX_DIST) * RIPPLE_TRAVEL;

const RISE_PCT = r1(((RIPPLE_FLASH * 0.32) / RIPPLE_PERIOD) * 100);
const FALL_PCT = r1((RIPPLE_FLASH / RIPPLE_PERIOD) * 100);

const VB = { x: -PAD, y: -PAD, w: width + PAD * 2, h: CELL_H + PAD * 2 };

/**
 * An SVG served as image/svg+xml is parsed as XML, so a bare "<" or "&"
 * anywhere in the stylesheet is a parse error and the whole mark fails to
 * render - silently, as a broken-image icon. Writing an img tag in a CSS
 * comment did exactly that once. Comparing rendered bytes did not catch it
 * either, because two identical broken-image icons compare equal.
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

function render(t) {
  const paths = plan.map((s, i) => `<path class="t${i}" d="${s.d}"/>`).join("");
  const ripple = plan.map((s, i) => `<path class="r${i}" d="${s.d}"/>`).join("");

  const powerCss = plan
    .map(
      (s, i) =>
        `.t${i}{stroke-dasharray:${r1(s.len)};stroke-dashoffset:${r1(s.len)};` +
        `animation:up ${r1(s.dur)}ms cubic-bezier(.3,.7,.4,1) ${r1(s.delay)}ms forwards}`
    )
    .join("\n    ");

  // Phase only - one period for every element, so the ripple stays a single
  // wave crossing the board instead of drifting apart over time.
  const rippleCss = plan
    .map((s, i) => `.r${i}{animation:rip ${RIPPLE_PERIOD}ms linear ${r1(rippleAt(s.at))}ms infinite}`)
    .join("\n    ");

  const padCss = junctions
    .map(([x], i) => `.v${i}{animation:pad 320ms ease-out ${r1(phase(x) + 110)}ms forwards}`)
    .join("\n    ");
  const partCss = parts
    .map((c, i) => `.c${i}{animation:pad 320ms ease-out ${r1(phase(c.x) + 150)}ms forwards}`)
    .join("\n    ");

  // Shadow, drilled gold pad, hole - grouped so one opacity drives all three.
  const padMarkup = junctions
    .map(
      ([x, y], i) =>
        `<g class="v${i}">` +
        `<circle cx="${x}" cy="${r1(y + LIFT)}" r="${PAD_R}" fill="${t.shadow}" opacity="${t.shadowOp}"/>` +
        `<circle cx="${x}" cy="${y}" r="${PAD_R}" fill="url(#au)"/>` +
        `<circle cx="${x}" cy="${y}" r="${DRILL_R}" fill="${t.bg}" opacity="0.85"/>` +
        `</g>`
    )
    .join("");

  const partBody = (c) => {
    if (c.kind === "D")
      return `<rect x="${r1(c.x - 6.5)}" y="${r1(c.y - 5)}" width="13" height="10" rx="1.2" fill="${t.partBody}" stroke="${t.partEdge}" stroke-width="1.1"/>` +
             `<rect x="${r1(c.x + 3.4)}" y="${r1(c.y - 5)}" width="2.4" height="10" fill="${t.partEdge}"/>`;
    if (c.kind === "C")
      return `<rect x="${r1(c.x - 5.4)}" y="${r1(c.y - 6)}" width="10.8" height="12" rx="1.2" fill="${t.partBody}" stroke="${t.partEdge}" stroke-width="1.1"/>`;
    return `<rect x="${r1(c.x - 7)}" y="${r1(c.y - 5)}" width="14" height="10" rx="1.2" fill="${t.partBody}" stroke="${t.partEdge}" stroke-width="1.2"/>`;
  };

  const partMarkup = parts
    .map(
      (c, i) =>
        `<g class="c${i}">` +
        `<rect x="${r1(c.x - 12)}" y="${r1(c.y - 5.6)}" width="6.4" height="11.2" rx="1.3" fill="url(#au)"/>` +
        `<rect x="${r1(c.x + 5.6)}" y="${r1(c.y - 5.6)}" width="6.4" height="11.2" rx="1.3" fill="url(#au)"/>` +
        partBody(c) +
        `</g>`
    )
    .join("");

  const guard = RESPECT_REDUCED_MOTION
    ? `
    @media (prefers-reduced-motion:reduce){
      path,g{animation:none!important}
      .sh path,.cu path,.sp path{stroke-dashoffset:0!important}
      .rip,.riph{display:none!important}
      .pads g,.parts g{opacity:1!important}
    }`
    : `
    /* No prefers-reduced-motion guard, on purpose - see RESPECT_REDUCED_MOTION
       in the build script. Inside an img element that query reports the OS
       setting regardless of the host page, so honouring it froze the mark on
       any machine with Windows animation effects off. */`;

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${VB.x} ${VB.y} ${VB.w} ${VB.h}" width="${VB.w}" height="${VB.h}" role="img" aria-label="Nikhil Kolli">
  <title>Nikhil Kolli</title>
  <defs>
    <linearGradient id="cu" gradientUnits="userSpaceOnUse" x1="0" y1="${VB.y}" x2="0" y2="${r1(VB.y + VB.h)}">
      <stop offset="0" stop-color="${t.cuTop}"/>
      <stop offset="0.42" stop-color="${t.cuMid}"/>
      <stop offset="1" stop-color="${t.cuBot}"/>
    </linearGradient>
    <linearGradient id="au" gradientUnits="objectBoundingBox" x1="0.15" y1="0" x2="0.85" y2="1">
      <stop offset="0" stop-color="${t.goldTop}"/>
      <stop offset="0.5" stop-color="${t.goldMid}"/>
      <stop offset="1" stop-color="${t.goldBot}"/>
    </linearGradient>
  </defs>
  <style>
    .l{fill:none;stroke-linecap:round;stroke-linejoin:round}
    .sh{stroke:${t.shadow};stroke-width:${TRACE_W + 1};opacity:${t.shadowOp}}
    .cu{stroke:url(#cu);stroke-width:${TRACE_W}}
    .sp{stroke:${t.spec};stroke-width:${r1(TRACE_W * 0.26)};opacity:${t.specOp}}
    .rip{stroke:${t.ripple};stroke-width:${TRACE_W + RIPPLE_GROW};opacity:${t.rippleOp}}
    .riph{stroke:${t.ripple};stroke-width:${TRACE_W + RIPPLE_HALO_GROW};opacity:${t.rippleHalo}}
    .rip path,.riph path{opacity:0}
    /* opacity has to sit on each group: it is not inherited, so hiding the
       parent instead would leave the per-pad fade-ins animating nothing. */
    .pads g,.parts g{opacity:0}
    @keyframes up{to{stroke-dashoffset:0}}
    @keyframes pad{to{opacity:1}}
    @keyframes rip{
      0%{opacity:0}
      ${RISE_PCT}%{opacity:1}
      ${FALL_PCT}%{opacity:0}
      100%{opacity:0}
    }
    ${powerCss}
    ${rippleCss}
    ${padCss}
    ${partCss}${guard}
  </style>
  <g class="l sh" transform="translate(0 ${LIFT})">${paths}</g>
  <g class="l cu">${paths}</g>
  <g class="l sp" transform="translate(0 -${SPEC_RISE})">${paths}</g>
  <g class="l riph">${ripple}</g>
  <g class="l rip">${ripple}</g>
  <g class="pads">${padMarkup}</g>
  <g class="parts">${partMarkup}</g>
</svg>
`;
}

for (const [name, t] of Object.entries(THEMES)) {
  const svg = render(t);
  validate(svg, `circuit-${name}.svg`);
  writeFileSync(join(here, `circuit-${name}.svg`), svg);
}

console.log(`viewBox ${VB.x} ${VB.y} ${VB.w} ${VB.h}`);
console.log(`${runs.length} runs, ${junctions.length} junction pads, ${parts.length} parts`);
console.log(`power-up ${(POWER_END / 1000).toFixed(2)}s, ripple every ${(RIPPLE_PERIOD / 1000).toFixed(1)}s`);
console.log(`reduced-motion guard: ${RESPECT_REDUCED_MOTION ? "on" : "off"}`);
