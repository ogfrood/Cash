/**
 * Debt payoff projection.
 *
 * Given a current balance and a chosen daily contribution, work out the
 * straight-line payoff date, the ETA in days, and whether the user is on
 * track to meet an optional `targetDate`.
 *
 * Deliberately interest-free for now — see the note on `debts.balanceOverrideCents`.
 * When interest is added it becomes a second function that consumes an APR
 * and evolves the balance day by day.
 */

import type { LocalDate } from "@/lib/time";
import { addLocalDays, daysBetween } from "@/lib/time";

export type DebtProgress = {
  paidCents: number;
  balanceCents: number;
  /** 0..1, the fraction of the principal that has been paid off. */
  progress: number;
  /** Days until the balance hits zero at the current daily target. */
  daysToZero: number | null;
  projectedZeroDate: LocalDate | null;
  /** True when the projected date lands on or before `targetDate`. */
  onTrack: boolean | null;
  /** How much per day would be needed to hit `targetDate` on time. */
  requiredDailyCents: number | null;
};

export function debtProgress(args: {
  principalCents: number;
  balanceOverrideCents: number | null;
  totalPaidCents: number;
  dailyTargetCents: number;
  targetDate: LocalDate | null;
  today: LocalDate;
}): DebtProgress {
  const {
    principalCents,
    balanceOverrideCents,
    totalPaidCents,
    dailyTargetCents,
    targetDate,
    today,
  } = args;

  const balanceCents =
    balanceOverrideCents != null
      ? balanceOverrideCents
      : Math.max(0, principalCents - totalPaidCents);
  const paidCents = principalCents - balanceCents;

  const progress =
    principalCents > 0
      ? Math.min(1, Math.max(0, paidCents / principalCents))
      : 0;

  const daysToZero =
    balanceCents <= 0
      ? 0
      : dailyTargetCents > 0
        ? Math.ceil(balanceCents / dailyTargetCents)
        : null;

  const projectedZeroDate =
    daysToZero == null ? null : addLocalDays(today, daysToZero);

  const onTrack =
    targetDate == null || projectedZeroDate == null
      ? null
      : projectedZeroDate <= targetDate;

  const requiredDailyCents =
    targetDate == null || balanceCents <= 0
      ? null
      : (() => {
          const days = Math.max(1, daysBetween(today, targetDate));
          return Math.ceil(balanceCents / days);
        })();

  return {
    paidCents,
    balanceCents,
    progress,
    daysToZero,
    projectedZeroDate,
    onTrack,
    requiredDailyCents,
  };
}
