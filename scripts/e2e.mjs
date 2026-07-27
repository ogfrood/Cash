/**
 * End-to-end smoke test.
 *
 * Walks the app the way a real user would: creates a caixinha, a debt, a
 * conta, records a salary, adds an adhoc entry, edits things, deletes
 * things, tweaks settings. Grabs a screenshot at each key step so failures
 * are visible. Fails loudly on 404s and on unhandled server errors.
 */
import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const BASE = "http://localhost:3000";
const OUT = resolve("data/e2e");
await mkdir(OUT, { recursive: true });

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

const errors = [];
const consoleErrs = [];
const pageErrs = [];
const badResponses = [];

page.on("console", (m) => {
  if (m.type() === "error") consoleErrs.push(`[console] ${m.text()}`);
});
page.on("pageerror", (e) => pageErrs.push(`[pageerror] ${e.message}`));
page.on("response", (r) => {
  const u = r.url();
  if (!u.startsWith(BASE)) return;
  const s = r.status();
  // Ignore Next.js internal dev routes and hot-reload endpoints.
  if (
    s >= 400 &&
    !u.includes("/_next/") &&
    !u.includes("__nextjs") &&
    !u.includes("favicon")
  ) {
    badResponses.push(`${s} ${u}`);
  }
});

const shots = [];
let step = 0;

async function snap(name) {
  step += 1;
  const file = resolve(OUT, `${String(step).padStart(2, "0")}-${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  shots.push(file);
  console.log(`   📸 ${file}`);
}

async function goto(path, name) {
  console.log(`\n→ GET ${path}`);
  const resp = await page.goto(`${BASE}${path}`, {
    waitUntil: "networkidle",
    timeout: 30_000,
  });
  if (!resp) throw new Error(`no response for ${path}`);
  console.log(`   ← ${resp.status()}`);
  if (resp.status() >= 400) errors.push(`GET ${path} → ${resp.status()}`);
  await page.waitForTimeout(200);
  await snap(name);
  return resp;
}

async function openAllDetails() {
  // Server actions re-render the tree, which resets `<details open>` state.
  // Force everything open before we try to interact with fields inside.
  await page.evaluate(() =>
    document.querySelectorAll("details").forEach((d) => (d.open = true)),
  );
  await page.waitForTimeout(120);
}

/**
 * `<details>` toggling via `summary.click()` is finicky in Playwright — the
 * click sometimes doesn't fire the browser's default toggle. Set `open`
 * directly for reliability.
 */
async function openBySummary(text) {
  await page.evaluate((t) => {
    for (const s of document.querySelectorAll("details > summary")) {
      if (s.textContent?.includes(t)) {
        (s.parentElement).open = true;
      }
    }
  }, text);
  await page.waitForTimeout(120);
}

async function assertText(text, name) {
  const found = await page.getByText(text, { exact: false }).count();
  if (found === 0) {
    errors.push(`${name}: text "${text}" not found`);
    console.log(`   ❌ expected text "${text}" not found`);
  } else {
    console.log(`   ✓ text "${text}" present (${found})`);
  }
}

// ---------------------------------------------------------------------
// 1. Empty painel
// ---------------------------------------------------------------------
await goto("/", "painel-vazio");
await assertText("Regista o salário", "painel-empty-cta");

// ---------------------------------------------------------------------
// 2. Set weekly salary via the manual card
// ---------------------------------------------------------------------
console.log("\n→ setting manual weekly net = 1200");
await openAllDetails();
await page.fill('input[name="amount"]', "1200,00");
await Promise.all([
  page.waitForLoadState("networkidle"),
  page.click('button:has-text("Guardar salário da semana")'),
]);
await snap("painel-com-salario");
await assertText("AU$ 1.200,00", "painel-salary-shown");
await assertText("FLUXO DO SALÁRIO", "painel-cashflow-visible");

// ---------------------------------------------------------------------
// 3. Create a caixinha
// ---------------------------------------------------------------------
await goto("/caixinhas", "caixinhas-vazias");
// The "Livre" overflow bucket is always seeded. Assert.
await assertText("Livre", "caixinhas-overflow-present");
// Open the new-bucket card
console.log("\n→ creating caixinha 'Viagem Japão'");
await openBySummary("Nova caixinha");
await page.waitForTimeout(200);
// Fill the create form (there are multiple `name` inputs on the page; scope
// to the open `details` element).
const newForm = page.locator('details:has(summary:has-text("Nova caixinha"))');
await newForm.locator('input[name="emoji"]').fill("✈️");
await newForm.locator('input[name="name"]').fill("Viagem Japão");
await newForm.locator('select[name="kind"]').selectOption("goal");
await newForm.locator('input[name="targetAmount"]').fill("3000,00");
await newForm.locator('select[name="ruleType"]').selectOption("percent");
await newForm.locator('input[name="ruleValue"]').fill("25");
await Promise.all([
  page.waitForLoadState("networkidle"),
  newForm.locator('button:has-text("Criar caixinha")').click(),
]);
await snap("caixinhas-com-viagem");
await assertText("Viagem Japão", "caixinha-created");
await assertText("de AU$ 3.000,00", "caixinha-target-shown");

// ---------------------------------------------------------------------
// 4. Adjust that caixinha (+ 150)
// ---------------------------------------------------------------------
console.log("\n→ adjusting caixinha with +150");
await openBySummary("Viagem Japão");
await page.waitForTimeout(200);
const viagem = page.locator('details:has(summary:has-text("Viagem Japão"))');
await viagem.locator('input[name="amount"]').fill("150,00");
await Promise.all([
  page.waitForLoadState("networkidle"),
  viagem.locator('button:has-text("Registar")').click(),
]);
await snap("caixinha-com-saldo");
await assertText("AU$ 150,00", "caixinha-balance-set");

// ---------------------------------------------------------------------
// 5. Edit the caixinha (change target to 2500)
// ---------------------------------------------------------------------
console.log("\n→ editing caixinha target -> 2500");
await openBySummary("Viagem Japão");
await page.waitForTimeout(200);
const viagem2 = page.locator('details:has(summary:has-text("Viagem Japão"))');
await viagem2.locator('input[name="targetAmount"]').fill("2500,00");
await Promise.all([
  page.waitForLoadState("networkidle"),
  viagem2.locator('button:has-text("Guardar")').first().click(),
]);
await snap("caixinha-editada");
await assertText("de AU$ 2.500,00", "caixinha-target-updated");

// ---------------------------------------------------------------------
// 6. Create a fixed expense
// ---------------------------------------------------------------------
await goto("/contas", "contas-vazias");
console.log("\n→ creating expense 'Aluguel' 1600/mês");
await openBySummary("Nova conta");
await page.waitForTimeout(200);
const newExp = page.locator('details:has(summary:has-text("Nova conta"))');
await newExp.locator('input[name="name"]').fill("Aluguel");
await newExp.locator('input[name="amount"]').fill("1600,00");
await newExp.locator('select[name="cadence"]').selectOption("monthly");
// keep the pre-filled date
await Promise.all([
  page.waitForLoadState("networkidle"),
  newExp.locator('button:has-text("Criar conta")').click(),
]);
await snap("contas-com-aluguel");
await assertText("Aluguel", "expense-created");

// ---------------------------------------------------------------------
// 7. Create a debt
// ---------------------------------------------------------------------
await goto("/dividas", "dividas-vazias");
console.log("\n→ creating debt 'Cartão ANZ' 2400");
await openBySummary("Nova dívida");
await page.waitForTimeout(200);
const newDebt = page.locator('details:has(summary:has-text("Nova dívida"))');
await newDebt.locator('input[name="emoji"]').fill("💳");
await newDebt.locator('input[name="name"]').fill("Cartão ANZ");
await newDebt.locator('input[name="principal"]').fill("2400,00");
await newDebt.locator('input[name="dailyTarget"]').fill("10,00");
await Promise.all([
  page.waitForLoadState("networkidle"),
  newDebt.locator('button:has-text("Criar dívida")').click(),
]);
await snap("dividas-com-cartao");
await assertText("Cartão ANZ", "debt-created");
await assertText("de AU$ 2.400,00", "debt-principal-shown");

// ---------------------------------------------------------------------
// 8. Register a payment on that debt
// ---------------------------------------------------------------------
console.log("\n→ registering debt payment 200");
await openBySummary("Cartão ANZ");
await page.waitForTimeout(200);
const debt = page.locator('details:has(summary:has-text("Cartão ANZ"))');
await debt.locator('input[name="amount"]').fill("200,00");
await Promise.all([
  page.waitForLoadState("networkidle"),
  debt.locator('button:has-text("Adicionar pagamento")').click(),
]);
await snap("dividas-com-pagamento");
await assertText("AU$ 2.200,00", "debt-balance-after-payment");

// ---------------------------------------------------------------------
// 9. Change tax settings
// ---------------------------------------------------------------------
await goto("/config", "config-inicial");
console.log("\n→ changing super to 12.5");
const taxForm = page.locator('details:has(summary:has-text("Estatuto fiscal"))');
await taxForm.locator('input[name="superPercent"]').fill("12,5");
await Promise.all([
  page.waitForLoadState("networkidle"),
  taxForm.locator('button:has-text("Guardar")').click(),
]);
await snap("config-super-125");
await assertText("Super 12,5%", "config-super-updated");

// ---------------------------------------------------------------------
// 10. Adhoc income
// ---------------------------------------------------------------------
await goto("/avulso/novo", "avulso-form");
console.log("\n→ creating adhoc entry 150 informal");
await page.fill('input[name="amount"]', "150,00");
await page.selectOption('select[name="kind"]', "informal");
await page.fill('input[name="source"]', "Turno coberto");
await page.click('button:has-text("Guardar")');
// Server actions redirect via next/navigation; wait for the URL change instead
// of relying on networkidle (which can settle before the client-side
// navigation completes).
await page.waitForURL(`${BASE}/`, { timeout: 10_000 }).catch(() => {});
await page.waitForLoadState("networkidle");
await snap("painel-com-avulso");
await assertText("AU$ 1.350,00", "adhoc-added-to-income");

// ---------------------------------------------------------------------
// 11. Painel now has everything — allocation should display
// ---------------------------------------------------------------------
await goto("/", "painel-completo");
await assertText("Alocação prevista", "painel-allocation-shown");
await assertText("Viagem Japão", "painel-shows-bucket");

// ---------------------------------------------------------------------
// 12. Turnos page (still stub) — must NOT 404
// ---------------------------------------------------------------------
await goto("/turnos", "turnos");
await assertText("Turnos", "turnos-loaded");

// ---------------------------------------------------------------------
// 13. Delete the caixinha we created
// ---------------------------------------------------------------------
await goto("/caixinhas", "caixinhas-antes-delete");
console.log("\n→ deleting caixinha Viagem Japão");
await openBySummary("Viagem Japão");
await page.waitForTimeout(200);
const viagemDel = page.locator('details:has(summary:has-text("Viagem Japão"))');
// deleteBucket triggers a redirect back to /caixinhas
await viagemDel.locator('button:has-text("Apagar caixinha")').click();
await page.waitForTimeout(1500);
await page.reload({ waitUntil: "networkidle" });
await snap("caixinhas-apos-delete");
const stillHas = await page.getByText("Viagem Japão").count();
if (stillHas > 0) {
  errors.push("bucket 'Viagem Japão' still visible after delete");
  console.log("   ❌ delete did not remove bucket");
} else {
  console.log("   ✓ bucket deleted");
}

// ---------------------------------------------------------------------
// 14. Bad URL should 404 (deliberately hit a non-existent route)
// ---------------------------------------------------------------------
console.log("\n→ deliberate 404 check");
const bad = await page.goto(`${BASE}/nao-existe`, {
  waitUntil: "domcontentloaded",
});
if (bad && bad.status() === 404) {
  console.log("   ✓ 404 handler responds");
} else {
  console.log(`   ! unexpected status ${bad?.status()} — should be 404`);
}
// Drop this out of `badResponses` — we EXPECTED a 404 for this URL.
const filteredBad = badResponses.filter((r) => !r.endsWith("/nao-existe"));

// ---------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------
await browser.close();

const report = {
  errors,
  consoleErrs,
  pageErrs,
  badResponses: filteredBad,
  shotCount: shots.length,
};
await writeFile(resolve(OUT, "report.json"), JSON.stringify(report, null, 2));

console.log("\n────────────── RESULTADO ──────────────");
console.log(`Screenshots:      ${shots.length}`);
console.log(`Assertion fails:  ${errors.length}`);
console.log(`Console errors:   ${consoleErrs.length}`);
console.log(`Page errors:      ${pageErrs.length}`);
console.log(`HTTP >=400:       ${filteredBad.length}`);
if (errors.length) {
  console.log("\nAssertion fails:");
  for (const e of errors) console.log("  -", e);
}
if (consoleErrs.length) {
  console.log("\nConsole errors:");
  for (const e of consoleErrs.slice(0, 12)) console.log("  -", e);
}
if (pageErrs.length) {
  console.log("\nPage errors:");
  for (const e of pageErrs) console.log("  -", e);
}
if (filteredBad.length) {
  console.log("\nBad HTTP responses:");
  for (const r of filteredBad) console.log("  -", r);
}

const failed =
  errors.length + pageErrs.length + filteredBad.length > 0;
console.log(failed ? "\n❌ FAIL" : "\n✅ PASS");
process.exit(failed ? 1 : 0);
