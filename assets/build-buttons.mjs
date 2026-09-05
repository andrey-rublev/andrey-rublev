/**
 * Generates the static header buttons into assets/.
 *
 * Only the two link buttons are built here — the view counters have to be
 * rendered per request, so the Worker draws those from the same module.
 *
 *   node assets/build-buttons.mjs
 */
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { button } from "../visits-badge/src/button.mjs";

const here = dirname(fileURLToPath(import.meta.url));

const BUTTONS = {
  "portfolio.svg": {
    icon: "vercel",
    label: "portfolio",
    title: "Portfolio — nikhilkolli.com",
  },
  "linkedin.svg": {
    icon: "linkedin",
    label: "linkedin",
    title: "LinkedIn — in/nikhilxkolli",
  },
};

mkdirSync(here, { recursive: true });
for (const [name, spec] of Object.entries(BUTTONS)) {
  const svg = button(spec);
  writeFileSync(join(here, name), svg);
  console.log(`${name.padEnd(16)} ${svg.match(/width="(\d+)"/)[1]}x34`);
}
