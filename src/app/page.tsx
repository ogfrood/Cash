import Link from "next/link";

import { ProgressRing } from "@/components/ProgressRing";
import { Sparkline } from "@/components/Sparkline";
import { IconArrowRight, IconBriefcase, IconPlus } from "@/components/Icons";
import {
  activeBuckets,
  activeFixedExpenses,
  adhocForWeek,
  bucketBalances,
  recentPayPeriods,
  ytdTotals,
} from "@/db/queries";
import { pt } from "@/i18n/pt";
import { allocate, bucketProgress } from "@/lib/engine/allocation";
import { accrualsFor, totalWeeklyFixedCents } from "@/lib/engine/sinking";
import { dollarsToCents, fmtAUD } from "@/lib/money";
import { fmtWeekRange, weekStart } from "@/lib/time";

// Demo "today" — matches the seed so screenshots are stable.
const TODAY = "2026-07-26";

export default async function PainelPage() {
  const week = weekStart(TODAY);
  const buckets = activeBuckets();
  const balances = bucketBalances();
  const expenses = activeFixedExpenses();
  const periods = recentPayPeriods(8);
  const adhoc = adhocForWeek(week);
  const ytd = ytdTotals(TODAY);

  const thisWeek = periods.at(-1);
  const forecastNet =
    thisWeek?.forecastNetCents ?? thisWeek?.manualNetCents ?? 0;
  const adhocTotal = adhoc.reduce((s, a) => s + a.amountCents, 0);
  const income = forecastNet + adhocTotal;

  const expenseInputs = expenses.map((e) => ({
    id: e.id,
    name: e.name,
    amountCents: e.amountCents,
    cadence: e.cadence,
    sinkingBucketId: e.sinkingBucketId,
  }));
  const fixedTotal = totalWeeklyFixedCents(expenseInputs);

  const plan = allocate({
    weekStart: week,
    incomeCents: income,
    accruals: accrualsFor(expenseInputs),
    buckets: buckets.map((b) => ({
      id: b.id,
      name: b.name,
      emoji: b.emoji,
      kind: b.kind,
      ruleType: b.ruleType,
      ruleValue: b.ruleValue,
      targetCents: b.targetCents,
      targetDate: b.targetDate,
      weeklyCapCents: b.weeklyCapCents,
      priority: b.priority,
    })),
    balances,
  });

  const outTotal = fixedTotal;
  const barMax = Math.max(income, outTotal, 1);

  const netHistory = periods.map(
    (p) => p.actualNetCents ?? p.forecastNetCents ?? p.manualNetCents ?? 0,
  );

  const capCents = dollarsToCents("45000");
  const capProgress = Math.min(1, ytd.grossCents / capCents);

  const goalBuckets = buckets.filter((b) => b.kind === "goal");
  const topGoal = goalBuckets.find((b) => b.targetCents) ?? goalBuckets[0];
  const topGoalBalance = topGoal ? (balances[topGoal.id] ?? 0) : 0;
  const topGoalProgress = topGoal
    ? bucketProgress({
        bucketId: topGoal.id,
        balanceCents: topGoalBalance,
        targetCents: topGoal.targetCents,
        targetDate: topGoal.targetDate,
        weeklyContributions: [],
        today: TODAY,
      })
    : null;

  return (
    <div className="flex flex-col gap-5">
      <header className="flex items-center justify-between pt-2">
        <div>
          <p className="text-[color:var(--text-muted)] text-sm">
            {pt.app.greetingMorning}, Joshua
          </p>
          <h1 className="text-2xl font-extrabold tracking-tight">
            {fmtWeekRange(week)}
          </h1>
        </div>
        <Link
          href="/avulso/novo"
          className="pill pill-accent"
          aria-label={pt.adhoc.add}
        >
          <IconPlus size={16} />
          Avulso
        </Link>
      </header>

      {/* Cash flow */}
      <section className="card flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <p className="eyebrow">{pt.cashflow.subtitle}</p>
          <span className="pill">{fmtWeekRange(week)}</span>
        </div>
        <div className="flex flex-col gap-4">
          <CashRow
            label={pt.cashflow.in}
            amount={income}
            sign="+"
            widthPct={(income / barMax) * 100}
            tone="in"
          />
          <CashRow
            label={pt.cashflow.out}
            amount={outTotal}
            sign="−"
            widthPct={(outTotal / barMax) * 100}
            tone="out"
          />
        </div>
        <div className="flex flex-col gap-1 pt-2 border-t border-[color:var(--border)]">
          <p className="eyebrow">{pt.cashflow.left}</p>
          <p className="num-hero" style={{ color: "var(--accent)" }}>
            {fmtAUD(plan.distributableCents)}
          </p>
        </div>
      </section>

      {/* Salary progression */}
      <section className="card card-tight overflow-hidden">
        <div className="px-2 pt-2 flex flex-col gap-0.5">
          <p className="eyebrow">{pt.progression.title}</p>
          <p className="text-[color:var(--text-muted)] text-xs">
            {pt.progression.subtitle} · último líquido{" "}
            <span className="text-[color:var(--text)] font-semibold">
              {fmtAUD(netHistory.at(-1) ?? 0)}
            </span>
          </p>
        </div>
        <div className="mt-2 -mx-1">
          <Sparkline values={netHistory} width={440} height={110} />
        </div>
        <div className="grid grid-cols-3 gap-2 px-2 pb-2">
          <YtdTile label={pt.progression.ytdGross} amount={ytd.grossCents} />
          <YtdTile label={pt.progression.ytdTax} amount={ytd.taxCents} danger />
          <YtdTile label={pt.progression.ytdSuper} amount={ytd.superCents} />
        </div>
      </section>

      {/* WHM cap progress */}
      <section className="card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="eyebrow">Imposto WHM</p>
            <p className="text-xs text-[color:var(--text-muted)] mt-1">
              Working Holiday · FY {ytd.fy}
            </p>
          </div>
          <span className="pill" style={{ color: "var(--accent)" }}>
            15%
          </span>
        </div>
        <div className="flex items-center gap-5">
          <div className="flex-shrink-0">
            <ProgressRing value={capProgress} size={96} stroke={10}>
              <span className="text-xl font-extrabold">
                {Math.round(capProgress * 100)}%
              </span>
            </ProgressRing>
          </div>
          <div className="flex-1 min-w-0">
            <p className="num-lg leading-tight">
              {fmtAUD(ytd.grossCents)}
            </p>
            <p className="text-xs text-[color:var(--text-muted)] mt-1">
              de {fmtAUD(capCents)} até subir de escalão
            </p>
            <p className="text-xs mt-3" style={{ color: "var(--accent)" }}>
              Faltam {fmtAUD(capCents - ytd.grossCents)}
            </p>
          </div>
        </div>
      </section>

      {topGoal && topGoalProgress && (
        <section className="card">
          <div className="flex items-center justify-between mb-3">
            <p className="eyebrow">Meta principal</p>
            <Link
              href="/caixinhas"
              className="text-[color:var(--accent)] text-sm font-medium flex items-center gap-1"
            >
              Todas <IconArrowRight size={14} />
            </Link>
          </div>
          <div className="flex items-center gap-4">
            <ProgressRing value={topGoalProgress.progress ?? 0} size={120}>
              <span className="text-2xl">{topGoal.emoji}</span>
            </ProgressRing>
            <div className="flex-1">
              <p className="text-lg font-bold">{topGoal.name}</p>
              <p className="num-lg mt-1">
                {fmtAUD(topGoalBalance)}
                {topGoal.targetCents && (
                  <span className="text-sm font-normal text-[color:var(--text-muted)]">
                    {" "}
                    / {fmtAUD(topGoal.targetCents)}
                  </span>
                )}
              </p>
              {topGoalProgress.onTrack !== null && (
                <p
                  className="text-xs mt-2"
                  style={{
                    color: topGoalProgress.onTrack
                      ? "var(--accent)"
                      : "var(--warn)",
                  }}
                >
                  {topGoalProgress.onTrack ? "No ritmo" : "Preciso apertar"}
                  {topGoal.targetDate && ` · meta ${topGoal.targetDate}`}
                </p>
              )}
            </div>
          </div>
        </section>
      )}

      <section className="card">
        <div className="flex items-center justify-between mb-3">
          <div>
            <p className="eyebrow">Alocação prevista</p>
            <p className="text-[color:var(--text-muted)] text-xs mt-0.5">
              Como o salário desta semana se divide
            </p>
          </div>
        </div>
        <ul className="flex flex-col gap-2.5">
          {plan.fixedCostCents > 0 && (
            <li className="rounded-2xl bg-[color:var(--surface-2)] px-4 py-3 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Custos fixos (reserva)</p>
                <p className="text-xs text-[color:var(--text-muted)] mt-0.5">
                  {plan.accrualLines.length}{" "}
                  {plan.accrualLines.length === 1 ? "conta" : "contas"}
                </p>
              </div>
              <div className="text-right">
                <p className="num font-semibold">
                  −{fmtAUD(plan.fixedCostCents)}
                </p>
                <p className="text-[10px] text-[color:var(--text-muted)]">
                  {pct(plan.fixedCostCents, income)}% do salário
                </p>
              </div>
            </li>
          )}
          {plan.lines.map((line, i) => (
            <li
              key={`${line.bucketId ?? "u"}-${i}`}
              className="rounded-2xl bg-[color:var(--surface-2)] px-4 py-3 flex items-center justify-between"
            >
              <p className="text-sm font-medium">{line.name}</p>
              <div className="text-right">
                <p
                  className="num font-semibold"
                  style={{
                    color:
                      line.reason === "overflow"
                        ? "var(--accent)"
                        : "var(--text)",
                  }}
                >
                  +{fmtAUD(line.amountCents)}
                </p>
                <p className="text-[10px] text-[color:var(--text-muted)]">
                  {pct(line.amountCents, income)}% do salário
                </p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <Link
        href="/avulso/novo"
        className="card card-tight flex items-center gap-3"
        style={{ background: "var(--surface-2)" }}
      >
        <div
          className="rounded-full p-3"
          style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
        >
          <IconBriefcase size={20} />
        </div>
        <div className="flex-1">
          <p className="font-semibold">Trabalho avulso</p>
          <p className="text-xs text-[color:var(--text-muted)]">
            {pt.adhoc.hint}
          </p>
        </div>
        <IconArrowRight size={20} className="text-[color:var(--text-muted)]" />
      </Link>
    </div>
  );
}

function CashRow({
  label,
  amount,
  sign,
  widthPct,
  tone,
}: {
  label: string;
  amount: number;
  sign: "+" | "−";
  widthPct: number;
  tone: "in" | "out";
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2.5 flex-shrink-0 w-14">
        <span
          className="w-2.5 h-2.5 rounded-full"
          style={{
            background: tone === "in" ? "var(--accent)" : "#4dc7ff",
          }}
        />
        <span className="text-sm text-[color:var(--text-muted)] font-medium">
          {label}
        </span>
      </div>
      <div className="flex-1 h-2 rounded-full bg-[color:var(--surface-2)] overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{
            width: `${Math.max(4, Math.min(100, widthPct))}%`,
            background: tone === "in" ? "var(--accent)" : "#4dc7ff",
          }}
        />
      </div>
      <p
        className="num font-bold text-base tabular-nums flex-shrink-0"
        style={{ color: tone === "in" ? "var(--accent)" : "#4dc7ff" }}
      >
        {sign}
        {fmtAUD(amount)}
      </p>
    </div>
  );
}

function YtdTile({
  label,
  amount,
  danger,
}: {
  label: string;
  amount: number;
  danger?: boolean;
}) {
  return (
    <div className="rounded-xl bg-[color:var(--surface-2)] px-3 py-2.5">
      <p className="text-[10px] uppercase tracking-wider text-[color:var(--text-muted)]">
        {label}
      </p>
      <p
        className="num text-sm font-bold mt-1"
        style={{ color: danger ? "var(--danger)" : "var(--text)" }}
      >
        {fmtAUD(amount)}
      </p>
    </div>
  );
}

function pct(part: number, whole: number): string {
  if (whole <= 0) return "0";
  return ((part / whole) * 100).toLocaleString("pt-BR", {
    maximumFractionDigits: 1,
  });
}

export const dynamic = "force-dynamic";
