import {
  createDebt,
  deleteDebt,
  logDebtPayment,
  updateDebt,
} from "@/actions/debts";
import { IconCaret, IconPlus, IconTrash } from "@/components/Icons";
import { activeDebts, debtPaidTotals, debtPayments } from "@/db/queries";
import { debtProgress } from "@/lib/engine/debts";
import { fmtAUD } from "@/lib/money";
import { fmtDate, todayLocal } from "@/lib/time";

const TODAY = todayLocal();

const KIND_LABEL: Record<string, string> = {
  credit_card: "Cartão de crédito",
  loan: "Empréstimo",
  personal: "Pessoal",
  bnpl: "Compra parcelada",
  other: "Outro",
};

type Debt = ReturnType<typeof activeDebts>[number];

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
  const overall = totalPrincipal > 0 ? totalPaid / totalPrincipal : 0;

  return (
    <div className="flex flex-col gap-5">
      <header className="pt-2">
        <h1 className="text-3xl font-extrabold tracking-tight">Dívidas</h1>
        <p className="text-sm text-[color:var(--text-muted)] mt-1">
          Pagar aos poucos, todos os dias
        </p>
      </header>

      {debts.length > 0 && (
        <section className="card">
          <p className="eyebrow">A dever no total</p>
          <p className="num-hero mt-2" style={{ color: "var(--warn)" }}>
            {fmtAUD(totalOwed)}
          </p>
          <div className="h-2 rounded-full bg-[color:var(--surface-3)] overflow-hidden mt-4">
            <div
              className="h-full"
              style={{
                width: `${Math.round(overall * 100)}%`,
                background: "var(--accent)",
              }}
            />
          </div>
          <div className="flex justify-between text-xs mt-2">
            <span className="text-[color:var(--text-muted)]">
              Pago {fmtAUD(totalPaid)}
            </span>
            <span style={{ color: "var(--accent)" }}>
              {Math.round(overall * 100)}%
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
      )}

      <NewDebtCard />

      {rows.length === 0 ? (
        <div className="card text-center py-8">
          <p className="text-3xl">🎉</p>
          <p className="font-bold mt-3">Sem dívidas registadas</p>
          <p className="text-sm text-[color:var(--text-muted)] mt-1">
            Adiciona a primeira acima
          </p>
        </div>
      ) : (
        <section className="flex flex-col gap-3">
          {rows.map(({ debt, progress }) => (
            <DebtDetails key={debt.id} debt={debt} progress={progress} />
          ))}
        </section>
      )}
    </div>
  );
}

function DebtDetails({
  debt,
  progress,
}: {
  debt: Debt;
  progress: ReturnType<typeof debtProgress>;
}) {
  const recentPayments = debtPayments(debt.id).slice(0, 5);
  return (
    <details className="card">
      <summary className="flex items-center gap-3">
        <span className="text-2xl">{debt.emoji ?? "💳"}</span>
        <div className="flex-1 min-w-0">
          <p className="font-bold truncate">{debt.name}</p>
          <p className="text-[11px] text-[color:var(--text-muted)]">
            {KIND_LABEL[debt.kind] ?? debt.kind}
          </p>
          <div className="h-1 rounded-full bg-[color:var(--surface-3)] overflow-hidden mt-2">
            <div
              className="h-full"
              style={{
                width: `${Math.round(progress.progress * 100)}%`,
                background: "var(--accent)",
              }}
            />
          </div>
        </div>
        <div className="text-right shrink-0">
          <p className="num font-bold text-sm" style={{ color: "var(--warn)" }}>
            {fmtAUD(progress.balanceCents)}
          </p>
          <p className="text-[10px] text-[color:var(--text-muted)]">
            de {fmtAUD(debt.principalCents)}
          </p>
        </div>
        <IconCaret size={20} className="caret" />
      </summary>

      <div className="edit-panel">
        <div className="grid grid-cols-3 gap-2 text-center">
          <StatTile
            label="Por dia"
            value={fmtAUD(debt.dailyTargetCents)}
          />
          <StatTile
            label={progress.daysToZero === null ? "Sem ritmo" : "Livre em"}
            value={
              progress.projectedZeroDate
                ? fmtDate(progress.projectedZeroDate)
                : "—"
            }
          />
          <StatTile
            label="Precisa"
            value={
              progress.requiredDailyCents
                ? `${fmtAUD(progress.requiredDailyCents)}/dia`
                : "—"
            }
          />
        </div>

        <form
          action={logDebtPayment}
          className="rounded-2xl bg-[color:var(--surface-2)] p-3 flex flex-col gap-2"
        >
          <label className="text-[11px] uppercase tracking-widest text-[color:var(--text-muted)]">
            Registar pagamento
          </label>
          <input type="hidden" name="debtId" value={debt.id} />
          <div className="flex gap-2">
            <input
              name="amount"
              inputMode="decimal"
              placeholder="Valor"
              required
              style={{ background: "var(--surface)", fontSize: 15 }}
            />
            <input
              name="date"
              type="date"
              defaultValue={TODAY}
              required
              style={{ background: "var(--surface)", maxWidth: 160 }}
            />
          </div>
          <input name="note" placeholder="Nota (opcional)" style={{ background: "var(--surface)", fontSize: 14 }} />
          <button type="submit" className="primary">
            Adicionar pagamento
          </button>
        </form>

        {recentPayments.length > 0 && (
          <div className="text-xs text-[color:var(--text-muted)]">
            <p className="mb-2">Últimos pagamentos:</p>
            <ul className="flex flex-col gap-1">
              {recentPayments.map((p) => (
                <li
                  key={p.id}
                  className="flex justify-between"
                >
                  <span>{fmtDate(p.date)}</span>
                  <span className="num text-[color:var(--text)] font-semibold">
                    {fmtAUD(p.amountCents)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <DebtEditForm debt={debt} />

        <form action={deleteDebt}>
          <input type="hidden" name="id" value={debt.id} />
          <button
            type="submit"
            className="danger w-full flex items-center justify-center gap-2"
          >
            <IconTrash size={16} /> Apagar dívida
          </button>
        </form>
      </div>
    </details>
  );
}

function DebtEditForm({ debt }: { debt: Debt }) {
  return (
    <form action={updateDebt} className="flex flex-col gap-3">
      <input type="hidden" name="id" value={debt.id} />

      <div className="row">
        <div className="flex flex-col gap-1">
          <label>Emoji</label>
          <input name="emoji" defaultValue={debt.emoji ?? ""} maxLength={4} />
        </div>
        <div className="flex flex-col gap-1">
          <label>Nome</label>
          <input name="name" defaultValue={debt.name} required />
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <label>Tipo</label>
        <select name="kind" defaultValue={debt.kind}>
          <option value="credit_card">Cartão de crédito</option>
          <option value="loan">Empréstimo</option>
          <option value="personal">Pessoal</option>
          <option value="bnpl">Compra parcelada</option>
          <option value="other">Outro</option>
        </select>
      </div>

      <div className="row">
        <div className="flex flex-col gap-1">
          <label>Valor original</label>
          <input
            name="principal"
            inputMode="decimal"
            defaultValue={(debt.principalCents / 100).toFixed(2)}
            required
          />
        </div>
        <div className="flex flex-col gap-1">
          <label>Saldo atual</label>
          <input
            name="currentBalance"
            inputMode="decimal"
            defaultValue={
              debt.balanceOverrideCents != null
                ? (debt.balanceOverrideCents / 100).toFixed(2)
                : ""
            }
            placeholder="deriva dos pagamentos"
          />
        </div>
      </div>

      <div className="row">
        <div className="flex flex-col gap-1">
          <label>Por dia (AUD)</label>
          <input
            name="dailyTarget"
            inputMode="decimal"
            defaultValue={(debt.dailyTargetCents / 100).toFixed(2)}
            required
          />
        </div>
        <div className="flex flex-col gap-1">
          <label>Meta até</label>
          <input name="targetDate" type="date" defaultValue={debt.targetDate ?? ""} />
        </div>
      </div>

      <button type="submit" className="primary">
        Guardar
      </button>
    </form>
  );
}

function NewDebtCard() {
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
          <p className="font-bold">Nova dívida</p>
          <p className="text-[11px] text-[color:var(--text-muted)]">
            Cartão, empréstimo, compra parcelada
          </p>
        </div>
        <IconCaret size={22} className="caret" />
      </summary>

      <div className="edit-panel">
        <form action={createDebt} className="flex flex-col gap-3">
          <div className="row">
            <div className="flex flex-col gap-1">
              <label>Emoji</label>
              <input name="emoji" maxLength={4} placeholder="💳" />
            </div>
            <div className="flex flex-col gap-1">
              <label>Nome</label>
              <input name="name" required placeholder="Ex: Cartão ANZ" />
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <label>Tipo</label>
            <select name="kind" defaultValue="credit_card">
              <option value="credit_card">Cartão de crédito</option>
              <option value="loan">Empréstimo</option>
              <option value="personal">Pessoal</option>
              <option value="bnpl">Compra parcelada</option>
              <option value="other">Outro</option>
            </select>
          </div>

          <div className="row">
            <div className="flex flex-col gap-1">
              <label>Valor original</label>
              <input name="principal" inputMode="decimal" required placeholder="2500,00" />
            </div>
            <div className="flex flex-col gap-1">
              <label>Saldo atual</label>
              <input name="currentBalance" inputMode="decimal" placeholder="opcional" />
            </div>
          </div>

          <div className="row">
            <div className="flex flex-col gap-1">
              <label>Por dia (AUD)</label>
              <input name="dailyTarget" inputMode="decimal" required placeholder="10,00" />
            </div>
            <div className="flex flex-col gap-1">
              <label>Meta até</label>
              <input name="targetDate" type="date" />
            </div>
          </div>

          <button type="submit" className="primary">
            Criar dívida
          </button>
        </form>
      </div>
    </details>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-[color:var(--surface-2)] px-3 py-2.5">
      <p className="text-[10px] uppercase tracking-widest text-[color:var(--text-muted)]">
        {label}
      </p>
      <p className="num text-xs font-bold mt-1 truncate">{value}</p>
    </div>
  );
}

export const dynamic = "force-dynamic";
