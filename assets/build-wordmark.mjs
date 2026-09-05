/**
 * Animated wordmark.
 *
 * Monospace on purpose: every glyph advances the same width, so each letter can
 * be positioned exactly without font metrics — which is what makes a staggered
 * per-letter reveal possible at all when no web font may load.
 *
 * Animation is CSS keyframes plus SMIL, both of which run when an SVG is
 * referenced by <img>. No JavaScript: GitHub strips it.
 */
import { writeFileSync } from "node:fs";

const MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono',monospace";
const W = 760, H = 104;
const NAME = "NIKHIL KOLLI";
const FS = 54, ADV = FS * 0.6, TRACK = 4;

const THEMES = {
  dark:  { ink: "#E6EDF3", glow: "#FFFFFF", accent: "#818CF8", kicker: "#7D8590" },
  light: { ink: "#1F2328", glow: "#5B4BD6", accent: "#5B4BD6", kicker: "#6E7781" },
};

function wordmark(t) {
  const step = ADV + TRACK;
  const total = NAME.length * step - TRACK;
  const x0 = (W - total) / 2;
  const baseY = 70;

  const letters = [...NAME].map((ch, i) => {
    if (ch === " ") return "";
    const x = x0 + i * step + ADV / 2;
    return `<text class="l" style="animation-delay:${(i * 55).toFixed(0)}ms" x="${x.toFixed(1)}" y="${baseY}" text-anchor="middle">${ch}</text>`;
  }).join("\n    ");

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Nikhil Kolli">
  <title>Nikhil Kolli</title>
  <defs>
    <linearGradient id="shine" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0.00" stop-color="${t.ink}"/>
      <stop offset="0.42" stop-color="${t.ink}"/>
      <stop offset="0.50" stop-color="${t.glow}"/>
      <stop offset="0.58" stop-color="${t.ink}"/>
      <stop offset="1.00" stop-color="${t.ink}"/>
      <animateTransform attributeName="gradientTransform" type="translate"
        values="-1 0; 1 0" dur="4.5s" begin="1.2s" repeatCount="indefinite"/>
    </linearGradient>
  </defs>
  <style>
    .l {
      font-family: ${MONO};
      font-size: ${FS}px;
      font-weight: 700;
      fill: url(#shine);
      opacity: 0;
      animation: rise .55s cubic-bezier(.2,.8,.2,1) forwards;
    }
    @keyframes rise {
      from { opacity: 0; transform: translateY(10px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    .rule { transform-origin: center; animation: draw .9s cubic-bezier(.2,.8,.2,1) .55s forwards; }
    @keyframes draw { from { transform: scaleX(0); opacity: 0 } to { transform: scaleX(1); opacity: .75 } }
    @media (prefers-reduced-motion: reduce) {
      .l, .rule { animation: none; opacity: 1; }
      .rule { opacity: .75 }
    }
  </style>
  <g>
    ${letters}
  </g>
  <rect class="rule" x="${(W - total) / 2}" y="88" width="${total.toFixed(1)}" height="2" rx="1" fill="${t.accent}" opacity="0"/>
</svg>`;
}

for (const [name, t] of Object.entries(THEMES)) {
  writeFileSync(`name-${name}.svg`, wordmark(t));
  console.log(`name-${name}.svg`);
}
