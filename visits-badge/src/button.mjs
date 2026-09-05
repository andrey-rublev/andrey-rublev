/**
 * Draws the header buttons as SVG.
 *
 * Shared deliberately: the static link buttons are generated into assets/ at
 * build time and the two counters are rendered live by the Worker. Both import
 * this, so the set cannot drift out of sync.
 *
 * Layout is computed rather than measured. GitHub strips external CSS from
 * proxied SVG, so no web font can load — the text is set in a monospace stack
 * where every glyph advances the same width, which makes the arithmetic exact
 * instead of an estimate. That is also why these read as a set with the
 * JetBrains Mono banner above them.
 */

const FONT = "ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono',monospace";

const H = 34;
const R = 9;
const FS = 12;

/** Monospace advance is ~0.6em; a touch over avoids clipping on wider faces. */
const ADV = FS * 0.605;

const PAD = 14;
const ICON = 14;
const GAP_ICON = 9;
const GAP_MID = 12;

const THEME = {
  bg: "#1B2029",
  border: "#30363D",
  icon: "#818CF8",
  label: "#8B949E",
  value: "#E6EDF3",
  accent: "#A5B4FC",
};

export const ICONS = {
  linkedin:
    "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z",
  github:
    "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12",
  vercel: "M24 22.525H0l12-21.05 12 21.05z",
};

const esc = (s) =>
  String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/**
 * @param {object} o
 * @param {string} [o.icon]    key of ICONS
 * @param {string} o.label     muted left text
 * @param {string} o.value     bright right text
 * @param {boolean} [o.accent] tint the value with the accent colour
 * @param {string} [o.title]   accessible name
 */
export function button({ icon, label, value, accent = false, title }) {
  const labelW = label.length * ADV;
  const valueW = value.length * ADV;
  const iconW = icon ? ICON + GAP_ICON : 0;
  const w = Math.ceil(PAD + iconW + labelW + GAP_MID + valueW + PAD);

  const iconX = PAD;
  const labelX = PAD + iconW;
  const valueX = labelX + labelW + GAP_MID;
  const baseline = H / 2 + FS * 0.35;

  const iconMarkup = icon
    ? `<g transform="translate(${iconX} ${(H - ICON) / 2}) scale(${ICON / 24})">` +
      `<path fill="${THEME.icon}" d="${ICONS[icon]}"/></g>`
    : "";

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${H}" viewBox="0 0 ${w} ${H}" role="img" aria-label="${esc(title || `${label} ${value}`)}">
  <title>${esc(title || `${label} ${value}`)}</title>
  <rect x="0.5" y="0.5" width="${w - 1}" height="${H - 1}" rx="${R}" fill="${THEME.bg}" stroke="${THEME.border}"/>
  ${iconMarkup}
  <g font-family="${FONT}" font-size="${FS}" dominant-baseline="middle">
    <text x="${labelX}" y="${baseline}" fill="${THEME.label}">${esc(label)}</text>
    <text x="${valueX}" y="${baseline}" fill="${accent ? THEME.accent : THEME.value}" font-weight="600">${esc(value)}</text>
  </g>
</svg>`;
}
