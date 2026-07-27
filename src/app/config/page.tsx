import {
  updateBreakDefaults,
  updateTaxSettings,
} from "@/actions/settings";
import { IconCaret } from "@/components/Icons";
import { currentSettings } from "@/db/queries";
import { fmtBp } from "@/lib/money";

export default async function ConfigPage() {
  const { app, tax } = currentSettings("2026-27");

  const statusLabel: Record<string, string> = {
    WHM: "Working Holiday Maker (417/462)",
    RESIDENT: "Residente fiscal (com threshold)",
    FOREIGN: "Não-residente",
  };

  return (
    <div className="flex flex-col gap-5">
      <header className="pt-2">
        <h1 className="text-3xl font-extrabold tracking-tight">Ajustes</h1>
        <p className="text-sm text-[color:var(--text-muted)] mt-1">
          Personaliza como a app calcula tudo
        </p>
      </header>

      <details className="card" open>
        <summary className="flex items-center gap-3">
          <div className="flex-1">
            <p className="eyebrow">Estatuto fiscal</p>
            <p className="font-bold mt-1">
              {statusLabel[tax?.status ?? "WHM"] ?? "—"}
            </p>
            <p className="text-[11px] text-[color:var(--text-muted)] mt-0.5">
              FY {tax?.fyLabel ?? "2026-27"} · Super{" "}
              {fmtBp(tax?.superGuaranteeBp ?? 1200)}
            </p>
          </div>
          <IconCaret size={22} className="caret" />
        </summary>
        <div className="edit-panel">
          <form action={updateTaxSettings} className="flex flex-col gap-3">
            <input type="hidden" name="fyLabel" value={tax?.fyLabel ?? "2026-27"} />

            <div className="flex flex-col gap-1">
              <label>Estatuto</label>
              <select name="status" defaultValue={tax?.status ?? "WHM"}>
                <option value="WHM">Working Holiday (417/462)</option>
                <option value="RESIDENT">Residente + threshold</option>
                <option value="FOREIGN">Não-residente</option>
              </select>
            </div>

            <div className="row">
              <div className="flex flex-col gap-1">
                <label>Super Guarantee (%)</label>
                <input
                  name="superPercent"
                  inputMode="decimal"
                  defaultValue={((tax?.superGuaranteeBp ?? 1200) / 100).toString()}
                  required
                />
              </div>
              <div className="flex flex-col gap-1">
                <label>Método de retenção</label>
                <select
                  name="withholdingMethod"
                  defaultValue={tax?.withholdingMethod ?? "annualised"}
                >
                  <option value="annualised">
                    Anualizado (bate com Xero)
                  </option>
                  <option value="cumulative">
                    Cumulativo (mais preciso)
                  </option>
                </select>
              </div>
            </div>

            <button type="submit" className="primary">
              Guardar
            </button>
          </form>
        </div>
      </details>

      <details className="card">
        <summary className="flex items-center gap-3">
          <div className="flex-1">
            <p className="eyebrow">Pausas</p>
            <p className="font-bold mt-1">
              Pausa {app?.defaultBreakMinutes ?? 30} min acima de{" "}
              {app?.defaultBreakThresholdMinutes ?? 300} min
            </p>
            <p className="text-[11px] text-[color:var(--text-muted)] mt-0.5">
              Usado quando o email não traz a pausa
            </p>
          </div>
          <IconCaret size={22} className="caret" />
        </summary>
        <div className="edit-panel">
          <form
            action={updateBreakDefaults}
            className="flex flex-col gap-3"
          >
            <div className="row">
              <div className="flex flex-col gap-1">
                <label>Pausa (min)</label>
                <input
                  name="defaultBreakMinutes"
                  inputMode="numeric"
                  defaultValue={app?.defaultBreakMinutes ?? 30}
                  required
                />
              </div>
              <div className="flex flex-col gap-1">
                <label>A partir de (min)</label>
                <input
                  name="defaultBreakThresholdMinutes"
                  inputMode="numeric"
                  defaultValue={app?.defaultBreakThresholdMinutes ?? 300}
                  required
                />
              </div>
            </div>
            <button type="submit" className="primary">
              Guardar
            </button>
          </form>
        </div>
      </details>

      <div className="card">
        <p className="eyebrow mb-2">Email — sincronização</p>
        <p className="text-sm text-[color:var(--text-muted)]">
          Ainda por configurar (IMAP). Fica para a Fase 3.
        </p>
      </div>

      <div className="card">
        <p className="eyebrow mb-2">Sobre</p>
        <p className="text-sm">Cash · Fase 1</p>
        <p className="text-xs text-[color:var(--text-muted)] mt-1">
          Local · SQLite · sem tracking externo
        </p>
      </div>
    </div>
  );
}

export const dynamic = "force-dynamic";
