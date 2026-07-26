/**
 * Seed the local DB with a realistic starter set:
 *  - one employer (SOHO Rivermakers ↔ Round Circle Services alias);
 *  - the standard "caixinhas" a hospitality worker in Brisbane needs;
 *  - a handful of recurring fixed costs;
 *  - eight weeks of forecast pay periods and allocation history so the
 *    dashboard chart and bucket progress rings show actual movement.
 *
 * Idempotent-ish: wipes the app-owned tables first, so `npm run db:seed` is
 * always safe to re-run.
 */
import Database from "better-sqlite3";
import { drizzle } from "drizzle-orm/better-sqlite3";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

import * as schema from "../src/db/schema";
import { dollarsToCents } from "../src/lib/money";
import { addLocalDays, weekStart } from "../src/lib/time";

const dbPath = resolve(process.env.DATABASE_PATH ?? "./data/cash.db");
mkdirSync(dirname(dbPath), { recursive: true });
const sqlite = new Database(dbPath);
sqlite.pragma("journal_mode = WAL");
sqlite.pragma("foreign_keys = ON");
const db = drizzle(sqlite, { schema });

// The demo "today" — use a fixed date so screenshots are reproducible.
const TODAY = "2026-07-26";
const THIS_WEEK = weekStart(TODAY);

console.log(`Semeando com hoje = ${TODAY}, semana = ${THIS_WEEK}`);

// -- reset app-owned rows --------------------------------------------------
for (const t of [
  schema.debtPayments,
  schema.debts,
  schema.ledgerEntries,
  schema.allocationRuns,
  schema.expenseOccurrences,
  schema.fixedExpenses,
  schema.adhocIncome,
  schema.payslipLines,
  schema.payslips,
  schema.payPeriods,
  schema.shifts,
  schema.rosterImports,
  schema.emailIngest,
  schema.payRateRules,
  schema.payRateSets,
  schema.employerAliases,
  schema.employers,
  schema.buckets,
  schema.publicHolidays,
  schema.taxSettings,
  schema.appSettings,
]) {
  db.delete(t).run();
}

// -- app settings ----------------------------------------------------------
db.insert(schema.appSettings).values({}).run();

db.insert(schema.taxSettings)
  .values({
    fyLabel: "2026-27",
    status: "WHM",
    superGuaranteeBp: 1200,
    withholdingMethod: "annualised",
  })
  .run();

// -- employer + aliases ----------------------------------------------------
const [{ id: employerId }] = db
  .insert(schema.employers)
  .values({ name: "SOHO Rivermakers" })
  .returning({ id: schema.employers.id })
  .all();

db.insert(schema.employerAliases)
  .values([
    { employerId, matchType: "roster_sender", value: "SOHO Rivermakers Pty Ltd" },
    { employerId, matchType: "payslip_entity", value: "Round Circle Services Pty Ltd" },
    { employerId, matchType: "payslip_entity", value: "GGHRCSR QLD Pty Ltd" },
    { employerId, matchType: "venue", value: "Kiosk & Urban Winery" },
    { employerId, matchType: "venue", value: "Cafe & Resaurant" },
  ])
  .run();

// -- pay rate set (placeholder — Joshua replaces with real per-band $/hr) --
const [{ id: rateSetId }] = db
  .insert(schema.payRateSets)
  .values({
    employerId,
    label: "Casual 2026",
    employmentType: "casual",
    baseRateCents: dollarsToCents("30.00"), // ballpark — to be verified
    effectiveFrom: "2026-07-01",
  })
  .returning({ id: schema.payRateSets.id })
  .all();

db.insert(schema.payRateRules)
  .values([
    { rateSetId, label: "Base", priority: 0, daysMask: 0b1111111, startMinute: 0, endMinute: 1440 },
    { rateSetId, label: "Noturno", priority: 40, daysMask: 0b0011111, startMinute: 19 * 60, endMinute: 1440, multiplierBp: 11000 },
    { rateSetId, label: "Sábado", priority: 60, daysMask: 0b0100000, startMinute: 0, endMinute: 1440, multiplierBp: 12500 },
    { rateSetId, label: "Domingo", priority: 80, daysMask: 0b1000000, startMinute: 0, endMinute: 1440, multiplierBp: 17500 },
    { rateSetId, label: "Feriado", priority: 100, daysMask: 0b1111111, appliesOnPublicHoliday: "only", startMinute: 0, endMinute: 1440, multiplierBp: 22500 },
  ])
  .run();

// -- fixed expenses --------------------------------------------------------
// Sinking buckets come first, then the expenses point at them.
const rentBucket = db
  .insert(schema.buckets)
  .values({
    name: "Aluguel",
    emoji: "🏠",
    kind: "sinking",
    ruleType: "none",
    priority: 5,
    sortIndex: 0,
  })
  .returning({ id: schema.buckets.id })
  .get();

const billsBucket = db
  .insert(schema.buckets)
  .values({
    name: "Contas fixas",
    emoji: "⚡",
    kind: "sinking",
    ruleType: "none",
    priority: 6,
    sortIndex: 1,
  })
  .returning({ id: schema.buckets.id })
  .get();

const subsBucket = db
  .insert(schema.buckets)
  .values({
    name: "Assinaturas",
    emoji: "📺",
    kind: "sinking",
    ruleType: "none",
    priority: 7,
    sortIndex: 2,
  })
  .returning({ id: schema.buckets.id })
  .get();

// Goal buckets — the meat of the app.
const savings = db
  .insert(schema.buckets)
  .values({
    name: "Emergência",
    emoji: "🛟",
    kind: "goal",
    targetCents: dollarsToCents("3000"),
    ruleType: "percent",
    ruleValue: 2000, // 20% of allocatable
    priority: 10,
    sortIndex: 3,
  })
  .returning({ id: schema.buckets.id })
  .get();

const travel = db
  .insert(schema.buckets)
  .values({
    name: "Viagem",
    emoji: "✈️",
    kind: "goal",
    targetCents: dollarsToCents("2500"),
    targetDate: "2026-12-15",
    ruleType: "fill_paced",
    ruleValue: 0,
    priority: 20,
    sortIndex: 4,
  })
  .returning({ id: schema.buckets.id })
  .get();

const gear = db
  .insert(schema.buckets)
  .values({
    name: "Câmara nova",
    emoji: "📷",
    kind: "goal",
    targetCents: dollarsToCents("1200"),
    ruleType: "fixed",
    ruleValue: dollarsToCents("40"),
    priority: 30,
    sortIndex: 5,
  })
  .returning({ id: schema.buckets.id })
  .get();

const overflow = db
  .insert(schema.buckets)
  .values({
    name: "Livre",
    emoji: "💚",
    kind: "overflow",
    ruleType: "none",
    priority: 999,
    sortIndex: 6,
  })
  .returning({ id: schema.buckets.id })
  .get();

// -- fixed expenses now that we have bucket ids ---------------------------
db.insert(schema.fixedExpenses)
  .values([
    {
      name: "Aluguel",
      category: "Habitação",
      amountCents: dollarsToCents("1600"),
      cadence: "monthly",
      anchorDate: "2026-08-01",
      sinkingBucketId: rentBucket?.id ?? null,
    },
    {
      name: "Internet",
      category: "Contas",
      amountCents: dollarsToCents("79"),
      cadence: "monthly",
      anchorDate: "2026-08-05",
      sinkingBucketId: billsBucket?.id ?? null,
    },
    {
      name: "Eletricidade",
      category: "Contas",
      amountCents: dollarsToCents("240"),
      cadence: "quarterly",
      anchorDate: "2026-09-15",
      sinkingBucketId: billsBucket?.id ?? null,
    },
    {
      name: "Telemóvel",
      category: "Contas",
      amountCents: dollarsToCents("35"),
      cadence: "monthly",
      anchorDate: "2026-08-03",
      sinkingBucketId: billsBucket?.id ?? null,
    },
    {
      name: "Spotify",
      category: "Assinaturas",
      amountCents: dollarsToCents("14.99"),
      cadence: "monthly",
      anchorDate: "2026-08-12",
      sinkingBucketId: subsBucket?.id ?? null,
    },
    {
      name: "Ginásio",
      category: "Saúde",
      amountCents: dollarsToCents("22"),
      cadence: "weekly",
      anchorDate: "2026-07-28",
      sinkingBucketId: subsBucket?.id ?? null,
    },
  ])
  .run();

// -- pay history: 8 weeks of forecast + committed allocations -------------
// Realistic hour swings, mapped to net pay via a rough 15% WHM cut.
const hourHistory = [22, 18.5, 32.5, 24.5, 27.5, 26.5, 24.5, 33.5];
const ratePerHour = 30;
const taxRate = 0.15;

for (let i = 0; i < hourHistory.length; i++) {
  const start = weekStart(addLocalDays(THIS_WEEK, -7 * (hourHistory.length - 1 - i)));
  const end = addLocalDays(start, 6);
  const hours = hourHistory[i];
  const gross = Math.round(hours * ratePerHour * 100);
  const tax = Math.round(gross * taxRate);
  const net = gross - tax;
  const superAmt = Math.round(gross * 0.12);

  db.insert(schema.payPeriods)
    .values({
      employerId,
      weekStart: start,
      weekEnd: end,
      forecastGrossCents: gross,
      forecastTaxCents: tax,
      forecastNetCents: net,
      forecastSuperCents: superAmt,
      forecastMinutes: Math.round(hours * 60),
      actualGrossCents: i === hourHistory.length - 1 ? null : gross,
      actualTaxCents: i === hourHistory.length - 1 ? null : tax,
      actualNetCents: i === hourHistory.length - 1 ? null : net,
      actualSuperCents: i === hourHistory.length - 1 ? null : superAmt,
      status: i === hourHistory.length - 1 ? "forecast" : "reconciled",
    })
    .run();

  // Fake an allocation run for each closed week so bucket balances look real.
  if (i < hourHistory.length - 1) {
    const rentAccrual = Math.round(dollarsToCents("1600") * (12 / 52));
    const billsAccrual =
      Math.round(dollarsToCents("79") * (12 / 52)) +
      Math.round(dollarsToCents("240") * (4 / 52)) +
      Math.round(dollarsToCents("35") * (12 / 52));
    const subsAccrual =
      Math.round(dollarsToCents("14.99") * (12 / 52)) + dollarsToCents("22");
    const fixed = rentAccrual + billsAccrual + subsAccrual;
    const allocatable = Math.max(0, net - fixed);

    const [{ id: runId }] = db
      .insert(schema.allocationRuns)
      .values({
        weekStart: start,
        basis: "actual",
        incomeCents: net,
        fixedCostCents: fixed,
        allocatableCents: allocatable,
        status: "committed",
      })
      .returning({ id: schema.allocationRuns.id })
      .all();

    // Sinking accruals
    const accrualEntries = [
      { bucket: rentBucket?.id, amt: rentAccrual },
      { bucket: billsBucket?.id, amt: billsAccrual },
      { bucket: subsBucket?.id, amt: subsAccrual },
    ];
    for (const a of accrualEntries) {
      if (!a.bucket) continue;
      db.insert(schema.ledgerEntries)
        .values({
          bucketId: a.bucket,
          allocationRunId: runId,
          date: start,
          amountCents: a.amt,
          kind: "allocation",
          note: "Provisão semanal",
        })
        .run();
    }

    // Goal buckets — same waterfall the engine uses.
    let remaining = allocatable;
    const goalAmts: { id: number | undefined; amt: number }[] = [
      { id: gear?.id, amt: Math.min(dollarsToCents("40"), remaining) },
    ];
    remaining -= goalAmts[0].amt;
    const savingsAmt = Math.min(Math.floor((allocatable * 2000) / 10000), remaining);
    goalAmts.push({ id: savings?.id, amt: savingsAmt });
    remaining -= savingsAmt;
    const travelAmt = Math.min(Math.floor(remaining * 0.35), remaining);
    goalAmts.push({ id: travel?.id, amt: travelAmt });
    remaining -= travelAmt;
    goalAmts.push({ id: overflow?.id, amt: remaining });

    for (const g of goalAmts) {
      if (!g.id || g.amt <= 0) continue;
      db.insert(schema.ledgerEntries)
        .values({
          bucketId: g.id,
          allocationRunId: runId,
          date: start,
          amountCents: g.amt,
          kind: "allocation",
        })
        .run();
    }
  }
}

// -- one ad-hoc income entry so the section is not empty in the demo ------
db.insert(schema.adhocIncome)
  .values({
    date: addLocalDays(THIS_WEEK, -3),
    amountCents: dollarsToCents("180"),
    kind: "informal",
    source: "Turno coberto por colega",
    taxSetAsideCents: dollarsToCents("27"),
    weekStart: THIS_WEEK,
    notes: "Sáb à noite, dinheiro em mão",
  })
  .run();

// -- example debts --------------------------------------------------------
const cc = db
  .insert(schema.debts)
  .values({
    name: "Cartão ANZ",
    emoji: "💳",
    kind: "credit_card",
    principalCents: dollarsToCents("2400"),
    dailyTargetCents: dollarsToCents("12"),
    targetDate: "2027-01-31",
    priority: 10,
    sortIndex: 0,
  })
  .returning({ id: schema.debts.id })
  .get();

const loan = db
  .insert(schema.debts)
  .values({
    name: "Empréstimo família",
    emoji: "🏦",
    kind: "personal",
    principalCents: dollarsToCents("1500"),
    dailyTargetCents: dollarsToCents("5"),
    priority: 20,
    sortIndex: 1,
  })
  .returning({ id: schema.debts.id })
  .get();

// Some past payments so the progress bars have movement.
if (cc?.id) {
  const payments = [
    { date: addLocalDays(TODAY, -25), amount: 12 },
    { date: addLocalDays(TODAY, -20), amount: 12 },
    { date: addLocalDays(TODAY, -15), amount: 60 },
    { date: addLocalDays(TODAY, -10), amount: 12 },
    { date: addLocalDays(TODAY, -5), amount: 12 },
    { date: addLocalDays(TODAY, -1), amount: 12 },
  ];
  for (const p of payments) {
    db.insert(schema.debtPayments)
      .values({
        debtId: cc.id,
        date: p.date,
        amountCents: dollarsToCents(String(p.amount)),
      })
      .run();
  }
}

if (loan?.id) {
  db.insert(schema.debtPayments)
    .values({
      debtId: loan.id,
      date: addLocalDays(TODAY, -14),
      amountCents: dollarsToCents("100"),
      note: "Fim de semana bom",
    })
    .run();
}

console.log("Seed concluído.");
sqlite.close();
