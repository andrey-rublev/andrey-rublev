/**
 * Generates the static header buttons into assets/, one file per theme.
 *
 * Only the two link buttons are built here — the view counters have to be
 * rendered per request, so the Worker draws those from the same module.
 *
 *   node assets/build-buttons.mjs
 */
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { button, THEMES } from "../visits-badge/src/button.mjs";

const here = dirname(fileURLToPath(import.meta.url));

const BUTTONS = {
  // The portfolio is the main destination, so it takes the accent fill the
  // live-site buttons use on the project cards.
  portfolio: {
    icon: "vercel",
    label: "portfolio",
    variant: "primary",
    title: "Portfolio — nikhilkolli.com",
  },
  linkedin: {
    icon: "linkedin",
    label: "linkedin",
    variant: "solid",
    title: "LinkedIn — in/nikhilxkolli",
  },
};

mkdirSync(here, { recursive: true });
for (const [name, spec] of Object.entries(BUTTONS)) {
  for (const theme of THEMES) {
    const svg = button({ ...spec, theme });
    const file = `${name}-${theme}.svg`;
    writeFileSync(join(here, file), svg);
    console.log(`${file.padEnd(22)} ${svg.match(/width="(\d+)"/)[1]}x34`);
  }
}
