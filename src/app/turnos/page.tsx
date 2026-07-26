import { recentPayPeriods } from "@/db/queries";
import { fmtAUD } from "@/lib/money";
import { fmtWeekRange } from "@/lib/time";

export default async function TurnosPage() {
  const periods = recentPayPeriods(8).reverse();

  return (
    <div className="flex flex-col gap-5">
      <header className="pt-2">
        <h1 className="text-3xl font-extrabold tracking-tight">Turnos</h1>
        <p className="text-sm text-[color:var(--text-muted)] mt-1">
          Sincronizados do email da Tanda (em breve)
        </p>
      </header>

      <div className="card">
        <p className="eyebrow mb-3">Histórico de semanas</p>
        <ul className="flex flex-col divide-y divide-[color:var(--border)]">
          {periods.map((p) => {
            const gross =
              p.actualGrossCents ?? p.forecastGrossCents ?? 0;
            const net = p.actualNetCents ?? p.forecastNetCents ?? 0;
            const minutes = p.forecastMinutes ?? 0;
            return (
              <li
                key={p.id}
                className="py-3 flex items-center justify-between"
              >
                <div>
                  <p className="text-sm font-semibold">
                    {fmtWeekRange(p.weekStart)}
                  </p>
                  <p className="text-[11px] text-[color:var(--text-muted)]">
                    {(minutes / 60).toLocaleString("pt-BR", {
                      maximumFractionDigits: 1,
                    })}
                    h ·{" "}
                    {p.status === "reconciled" ? "Reconciliado" : "Previsto"}
                  </p>
                </div>
                <div className="text-right">
                  <p className="num font-bold">{fmtAUD(net)}</p>
                  <p className="text-[10px] text-[color:var(--text-muted)]">
                    bruto {fmtAUD(gross)}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

export const dynamic = "force-dynamic";
