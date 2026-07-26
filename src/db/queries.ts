import "server-only";

import { and, desc, eq, gte, lte, sql } from "drizzle-orm";

import { db, schema } from "./index";
import type { LocalDate } from "@/lib/time";
import { fyEnd, fyStart, weekStart } from "@/lib/time";

/** Current balance of every bucket. Computed, never stored. */
export function bucketBalances(): Record<number, number> {
  const rows = db
    .select({
      bucketId: schema.ledgerEntries.bucketId,
      balance: sql<number>`sum(${schema.ledgerEntries.amountCents})`,
    })
    .from(schema.ledgerEntries)
    .groupBy(schema.ledgerEntries.bucketId)
    .all();
  const out: Record<number, number> = {};
  for (const r of rows) out[r.bucketId] = Number(r.balance ?? 0);
  return out;
}

/** Weekly contributions to a bucket, oldest first, capped at N weeks. */
export function weeklyContributions(bucketId: number, weeks = 8): number[] {
  const rows = db
    .select({
      w: schema.ledgerEntries.date,
      amount: sql<number>`sum(${schema.ledgerEntries.amountCents})`,
    })
    .from(schema.ledgerEntries)
    .where(
      and(
        eq(schema.ledgerEntries.bucketId, bucketId),
        eq(schema.ledgerEntries.kind, "allocation"),
      ),
    )
    .groupBy(schema.ledgerEntries.date)
    .orderBy(desc(schema.ledgerEntries.date))
    .limit(weeks)
    .all();
  return rows.map((r) => Number(r.amount)).reverse();
}

/** All active buckets in display order. */
export function activeBuckets() {
  return db
    .select()
    .from(schema.buckets)
    .where(eq(schema.buckets.isArchived, false))
    .orderBy(schema.buckets.sortIndex, schema.buckets.id)
    .all();
}

/** All active fixed expenses. */
export function activeFixedExpenses() {
  return db
    .select()
    .from(schema.fixedExpenses)
    .where(eq(schema.fixedExpenses.isActive, true))
    .all();
}

/** The last N committed pay periods, oldest first (for a chart). */
export function recentPayPeriods(n = 8) {
  return db
    .select()
    .from(schema.payPeriods)
    .orderBy(desc(schema.payPeriods.weekEnd))
    .limit(n)
    .all()
    .reverse();
}

/** Ad-hoc income for a given week (Monday-anchored). */
export function adhocForWeek(week: LocalDate) {
  return db
    .select()
    .from(schema.adhocIncome)
    .where(eq(schema.adhocIncome.weekStart, week))
    .orderBy(desc(schema.adhocIncome.date))
    .all();
}

/** All ad-hoc income entries, most recent first. */
export function allAdhocIncome() {
  return db
    .select()
    .from(schema.adhocIncome)
    .orderBy(desc(schema.adhocIncome.date))
    .all();
}

/** YTD totals for the financial year containing `date`. */
export function ytdTotals(date: LocalDate) {
  const fy = ytdFyLabel(date);
  const start = fyStart(fy);
  const end = fyEnd(fy);

  const [pp] = db
    .select({
      gross: sql<number>`coalesce(sum(coalesce(${schema.payPeriods.actualGrossCents}, ${schema.payPeriods.forecastGrossCents}, ${schema.payPeriods.manualNetCents}, 0)), 0)`,
      tax: sql<number>`coalesce(sum(coalesce(${schema.payPeriods.actualTaxCents}, ${schema.payPeriods.forecastTaxCents}, 0)), 0)`,
      superAmt: sql<number>`coalesce(sum(coalesce(${schema.payPeriods.actualSuperCents}, ${schema.payPeriods.forecastSuperCents}, 0)), 0)`,
    })
    .from(schema.payPeriods)
    .where(
      and(
        gte(schema.payPeriods.weekEnd, start),
        lte(schema.payPeriods.weekEnd, end),
      ),
    )
    .all();

  const [adhoc] = db
    .select({
      total: sql<number>`coalesce(sum(${schema.adhocIncome.amountCents}), 0)`,
    })
    .from(schema.adhocIncome)
    .where(
      and(
        gte(schema.adhocIncome.date, start),
        lte(schema.adhocIncome.date, end),
      ),
    )
    .all();

  return {
    fy,
    grossCents: Number(pp?.gross ?? 0) + Number(adhoc?.total ?? 0),
    taxCents: Number(pp?.tax ?? 0),
    superCents: Number(pp?.superAmt ?? 0),
  };
}

function ytdFyLabel(date: LocalDate): string {
  const [y, m] = date.split("-").map(Number);
  const startYear = m >= 7 ? y : y - 1;
  return `${startYear}-${String((startYear + 1) % 100).padStart(2, "0")}`;
}

/** Convenience — the week the given date belongs to. */
export function currentWeekStart(today: LocalDate): LocalDate {
  return weekStart(today);
}

/** All active debts, in display order. */
export function activeDebts() {
  return db
    .select()
    .from(schema.debts)
    .where(eq(schema.debts.isActive, true))
    .orderBy(schema.debts.sortIndex, schema.debts.id)
    .all();
}

/** Total paid per debt id. */
export function debtPaidTotals(): Record<number, number> {
  const rows = db
    .select({
      debtId: schema.debtPayments.debtId,
      paid: sql<number>`sum(${schema.debtPayments.amountCents})`,
    })
    .from(schema.debtPayments)
    .groupBy(schema.debtPayments.debtId)
    .all();
  const out: Record<number, number> = {};
  for (const r of rows) out[r.debtId] = Number(r.paid ?? 0);
  return out;
}

/** All payments for one debt, most recent first. */
export function debtPayments(debtId: number) {
  return db
    .select()
    .from(schema.debtPayments)
    .where(eq(schema.debtPayments.debtId, debtId))
    .orderBy(desc(schema.debtPayments.date))
    .all();
}
