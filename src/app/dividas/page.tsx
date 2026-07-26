import Link from "next/link";

import { IconPlus } from "@/components/Icons";
import { activeDebts, debtPaidTotals } from "@/db/queries";
import { debtProgress } from "@/lib/engine/debts";
import { fmtAUD } from "@/lib/money";
import { fmtDate } from "@/lib/time";

const TODAY = "2026-07-26";

const KIND_LABEL: Record<string, string> = {
  credit_card: "Cartão de crédito",
  loan: "Empréstimo",
  personal: "Pessoal",
  bnpl: "Compra parcelada",
  other: "Outro",
};

export default async function DividasPage() {
  const debts = activeDebts();
  const paidTotals = debtPaidTotals();

  const rows = debts.map((d) => ({
    debt: d,
    progress: debtProgress({
      principalCents: d.principalCents,
      balanceOverrideCents: d.balanceOverrideCents,
      totalPaidCents: paidTotals[d.id] ?? 0,
      dailyTargetCents: d.dailyTargetCents,
      targetDate: d.targetDate,
      today: TODAY,
    }),
  }));

  const totalOwed = rows.reduce((s, r) => s + r.progress.balanceCents, 0);
  const totalPaid = rows.reduce((s, r) => s + r.progress.paidCents, 0);
  const totalDaily = debts.reduce((s, d) => s + d.dailyTargetCents, 0);
  const totalPrincipal = debts.reduce((s, d) => s + d.principalCents, 0);
  const overallProgress =
    totalPrincipal > 0 ? totalPaid / totalPrincipal : 0;

  return (
    <div className="flex flex-col gap-5">
      <header className="flex items-center justify-between pt-2">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight">Dívidas</h1>
          <p className="text-sm text-[color:var(--text-muted)] mt-1">
            Pagar aos poucos, todos os dias
          </p>
        </div>
        <Link href="/dividas/nova" className="pill pill-accent">
          <IconPlus size={16} />
          Nova
        </Link>
      </header>

      {debts.length === 0 ? (
        <div className="card text-center py-10">
          <p className="text-3xl">🎉</p>
          <p className="font-bold mt-3">Sem dívidas registadas</p>
          <p className="text-sm text-[color:var(--text-muted)] mt-1">
            Adiciona a primeira para começares a acompanhar o pagamento
          </p>
        </div>
      ) : (
        <>
          {/* Summary card */}
          <section className="card">
            <p className="eyebrow">A dever no total</p>
            <p className="num-hero mt-2" style={{ color: "var(--warn)" }}>
              {fmtAUD(totalOwed)}
            </p>
            <div className="h-2 rounded-full bg-[color:var(--surface-3)] overflow-hidden mt-4">
              <div
                className="h-full"
                style={{
                  width: `${Math.round(overallProgress * 100)}%`,
                  background: "var(--accent)",
                }}
              />
            </div>
            <div className="flex justify-between text-xs mt-2">
              <span className="text-[color:var(--text-muted)]">
                Pago {fmtAUD(totalPaid)}
              </span>
              <span style={{ color: "var(--accent)" }}>
                {Math.round(overallProgress * 100)}%
              </span>
            </div>
            {totalDaily > 0 && (
              <div className="mt-4 pt-4 border-t border-[color:var(--border)] flex items-center justify-between">
                <div>
                  <p className="text-xs text-[color:var(--text-muted)]">
                    A pôr de lado por dia
                  </p>
                  <p className="num-lg mt-1" style={{ color: "var(--accent)" }}>
                    {fmtAUD(totalDaily)}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-[color:var(--text-muted)]">
                    Por mês
                  </p>
                  <p className="num font-semibold text-sm mt-1">
                    {fmtAUD(totalDaily * 30)}
                  </p>
                </div>
              </div>
            )}
          </section>

          <section className="flex flex-col gap-3">
            {rows.map(({ debt, progress }) => (
              <DebtCard key={debt.id} debt={debt} progress={progress} />
            ))}
          </section>
        </>
      )}
    </div>
  );
}

function DebtCard({
  debt,
  progress,
}: {
  debt: ReturnType<typeof activeDebts>[number];
  progress: ReturnType<typeof debtProgress>;
}) {
  return (
    <Link href={`/dividas/${debt.id}`} className="card flex flex-col gap-3">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{debt.emoji ?? "💳"}</span>
          <div>
            <p className="font-bold">{debt.name}</p>
            <p className="text-[11px] text-[color:var(--text-muted)]">
              {KIND_LABEL[debt.kind] ?? debt.kind}
            </p>
          </div>
        </div>
        {progress.onTrack !== null && (
          <span
            className={`pill ${progress.onTrack ? "pill-accent" : "pill-warn"}`}
            style={{ fontSize: 10, padding: "3px 8px" }}
          >
            {progress.onTrack ? "No ritmo" : "Precisa apertar"}
          </span>
        )}
      </div>

      <div className="flex items-baseline justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-[color:var(--text-muted)]">
            Falta pagar
          </p>
          <p className="num-lg" style={{ color: "var(--warn)" }}>
            {fmtAUD(progress.balanceCents)}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[10px] uppercase tracking-widest text-[color:var(--text-muted)]">
            De
          </p>
          <p className="num font-semibold text-sm">
            {fmtAUD(debt.principalCents)}
          </p>
        </div>
      </div>

      <div className="h-1.5 rounded-full bg-[color:var(--surface-3)] overflow-hidden">
        <div
          className="h-full"
          style={{
            width: `${Math.round(progress.progress * 100)}%`,
            background: "var(--accent)",
          }}
        />
      </div>

      <div className="grid grid-cols-2 gap-2 pt-1">
        <div className="rounded-xl bg-[color:var(--surface-2)] px-3 py-2">
          <p className="text-[10px] uppercase tracking-widest text-[color:var(--text-muted)]">
            Por dia
          </p>
          <p className="num font-bold text-sm mt-0.5" style={{ color: "var(--accent)" }}>
            {fmtAUD(debt.dailyTargetCents)}
          </p>
        </div>
        <div className="rounded-xl bg-[color:var(--surface-2)] px-3 py-2">
          <p className="text-[10px] uppercase tracking-widest text-[color:var(--text-muted)]">
            {progress.daysToZero === null ? "Sem meta" : "Livre em"}
          </p>
          <p className="num font-bold text-sm mt-0.5">
            {progress.projectedZeroDate
              ? fmtDate(progress.projectedZeroDate)
              : "—"}
          </p>
        </div>
      </div>

      {progress.requiredDailyCents != null &&
        progress.requiredDailyCents > debt.dailyTargetCents && (
          <p
            className="text-[11px]"
            style={{ color: "var(--warn)" }}
          >
            Para pagar até {debt.targetDate}: {fmtAUD(progress.requiredDailyCents)}/dia
          </p>
        )}
    </Link>
  );
}

export const dynamic = "force-dynamic";
