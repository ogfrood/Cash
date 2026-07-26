/**
 * Fixed costs -> weekly accrual (the sinking-fund approach).
 *
 * Joshua is paid weekly but rent is monthly. The naive approach — charging the
 * whole bill in the week it happens to fall due — produces one starvation week
 * a month, which is exactly the pattern a budget is supposed to remove.
 *
 * Instead every non-weekly expense is converted to a weekly accrual that is
 * set aside into a sinking-fund bucket. When the bill actually lands, it is
 * paid out of that bucket. Money available per week stays flat.
 *
 * Pure module: no database, no I/O.
 */

import { roundHalfAwayFromZero } from "@/lib/money";
import type { LocalDate } from "@/lib/time";
import { addLocalDays, daysBetween, fromLocalDate } from "@/lib/time";

export type Cadence =
  | "weekly"
  | "fortnightly"
  | "monthly"
  | "quarterly"
  | "yearly";

/**
 * Occurrences per 52-week year, divided by 52.
 *
 * Using a flat 52 rather than 52.18 means a year of accruals sums to exactly
 * the year's bills over 52 weeks. The extra ~1.25 days per calendar year
 * accrues very slightly in Joshua's favour, which is the safe direction.
 */
const WEEKLY_FACTOR: Record<Cadence, number> = {
  weekly: 1,
  fortnightly: 1 / 2,
  monthly: 12 / 52,
  quarterly: 4 / 52,
  yearly: 1 / 52,
};

/** Days between occurrences, used to project the due-date schedule. */
const CADENCE_DAYS: Record<Cadence, number> = {
  weekly: 7,
  fortnightly: 14,
  monthly: 0, // handled by calendar-month arithmetic
  quarterly: 0,
  yearly: 0,
};

const CADENCE_MONTHS: Record<Cadence, number> = {
  weekly: 0,
  fortnightly: 0,
  monthly: 1,
  quarterly: 3,
  yearly: 12,
};

export type ExpenseForAccrual = {
  id: number;
  name: string;
  amountCents: number;
  cadence: Cadence;
  sinkingBucketId: number | null;
};

export type Accrual = {
  expenseId: number;
  bucketId: number | null;
  label: string;
  amountCents: number;
};

/** The weekly amount to set aside for a single expense. */
export function weeklyAccrualCents(
  amountCents: number,
  cadence: Cadence,
): number {
  return roundHalfAwayFromZero(amountCents * WEEKLY_FACTOR[cadence]);
}

/** Weekly accruals for a set of expenses. */
export function accrualsFor(expenses: ExpenseForAccrual[]): Accrual[] {
  return expenses.map((e) => ({
    expenseId: e.id,
    bucketId: e.sinkingBucketId,
    label: e.name,
    amountCents: weeklyAccrualCents(e.amountCents, e.cadence),
  }));
}

/** Total weekly cost of all fixed expenses. */
export function totalWeeklyFixedCents(expenses: ExpenseForAccrual[]): number {
  return accrualsFor(expenses).reduce((sum, a) => sum + a.amountCents, 0);
}

/**
 * Project the next `count` due dates for an expense, starting at or after
 * `from`. Monthly and longer cadences step by calendar months so the 1st of
 * the month stays the 1st, rather than drifting by a day each period.
 */
export function projectDueDates(
  anchorDate: LocalDate,
  cadence: Cadence,
  from: LocalDate,
  count: number,
): LocalDate[] {
  const out: LocalDate[] = [];
  let cursor = anchorDate;

  // Fast-forward to the first occurrence at or after `from`.
  let guard = 0;
  while (daysBetween(cursor, from) > 0 && guard++ < 1000) {
    cursor = nextOccurrence(cursor, anchorDate, cadence, guard);
  }

  for (let i = 0; i < count; i++) {
    out.push(cursor);
    cursor = nextOccurrence(cursor, anchorDate, cadence, guard + i + 1);
  }
  return out;
}

function nextOccurrence(
  current: LocalDate,
  anchor: LocalDate,
  cadence: Cadence,
  step: number,
): LocalDate {
  const months = CADENCE_MONTHS[cadence];
  if (months > 0) {
    // Step from the anchor rather than from `current`, so a month that is
    // short (February) does not permanently pull the day-of-month backwards.
    const a = fromLocalDate(anchor);
    const targetDay = a.getDate();
    const d = new Date(a.getFullYear(), a.getMonth() + months * step, 1);
    const daysInMonth = new Date(
      d.getFullYear(),
      d.getMonth() + 1,
      0,
    ).getDate();
    d.setDate(Math.min(targetDay, daysInMonth));
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
      d.getDate(),
    ).padStart(2, "0")}`;
  }
  return addLocalDays(current, CADENCE_DAYS[cadence]);
}
