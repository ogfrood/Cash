import Link from "next/link";

import { createAdhoc } from "@/actions/adhoc";
import { pt } from "@/i18n/pt";
import { todayLocal } from "@/lib/time";

const TODAY = todayLocal();

export default function NovaAvulsaPage() {
  return (
    <form action={createAdhoc} className="flex flex-col gap-5">
      <header className="pt-2">
        <p className="text-sm text-[color:var(--text-muted)]">
          <Link href="/" className="text-[color:var(--accent)]">
            ← Voltar
          </Link>
        </p>
        <h1 className="text-3xl font-extrabold tracking-tight mt-2">
          {pt.adhoc.title}
        </h1>
        <p className="text-sm text-[color:var(--text-muted)] mt-1">
          {pt.adhoc.hint}
        </p>
      </header>

      <div className="card flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <label htmlFor="amount">{pt.adhoc.amount} (AUD)</label>
          <input
            id="amount"
            name="amount"
            inputMode="decimal"
            placeholder="180,00"
            required
            className="text-2xl font-bold"
            style={{ fontVariantNumeric: "tabular-nums" }}
          />
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="kind">{pt.adhoc.kind}</label>
          <select id="kind" name="kind" defaultValue="informal" required>
            <option value="abn">{pt.adhoc.kinds.abn}</option>
            <option value="informal">{pt.adhoc.kinds.informal}</option>
            <option value="tip">{pt.adhoc.kinds.tip}</option>
            <option value="bonus">{pt.adhoc.kinds.bonus}</option>
            <option value="other">{pt.adhoc.kinds.other}</option>
          </select>
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="date">{pt.adhoc.date}</label>
          <input
            id="date"
            name="date"
            type="date"
            defaultValue={TODAY}
            required
          />
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="source">{pt.adhoc.source}</label>
          <input
            id="source"
            name="source"
            placeholder="Ex: cliente do ABN, colega que cobri…"
          />
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="taxSetAside">
            {pt.adhoc.taxSetAside}{" "}
            <span className="text-[11px] text-[color:var(--text-dim)]">
              (opcional — sugerido 15% para ABN)
            </span>
          </label>
          <input
            id="taxSetAside"
            name="taxSetAside"
            inputMode="decimal"
            placeholder="0,00"
          />
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="notes">Notas</label>
          <textarea
            id="notes"
            name="notes"
            rows={2}
            placeholder="Detalhes que queiras lembrar"
          />
        </div>
      </div>

      <div className="flex gap-3">
        <Link
          href="/"
          className="flex-1 text-center py-3 rounded-2xl font-semibold"
          style={{
            background: "var(--surface-2)",
            color: "var(--text-muted)",
          }}
        >
          {pt.common.cancel}
        </Link>
        <button
          type="submit"
          className="flex-1 py-3 rounded-2xl font-bold"
          style={{ background: "var(--accent)", color: "#001a10" }}
        >
          {pt.common.save}
        </button>
      </div>
    </form>
  );
}
