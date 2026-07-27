import {
  createExpense,
  deleteExpense,
  updateExpense,
} from "@/actions/expenses";
import { IconCaret, IconPlus, IconTrash } from "@/components/Icons";
import { activeBuckets, activeFixedExpenses } from "@/db/queries";
import { pt } from "@/i18n/pt";
import {
  projectDueDates,
  totalWeeklyFixedCents,
  weeklyAccrualCents,
} from "@/lib/engine/sinking";
import { fmtAUD } from "@/lib/money";
import { daysBetween, fmtDate, todayLocal } from "@/lib/time";

const TODAY = todayLocal();

type Expense = ReturnType<typeof activeFixedExpenses>[number];
type Bucket = ReturnType<typeof activeBuckets>[number];

export default async function ContasPage() {
  const expenses = activeFixedExpenses();
  const buckets = activeBuckets();
  const sinkingBuckets = buckets.filter(
    (b) => b.kind === "sinking" || b.kind === "overflow",
  );
  const weeklyTotal = totalWeeklyFixedCents(expenses);

  const upcoming = expenses
    .flatMap((e) =>
      projectDueDates(e.anchorDate, e.cadence, TODAY, 2).map((d) => ({
        expense: e,
        dueDate: d,
      })),
    )
    .sort((a, b) => a.dueDate.localeCompare(b.dueDate))
    .slice(0, 6);

  return (
    <div className="flex flex-col gap-5">
      <header className="pt-2">
        <h1 className="text-3xl font-extrabold tracking-tight">
          {pt.bills.title}
        </h1>
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

      <NewExpenseCard sinkingBuckets={sinkingBuckets} />

      {expenses.length === 0 ? (
        <div className="card text-center py-8">
          <p className="text-3xl">📅</p>
          <p className="font-bold mt-3">Sem contas registadas</p>
          <p className="text-sm text-[color:var(--text-muted)] mt-1">
            Adiciona aluguel, internet, ginásio, subscrições…
          </p>
        </div>
      ) : (
        <>
          {upcoming.length > 0 && (
            <section>
              <p className="eyebrow px-1 mb-3">Próximas</p>
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
          )}

          <section className="flex flex-col gap-3">
            <p className="eyebrow px-1">Todas as contas</p>
            {expenses.map((e) => (
              <ExpenseDetails
                key={e.id}
                expense={e}
                sinkingBuckets={sinkingBuckets}
              />
            ))}
          </section>
        </>
      )}
    </div>
  );
}

function ExpenseDetails({
  expense,
  sinkingBuckets,
}: {
  expense: Expense;
  sinkingBuckets: Bucket[];
}) {
  const weekly = weeklyAccrualCents(expense.amountCents, expense.cadence);
  return (
    <details className="card">
      <summary className="flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm truncate">{expense.name}</p>
          <p className="text-[11px] text-[color:var(--text-muted)] mt-0.5">
            {expense.category ?? pt.bills.cadence[expense.cadence]}
          </p>
        </div>
        <div className="text-right shrink-0">
          <p className="num font-semibold text-sm">
            {fmtAUD(expense.amountCents)}
          </p>
          <p className="text-[10px] text-[color:var(--text-muted)]">
            {fmtAUD(weekly)}/sem
          </p>
        </div>
        <IconCaret size={20} className="caret" />
      </summary>

      <div className="edit-panel">
        <ExpenseEditForm expense={expense} sinkingBuckets={sinkingBuckets} />
        <form action={deleteExpense}>
          <input type="hidden" name="id" value={expense.id} />
          <button
            type="submit"
            className="danger w-full flex items-center justify-center gap-2"
          >
            <IconTrash size={16} /> Apagar conta
          </button>
        </form>
      </div>
    </details>
  );
}

function ExpenseEditForm({
  expense,
  sinkingBuckets,
}: {
  expense: Expense;
  sinkingBuckets: Bucket[];
}) {
  return (
    <form action={updateExpense} className="flex flex-col gap-3">
      <input type="hidden" name="id" value={expense.id} />

      <div className="row">
        <div className="flex flex-col gap-1">
          <label>Nome</label>
          <input name="name" defaultValue={expense.name} required />
        </div>
        <div className="flex flex-col gap-1">
          <label>Categoria</label>
          <input
            name="category"
            defaultValue={expense.category ?? ""}
            placeholder="opcional"
          />
        </div>
      </div>

      <div className="row">
        <div className="flex flex-col gap-1">
          <label>Valor (AUD)</label>
          <input
            name="amount"
            inputMode="decimal"
            defaultValue={(expense.amountCents / 100).toFixed(2)}
            required
          />
        </div>
        <div className="flex flex-col gap-1">
          <label>Cadência</label>
          <select name="cadence" defaultValue={expense.cadence}>
            <option value="weekly">Semanal</option>
            <option value="fortnightly">Quinzenal</option>
            <option value="monthly">Mensal</option>
            <option value="quarterly">Trimestral</option>
            <option value="yearly">Anual</option>
          </select>
        </div>
      </div>

      <div className="row">
        <div className="flex flex-col gap-1">
          <label>Próximo vencimento</label>
          <input
            name="anchorDate"
            type="date"
            defaultValue={expense.anchorDate}
            required
          />
        </div>
        <div className="flex flex-col gap-1">
          <label>Reserva na caixinha</label>
          <select
            name="sinkingBucketId"
            defaultValue={expense.sinkingBucketId?.toString() ?? ""}
          >
            <option value="">— nenhuma —</option>
            {sinkingBuckets.map((b) => (
              <option key={b.id} value={b.id}>
                {b.emoji ?? "📦"} {b.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <label>Notas</label>
        <input
          name="notes"
          defaultValue={expense.notes ?? ""}
          placeholder="opcional"
        />
      </div>

      <button type="submit" className="primary">
        Guardar
      </button>
    </form>
  );
}

function NewExpenseCard({ sinkingBuckets }: { sinkingBuckets: Bucket[] }) {
  return (
    <details className="card" style={{ borderColor: "var(--accent-dim)" }}>
      <summary className="flex items-center gap-3">
        <div
          className="w-10 h-10 rounded-full grid place-items-center"
          style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
        >
          <IconPlus size={22} />
        </div>
        <div className="flex-1">
          <p className="font-bold">Nova conta</p>
          <p className="text-[11px] text-[color:var(--text-muted)]">
            Aluguel, internet, assinatura, ginásio…
          </p>
        </div>
        <IconCaret size={22} className="caret" />
      </summary>

      <div className="edit-panel">
        <form action={createExpense} className="flex flex-col gap-3">
          <div className="row">
            <div className="flex flex-col gap-1">
              <label>Nome</label>
              <input name="name" required placeholder="Ex: Aluguel" />
            </div>
            <div className="flex flex-col gap-1">
              <label>Categoria</label>
              <input name="category" placeholder="opcional" />
            </div>
          </div>

          <div className="row">
            <div className="flex flex-col gap-1">
              <label>Valor (AUD)</label>
              <input
                name="amount"
                inputMode="decimal"
                required
                placeholder="1600,00"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label>Cadência</label>
              <select name="cadence" defaultValue="monthly">
                <option value="weekly">Semanal</option>
                <option value="fortnightly">Quinzenal</option>
                <option value="monthly">Mensal</option>
                <option value="quarterly">Trimestral</option>
                <option value="yearly">Anual</option>
              </select>
            </div>
          </div>

          <div className="row">
            <div className="flex flex-col gap-1">
              <label>Próximo vencimento</label>
              <input
                name="anchorDate"
                type="date"
                required
                defaultValue={TODAY}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label>Reserva na caixinha</label>
              <select name="sinkingBucketId" defaultValue="">
                <option value="">— nenhuma —</option>
                {sinkingBuckets.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.emoji ?? "📦"} {b.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <button type="submit" className="primary">
            Criar conta
          </button>
        </form>
      </div>
    </details>
  );
}

export const dynamic = "force-dynamic";
