import Link from "next/link";

import { createDebt } from "@/actions/debts";

const TODAY = "2026-07-26";

export default function NovaDividaPage() {
  return (
    <form action={createDebt} className="flex flex-col gap-5">
      <header className="pt-2">
        <p className="text-sm">
          <Link href="/dividas" className="text-[color:var(--accent)]">
            ← Voltar
          </Link>
        </p>
        <h1 className="text-3xl font-extrabold tracking-tight mt-2">
          Nova dívida
        </h1>
      </header>

      <div className="card flex flex-col gap-4">
        <div className="grid grid-cols-[80px_1fr] gap-3">
          <div className="flex flex-col gap-2">
            <label htmlFor="emoji">Emoji</label>
            <input id="emoji" name="emoji" placeholder="💳" maxLength={4} />
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor="name">Nome</label>
            <input
              id="name"
              name="name"
              required
              placeholder="Ex: Cartão ANZ"
            />
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="kind">Tipo</label>
          <select id="kind" name="kind" defaultValue="credit_card">
            <option value="credit_card">Cartão de crédito</option>
            <option value="loan">Empréstimo</option>
            <option value="personal">Pessoal</option>
            <option value="bnpl">Compra parcelada (Afterpay/Zip)</option>
            <option value="other">Outro</option>
          </select>
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="principal">Valor original (AUD)</label>
          <input
            id="principal"
            name="principal"
            inputMode="decimal"
            required
            placeholder="2500,00"
            className="text-2xl font-bold"
            style={{ fontVariantNumeric: "tabular-nums" }}
          />
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="currentBalance">
            Saldo atual{" "}
            <span className="text-[11px] text-[color:var(--text-dim)]">
              (deixa em branco se ainda não pagaste nada)
            </span>
          </label>
          <input
            id="currentBalance"
            name="currentBalance"
            inputMode="decimal"
            placeholder="2500,00"
          />
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="dailyTarget">Quanto pôr de lado por dia</label>
          <input
            id="dailyTarget"
            name="dailyTarget"
            inputMode="decimal"
            required
            placeholder="10,00"
          />
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="targetDate">
            Meta de ficar sem dívida{" "}
            <span className="text-[11px] text-[color:var(--text-dim)]">
              (opcional)
            </span>
          </label>
          <input id="targetDate" name="targetDate" type="date" min={TODAY} />
        </div>
      </div>

      <div className="flex gap-3">
        <Link
          href="/dividas"
          className="flex-1 text-center py-3 rounded-2xl font-semibold"
          style={{
            background: "var(--surface-2)",
            color: "var(--text-muted)",
          }}
        >
          Cancelar
        </Link>
        <button
          type="submit"
          className="flex-1 py-3 rounded-2xl font-bold"
          style={{ background: "var(--accent)", color: "#001a10" }}
        >
          Adicionar
        </button>
      </div>
    </form>
  );
}
