/**
 * Render the app in a phone-shaped Chromium and save PNGs.
 *
 * We take TWO shots per page:
 *  - viewport-only (`_top.png`)   → tab bar sits at the bottom, as intended
 *  - full-page  (`_full.png`)     → all content, with tab bar hidden via CSS
 *                                    injection so it does not appear mid-page
 */
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const OUT = resolve("data/screenshots");
await mkdir(OUT, { recursive: true });

const pages = [
  { path: "/", name: "01-painel" },
  { path: "/caixinhas", name: "02-caixinhas" },
  { path: "/dividas", name: "03-dividas" },
  { path: "/contas", name: "04-contas" },
  { path: "/dividas/nova", name: "05-nova-divida" },
  { path: "/avulso/novo", name: "06-avulso" },
];

const browser = await chromium.launch({
  executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const ctx = await browser.newContext({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
  colorScheme: "dark",
});
const page = await ctx.newPage();

for (const p of pages) {
  const url = `http://localhost:3000${p.path}`;
  console.log(`→ ${url}`);
  await page.goto(url, { waitUntil: "networkidle", timeout: 30_000 });
  await page.waitForTimeout(400);

  // 1) viewport shot — with tab bar visible
  const top = resolve(OUT, `${p.name}_top.png`);
  await page.screenshot({ path: top, fullPage: false });
  console.log(`   saved ${top}`);

  // 2) full-page shot — hide the fixed tab bar first so it does not float
  // in the middle of the frame.
  await page.addStyleTag({ content: ".tabbar{display:none!important;}" });
  const full = resolve(OUT, `${p.name}_full.png`);
  await page.screenshot({ path: full, fullPage: true });
  console.log(`   saved ${full}`);
}

await browser.close();
console.log("done");
