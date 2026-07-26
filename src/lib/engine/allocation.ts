/**
 * The allocation engine: turn one week's net income into money in buckets.
 *
 * Why a priority waterfall rather than plain percentages: Joshua's hours swing
 * hard (21.5h one week, 33.5h the next). A percentage-only split silently
 * underfunds rent in a lean week — the percentages still "work", they just
 * work on a smaller number, and the essentials quietly come up short. A
 * waterfall guarantees the must-fund buckets fill first and the discretionary
 * ones absorb the variance. Percentages still exist, but inside the waterfall.
 *
 * Pure module: no database, no I/O. Every number is integer cents.
 *
 * Invariant, asserted below and property-tested:
 *     sum(plan.lines[].amountCents) === plan.distributableCents
 * Money is never created and never silently lost.
 */

import { BP_SCALE } from "@/lib/money";
import type { LocalDate } from "@/lib/time";
import { weeksBetween } from "@/lib/time";
import type { Accrual } from "./sinking";

export type BucketRuleType =
  | "percent"
  | "fixed"
  | "fill_to_target"
  | "fill_paced"
  | "none";

export type BucketKind = "goal" | "sinking" | "spending" | "overflow";

export type BucketRule = {
  id: number;
  name: string;
  emoji?: string | null;
  kind: BucketKind;
  ruleType: BucketRuleType;
  /** Basis points for `percent`, cents for `fixed`. */
  ruleValue: number;
  targetCents: number | null;
  targetDate: LocalDate | null;
  weeklyCapCents: number | null;
  priority: number;
};

export type AllocationInput = {
  weekStart: LocalDate;
  incomeCents: number;
  /** Weekly sinking-fund accruals for fixed costs; taken off the top. */
  accruals: Accrual[];
  buckets: BucketRule[];
  /** Current balance per bucket id. Missing means zero. */
  balances: Record<number, number>;
};

export type AllocationLine = {
  bucketId: number | null;
  name: string;
  amountCents: number;
  reason: "accrual" | "rule" | "overflow" | "unallocated";
  ruleType?: BucketRuleType;
  /** True when the weekly cap, not the rule, decided the amount. */
  cappedByWeeklyCap?: boolean;
  /** True when there was not enough left to satisfy the rule in full. */
  short?: boolean;
};

export type AllocationPlan = {
  weekStart: LocalDate;
  incomeCents: number;
  fixedCostCents: number;
  /** income − fixedCost. Can be negative. */
  allocatableCents: number;
  /** max(allocatable, 0). This is what the lines sum to. */
  distributableCents: number;
  /** Accrual lines. Sum equals `fixedCostCents`. */
  accrualLines: AllocationLine[];
  /** Bucket allocation lines. Sum equals `distributableCents`, exactly. */
  lines: AllocationLine[];
  /** True when fixed costs exceed income for the week. */
  isDeficit: boolean;
  /** How far short the week is, in cents. Zero unless `isDeficit`. */
  deficitCents: number;
};

/**
 * Build the allocation plan for one week.
 *
 * Deliberately pure and cheap so the dashboard can re-render it live as the
 * roster or the rules change, long before anything is committed.
 */
export function allocate(input: AllocationInput): AllocationPlan {
  const { weekStart, incomeCents, accruals, buckets, balances } = input;

  const accrualLines: AllocationLine[] = accruals.map((a) => ({
    bucketId: a.bucketId,
    name: a.label,
    amountCents: a.amountCents,
    reason: "accrual" as const,
  }));

  const fixedCostCents = accrualLines.reduce((s, l) => s + l.amountCents, 0);
  const allocatableCents = incomeCents - fixedCostCents;
  const distributableCents = Math.max(allocatableCents, 0);

  const active = buckets.filter((b) => b.kind !== "overflow");
  const overflow = buckets.find((b) => b.kind === "overflow") ?? null;

  // Lower priority number runs first; ties break on id for determinism.
  const ordered = [...active].sort(
    (a, b) => a.priority - b.priority || a.id - b.id,
  );

  const lines: AllocationLine[] = [];
  let remaining = distributableCents;

  for (const bucket of ordered) {
    if (remaining <= 0) break;

    const balance = balances[bucket.id] ?? 0;
    const wanted = wantedFor(bucket, {
      distributableCents,
      balance,
      weekStart,
    });
    if (wanted <= 0) continue;

    const capped =
      bucket.weeklyCapCents != null
        ? Math.min(wanted, bucket.weeklyCapCents)
        : wanted;
    const take = Math.min(capped, remaining);
    if (take <= 0) continue;

    lines.push({
      bucketId: bucket.id,
      name: bucket.name,
      amountCents: take,
      reason: "rule",
      ruleType: bucket.ruleType,
      cappedByWeeklyCap: capped < wanted,
      short: take < capped,
    });
    remaining -= take;
  }

  // Whatever is left — including every cent of rounding dust — lands in the
  // overflow bucket. If there is no overflow bucket it is reported as an
  // explicit "unallocated" line. It is never dropped.
  if (remaining > 0) {
    lines.push(
      overflow
        ? {
            bucketId: overflow.id,
            name: overflow.name,
            amountCents: remaining,
            reason: "overflow",
          }
        : {
            bucketId: null,
            name: "Não alocado",
            amountCents: remaining,
            reason: "unallocated",
          },
    );
    remaining = 0;
  }

  const plan: AllocationPlan = {
    weekStart,
    incomeCents,
    fixedCostCents,
    allocatableCents,
    distributableCents,
    accrualLines,
    lines,
    isDeficit: allocatableCents < 0,
    deficitCents: allocatableCents < 0 ? -allocatableCents : 0,
  };

  assertBalanced(plan);
  return plan;
}

function wantedFor(
  bucket: BucketRule,
  ctx: { distributableCents: number; balance: number; weekStart: LocalDate },
): number {
  const { distributableCents, balance, weekStart } = ctx;

  switch (bucket.ruleType) {
    case "none":
      return 0;

    case "fixed":
      return Math.max(0, bucket.ruleValue);

    case "percent":
      // Deliberately a percentage of the *fixed base*, not of what happens to
      // be left. That makes the result independent of the order buckets are
      // processed in — reordering the list can never change anyone's share.
      return Math.max(
        0,
        Math.floor((distributableCents * bucket.ruleValue) / BP_SCALE),
      );

    case "fill_to_target": {
      if (bucket.targetCents == null) return 0;
      return Math.max(0, bucket.targetCents - balance);
    }

    case "fill_paced": {
      if (bucket.targetCents == null) return 0;
      const gap = Math.max(0, bucket.targetCents - balance);
      if (gap === 0) return 0;
      if (!bucket.targetDate) return gap;
      // Spread the remaining gap evenly over the weeks left until the target
      // date. With no weeks left, take the whole gap now.
      const weeks = weeksBetween(weekStart, bucket.targetDate);
      return weeks <= 0 ? gap : Math.min(gap, Math.ceil(gap / weeks));
    }
  }
}

/**
 * The engine's safety net. If this ever throws, the bug is here — better a
 * loud failure in a preview than a budget that quietly stops adding up.
 */
function assertBalanced(plan: AllocationPlan): void {
  const total = plan.lines.reduce((s, l) => s + l.amountCents, 0);
  if (total !== plan.distributableCents) {
    throw new Error(
      `Alocação desequilibrada: linhas somam ${total}, esperado ${plan.distributableCents}`,
    );
  }
  const accrued = plan.accrualLines.reduce((s, l) => s + l.amountCents, 0);
  if (accrued !== plan.fixedCostCents) {
    throw new Error(
      `Provisões desequilibradas: somam ${accrued}, esperado ${plan.fixedCostCents}`,
    );
  }
}

/* ------------------------------------------------------------------ *
 * Bucket progress metrics
 * ------------------------------------------------------------------ */

export type BucketProgress = {
  bucketId: number;
  balanceCents: number;
  targetCents: number | null;
  /** 0..1, clamped. Null when the bucket has no target. */
  progress: number | null;
  /** Average contribution per week over the observed weeks. */
  avgWeeklyCents: number;
  /** Weeks to reach target at the current pace. Null if unreachable. */
  weeksToGoal: number | null;
  /** Projected completion date at the current pace. */
  projectedDate: LocalDate | null;
  /** Weekly amount needed to hit `targetDate`. Null without a target date. */
  requiredWeeklyCents: number | null;
  /** False when the projected date lands after the target date. */
  onTrack: boolean | null;
};

/**
 * Derive progress metrics for one bucket.
 *
 * `weeklyContributions` should be the per-week totals over the recent past
 * (most recent first or last, order does not matter).
 */
export function bucketProgress(args: {
  bucketId: number;
  balanceCents: number;
  targetCents: number | null;
  targetDate: LocalDate | null;
  weeklyContributions: number[];
  today: LocalDate;
}): BucketProgress {
  const {
    bucketId,
    balanceCents,
    targetCents,
    targetDate,
    weeklyContributions,
    today,
  } = args;

  const weeks = weeklyContributions.length;
  const avgWeeklyCents =
    weeks === 0
      ? 0
      : Math.round(weeklyContributions.reduce((a, b) => a + b, 0) / weeks);

  const gap =
    targetCents == null ? null : Math.max(0, targetCents - balanceCents);

  const weeksToGoal =
    gap == null || avgWeeklyCents <= 0
      ? gap === 0
        ? 0
        : null
      : Math.ceil(gap / avgWeeklyCents);

  const projectedDate =
    weeksToGoal == null ? null : addWeeks(today, weeksToGoal);

  const requiredWeeklyCents =
    gap == null || targetDate == null
      ? null
      : (() => {
          const w = weeksBetween(today, targetDate);
          return w <= 0 ? gap : Math.ceil(gap / w);
        })();

  const onTrack =
    targetDate == null || projectedDate == null
      ? null
      : projectedDate <= targetDate;

  return {
    bucketId,
    balanceCents,
    targetCents,
    progress:
      targetCents == null || targetCents <= 0
        ? null
        : Math.min(1, Math.max(0, balanceCents / targetCents)),
    avgWeeklyCents,
    weeksToGoal,
    projectedDate,
    requiredWeeklyCents,
    onTrack,
  };
}

function addWeeks(date: LocalDate, weeks: number): LocalDate {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + weeks * 7);
  return d.toISOString().slice(0, 10);
}
