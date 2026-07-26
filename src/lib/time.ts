/**
 * Everything is anchored to Brisbane local time.
 *
 * Queensland does not observe daylight saving, so the offset is a constant
 * UTC+10 all year. That is a genuine simplification — but we still go through
 * the timezone layer rather than hardcoding +10, so nothing silently breaks if
 * Joshua moves to a state that does observe DST.
 */

import { TZDate } from "@date-fns/tz";
import { addDays, differenceInCalendarDays, format, parse } from "date-fns";

export const TZ = "Australia/Brisbane";

/** A calendar date with no time component, as `YYYY-MM-DD`. */
export type LocalDate = string;

/** Current instant, as a Brisbane-local date object. */
export function nowLocal(): TZDate {
  return TZDate.tz(TZ);
}

/** Convert any instant to its Brisbane-local wall-clock representation. */
export function toLocal(instant: Date): TZDate {
  return new TZDate(instant, TZ);
}

/** Render an instant as the Brisbane-local `YYYY-MM-DD` it falls on. */
export function toLocalDate(instant: Date): LocalDate {
  return format(toLocal(instant), "yyyy-MM-dd");
}

/** Parse a `YYYY-MM-DD` as midnight Brisbane-local. */
export function fromLocalDate(date: LocalDate): TZDate {
  const parsed = parse(date, "yyyy-MM-dd", new Date());
  return new TZDate(
    parsed.getFullYear(),
    parsed.getMonth(),
    parsed.getDate(),
    TZ,
  );
}

/**
 * The Monday that starts the week containing `date`.
 *
 * Tanda rosters run Monday–Sunday ("Shifts between Mon 20 Jul - Sun 26 Jul"),
 * so Monday is the week key throughout the app.
 */
export function weekStart(date: LocalDate | Date): LocalDate {
  const local = typeof date === "string" ? fromLocalDate(date) : toLocal(date);
  const dow = local.getDay(); // 0 = Sunday
  const backToMonday = dow === 0 ? 6 : dow - 1;
  return format(addDays(local, -backToMonday), "yyyy-MM-dd");
}

/** The Sunday that ends the week containing `date`. */
export function weekEnd(date: LocalDate | Date): LocalDate {
  return format(addDays(fromLocalDate(weekStart(date)), 6), "yyyy-MM-dd");
}

/** Shift a local date by a whole number of days. */
export function addLocalDays(date: LocalDate, days: number): LocalDate {
  return format(addDays(fromLocalDate(date), days), "yyyy-MM-dd");
}

/** Whole days from `from` to `to`, positive when `to` is later. */
export function daysBetween(from: LocalDate, to: LocalDate): number {
  return differenceInCalendarDays(fromLocalDate(to), fromLocalDate(from));
}

/** Whole weeks from `from` to `to`, rounded up, never below zero. */
export function weeksBetween(from: LocalDate, to: LocalDate): number {
  return Math.max(0, Math.ceil(daysBetween(from, to) / 7));
}

/**
 * The Australian financial year containing `date`, as `2026-27`.
 * The FY runs 1 July – 30 June.
 */
export function fyOf(date: LocalDate | Date): string {
  const local = typeof date === "string" ? fromLocalDate(date) : toLocal(date);
  const year = local.getFullYear();
  const month = local.getMonth(); // 0 = January
  const startYear = month >= 6 ? year : year - 1;
  return `${startYear}-${String((startYear + 1) % 100).padStart(2, "0")}`;
}

/** First day of a financial year labelled `2026-27`. */
export function fyStart(fy: string): LocalDate {
  const startYear = Number(fy.split("-")[0]);
  return `${startYear}-07-01`;
}

/** Last day of a financial year labelled `2026-27`. */
export function fyEnd(fy: string): LocalDate {
  const startYear = Number(fy.split("-")[0]);
  return `${startYear + 1}-06-30`;
}

const DOW_SHORT = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const MONTH_SHORT = [
  "jan", "fev", "mar", "abr", "mai", "jun",
  "jul", "ago", "set", "out", "nov", "dez",
];

/** Human-readable local date, e.g. "Sáb, 25 jul". */
export function fmtDate(date: LocalDate): string {
  const d = fromLocalDate(date);
  return `${DOW_SHORT[d.getDay()]}, ${d.getDate()} ${MONTH_SHORT[d.getMonth()]}`;
}

/** Human-readable week range, e.g. "20 – 26 jul". */
export function fmtWeekRange(start: LocalDate): string {
  const a = fromLocalDate(start);
  const b = fromLocalDate(addLocalDays(start, 6));
  const sameMonth = a.getMonth() === b.getMonth();
  return sameMonth
    ? `${a.getDate()} – ${b.getDate()} ${MONTH_SHORT[b.getMonth()]}`
    : `${a.getDate()} ${MONTH_SHORT[a.getMonth()]} – ${b.getDate()} ${MONTH_SHORT[b.getMonth()]}`;
}

/** Minutes since local midnight, used by the penalty-rate rule matcher. */
export function minuteOfDay(instant: Date): number {
  const local = toLocal(instant);
  return local.getHours() * 60 + local.getMinutes();
}
