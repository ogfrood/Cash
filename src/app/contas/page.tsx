import Link from "next/link";

import { IconPlus } from "@/components/Icons";
import { activeFixedExpenses } from "@/db/queries";
import { pt } from "@/i18n/pt";
import {
  projectDueDates,
  totalWeeklyFixedCents,
  weeklyAccrualCents,
} from "@/lib/engine/sinking";
import { fmtAUD } from "@/lib/money";
import { daysBetween, fmtDate } from "@/lib/time";

const TODAY = "2026-07-26";

export default async function ContasPage() {
  const expenses = activeFixedExpenses();
  const weeklyTotal = totalWeeklyFixedCents(expenses);

  // Merge everyone's next 3 due dates, sort ascending, take the first 6.
  const upcoming = expenses
    .flatMap((e) =>
      projectDueDates(e.anchorDate, e.cadence, TODAY, 3).map((d) => ({
        expense: e,
        dueDate: d,
      })),
    )
    .sort((a, b) => a.dueDate.localeCompare(b.dueDate))
    .slice(0, 6);

  return (
    <div className="flex flex-col gap-5">
      <header className="flex items-center justify-between pt-2">
        <h1 className="text-3xl font-extrabold tracking-tight">
          {pt.bills.title}
        </h1>
        <Link href="/contas/nova" className="pill pill-accent">
          <IconPlus size={16} />
          Nova
        </Link>
      </header>

      <section className="card">
        <div className="flex items-center justify-between">
          <p className="eyebrow">Reserva semanal</p>
          <p className="text-xs text-[color:var(--text-muted)]">
            das contas fixas
          </p>
        </div>
        <p className="num-hero mt-3" style={{ color: "var(--accent)" }}>
          {fmtAUD(weeklyTotal)}
        </p>
        <p className="text-xs text-[color:var(--text-muted)] mt-1">
          Sai do salário todas as semanas para as caixinhas de reserva
        </p>
      </section>

      <section>
        <p className="eyebrow px-1 mb-3">{pt.bills.upcoming}</p>
        <ul className="flex flex-col gap-2">
          {upcoming.map(({ expense, dueDate }) => {
            const days = daysBetween(TODAY, dueDate);
            return (
              <li
                key={`${expense.id}-${dueDate}`}
                className="card card-tight flex items-center gap-3"
              >
                <div
                  className="w-1 self-stretch rounded-full"
                  style={{
                    background:
                      days <= 3 ? "var(--warn)" : "var(--accent)",
                  }}
                />
                <div className="flex-1">
                  <p className="font-semibold text-sm">{expense.name}</p>
                  <p className="text-[11px] text-[color:var(--text-muted)] mt-0.5">
                    {pt.bills.dueIn(days)} · {fmtDate(dueDate)}
                  </p>
                </div>
                <div className="text-right">
                  <p className="num font-semibold text-sm">
                    {fmtAUD(expense.amountCents)}
                  </p>
                  <p className="text-[10px] text-[color:var(--text-muted)]">
                    {pt.bills.cadence[expense.cadence]}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <section>
        <p className="eyebrow px-1 mb-3">Todas as contas</p>
        <ul className="flex flex-col gap-2">
          {expenses.map((e) => (
            <li key={e.id} className="card card-tight flex items-center gap-3">
              <div className="flex-1">
                <p className="font-semibold text-sm">{e.name}</p>
                <p className="text-[11px] text-[color:var(--text-muted)] mt-0.5">
                  {e.category ?? pt.bills.cadence[e.cadence]}
                </p>
              </div>
              <div className="text-right">
                <p className="num font-semibold text-sm">
                  {fmtAUD(e.amountCents)}
                </p>
                <p className="text-[10px] text-[color:var(--text-muted)]">
                  {fmtAUD(weeklyAccrualCents(e.amountCents, e.cadence))}/sem
                </p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export const dynamic = "force-dynamic";
