import {
  adjustBucket,
  createBucket,
  deleteBucket,
  updateBucket,
} from "@/actions/buckets";
import { IconCaret, IconPlus, IconTrash } from "@/components/Icons";
import { ProgressRing } from "@/components/ProgressRing";
import {
  activeBuckets,
  bucketBalances,
  recentPayPeriods,
  weeklyContributions,
} from "@/db/queries";
import { pt } from "@/i18n/pt";
import { bucketProgress } from "@/lib/engine/allocation";
import { BP_SCALE, fmtAUD } from "@/lib/money";
import { todayLocal } from "@/lib/time";

const TODAY = todayLocal();

const KIND_LABEL: Record<string, string> = {
  goal: "Meta",
  sinking: "Reserva",
  spending: "Gasto",
  overflow: "Sobra livre",
};

const RULE_LABEL: Record<string, string> = {
  percent: "% do salário",
  fixed: "$ fixo por semana",
  fill_to_target: "Encher até à meta",
  fill_paced: "Encher até à data",
  none: "Sem regra",
};

type Bucket = ReturnType<typeof activeBuckets>[number];

export default async function CaixinhasPage() {
  const buckets = activeBuckets();
  const balances = bucketBalances();

  const totalBalance = Object.values(balances).reduce((a, b) => a + b, 0);
  const goal = buckets.filter((b) => b.kind === "goal");
  const sinking = buckets.filter((b) => b.kind === "sinking");
  const spending = buckets.filter((b) => b.kind === "spending");
  const overflow = buckets.filter((b) => b.kind === "overflow");

  return (
    <div className="flex flex-col gap-5">
      <header className="flex items-center justify-between pt-2">
        <h1 className="text-3xl font-extrabold tracking-tight">
          {pt.buckets.title}
        </h1>
        <span className="pill">{buckets.length}</span>
      </header>

      <p className="text-sm text-[color:var(--text-muted)] -mt-3">
        {fmtAUD(totalBalance)} guardados no total
      </p>

      <NewBucketCard />

      {goal.length > 0 && (
        <section className="flex flex-col gap-3">
          <p className="eyebrow px-1">Metas</p>
          {goal.map((b) => (
            <BucketDetails
              key={b.id}
              bucket={b}
              balance={balances[b.id] ?? 0}
            />
          ))}
        </section>
      )}

      {sinking.length > 0 && (
        <section className="flex flex-col gap-3">
          <p className="eyebrow px-1">Reservas para contas</p>
          {sinking.map((b) => (
            <BucketDetails
              key={b.id}
              bucket={b}
              balance={balances[b.id] ?? 0}
            />
          ))}
        </section>
      )}

      {spending.length > 0 && (
        <section className="flex flex-col gap-3">
          <p className="eyebrow px-1">Gastos correntes</p>
          {spending.map((b) => (
            <BucketDetails
              key={b.id}
              bucket={b}
              balance={balances[b.id] ?? 0}
            />
          ))}
        </section>
      )}

      {overflow.length > 0 && (
        <section className="flex flex-col gap-3">
          <p className="eyebrow px-1">Livre</p>
          {overflow.map((b) => (
            <BucketDetails
              key={b.id}
              bucket={b}
              balance={balances[b.id] ?? 0}
            />
          ))}
        </section>
      )}

      {buckets.length === 0 && (
        <div className="card text-center py-8">
          <p className="text-3xl">💚</p>
          <p className="font-bold mt-3">Sem caixinhas ainda</p>
          <p className="text-sm text-[color:var(--text-muted)] mt-1">
            Cria a primeira no botão em cima
          </p>
        </div>
      )}
    </div>
  );
}

function BucketDetails({
  bucket,
  balance,
}: {
  bucket: Bucket;
  balance: number;
}) {
  const contributions = weeklyContributions(bucket.id, 8);
  const progress = bucketProgress({
    bucketId: bucket.id,
    balanceCents: balance,
    targetCents: bucket.targetCents,
    targetDate: bucket.targetDate,
    weeklyContributions: contributions,
    today: TODAY,
  });
  const lastNet =
    recentPayPeriods(1).at(-1)?.actualNetCents ??
    recentPayPeriods(1).at(-1)?.forecastNetCents ??
    recentPayPeriods(1).at(-1)?.manualNetCents ??
    0;
  const share =
    lastNet > 0 && progress.avgWeeklyCents > 0
      ? Math.round((progress.avgWeeklyCents / lastNet) * 100)
      : 0;

  return (
    <details className="card">
      <summary className="flex items-center gap-3">
        <ProgressRing value={progress.progress ?? 0} size={64} stroke={7}>
          <span className="text-xl">{bucket.emoji ?? "💰"}</span>
        </ProgressRing>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="font-bold truncate">{bucket.name}</p>
            {progress.onTrack === false && (
              <span
                className="pill pill-warn"
                style={{ fontSize: 10, padding: "2px 6px" }}
              >
                Atrasado
              </span>
            )}
          </div>
          <p className="num-lg mt-0.5">{fmtAUD(balance)}</p>
          {bucket.targetCents ? (
            <p className="text-[11px] text-[color:var(--text-muted)]">
              de {fmtAUD(bucket.targetCents)} ·{" "}
              {Math.round((progress.progress ?? 0) * 100)}%
            </p>
          ) : (
            <p className="text-[11px] text-[color:var(--text-muted)]">
              {KIND_LABEL[bucket.kind] ?? bucket.kind}
            </p>
          )}
        </div>
        <IconCaret size={22} className="caret" />
      </summary>

      <div className="edit-panel">
        {(progress.avgWeeklyCents > 0 || share > 0) && (
          <div className="grid grid-cols-3 gap-2 text-center">
            <StatTile
              label="Ritmo"
              value={
                progress.avgWeeklyCents > 0
                  ? `${fmtAUD(progress.avgWeeklyCents)}/sem`
                  : "—"
              }
            />
            <StatTile
              label="% salário"
              value={share > 0 ? `${share}%` : "—"}
            />
            <StatTile
              label="Meta em"
              value={progress.projectedDate ?? "—"}
            />
          </div>
        )}

        <form
          action={adjustBucket}
          className="rounded-2xl bg-[color:var(--surface-2)] p-3 flex flex-col gap-2"
        >
          <label className="text-[11px] uppercase tracking-widest text-[color:var(--text-muted)]">
            Ajustar saldo
          </label>
          <input type="hidden" name="bucketId" value={bucket.id} />
          <input type="hidden" name="kind" value="adjustment" />
          <div className="flex gap-2">
            <input
              name="amount"
              inputMode="decimal"
              placeholder="+50 ou -20"
              required
              style={{ background: "var(--surface)", fontSize: 15 }}
            />
            <button type="submit" className="primary shrink-0 px-4">
              Registar
            </button>
          </div>
          <p className="text-[11px] text-[color:var(--text-dim)]">
            Positivo põe dinheiro, negativo tira. Vai para o histórico.
          </p>
        </form>

        <BucketEditForm bucket={bucket} />

        <form action={deleteBucket}>
          <input type="hidden" name="id" value={bucket.id} />
          <button type="submit" className="danger w-full flex items-center justify-center gap-2">
            <IconTrash size={16} /> Apagar caixinha
          </button>
        </form>
      </div>
    </details>
  );
}

function BucketEditForm({ bucket }: { bucket: Bucket }) {
  const percentValue =
    bucket.ruleType === "percent"
      ? (bucket.ruleValue / (BP_SCALE / 100)).toString()
      : "";
  const fixedValue =
    bucket.ruleType === "fixed"
      ? (bucket.ruleValue / 100).toFixed(2)
      : "";
  return (
    <form action={updateBucket} className="flex flex-col gap-3">
      <input type="hidden" name="id" value={bucket.id} />

      <div className="row">
        <div className="flex flex-col gap-1">
          <label>Emoji</label>
          <input
            name="emoji"
            defaultValue={bucket.emoji ?? ""}
            maxLength={4}
            placeholder="💰"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label>Nome</label>
          <input name="name" defaultValue={bucket.name} required />
        </div>
      </div>

      <div className="row">
        <div className="flex flex-col gap-1">
          <label>Tipo</label>
          <select name="kind" defaultValue={bucket.kind}>
            <option value="goal">Meta</option>
            <option value="sinking">Reserva</option>
            <option value="spending">Gasto</option>
            <option value="overflow">Sobra livre</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label>Meta (AUD)</label>
          <input
            name="targetAmount"
            inputMode="decimal"
            defaultValue={
              bucket.targetCents ? (bucket.targetCents / 100).toFixed(2) : ""
            }
            placeholder="opcional"
          />
        </div>
      </div>

      <div className="row">
        <div className="flex flex-col gap-1">
          <label>Como enche</label>
          <select name="ruleType" defaultValue={bucket.ruleType}>
            <option value="percent">% do salário</option>
            <option value="fixed">$ fixo/sem</option>
            <option value="fill_to_target">Encher até meta</option>
            <option value="fill_paced">Encher até à data</option>
            <option value="none">Manual</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label>Valor da regra</label>
          <input
            name="ruleValue"
            inputMode="decimal"
            defaultValue={percentValue || fixedValue}
            placeholder="ex: 20 (%) ou 50 ($)"
          />
        </div>
      </div>

      <div className="row">
        <div className="flex flex-col gap-1">
          <label>Meta até</label>
          <input
            name="targetDate"
            type="date"
            defaultValue={bucket.targetDate ?? ""}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label>Limite/semana</label>
          <input
            name="weeklyCap"
            inputMode="decimal"
            defaultValue={
              bucket.weeklyCapCents
                ? (bucket.weeklyCapCents / 100).toFixed(2)
                : ""
            }
            placeholder="opcional"
          />
        </div>
      </div>

      <input type="hidden" name="priority" value={bucket.priority} />

      <button type="submit" className="primary">
        Guardar
      </button>
    </form>
  );
}

function NewBucketCard() {
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
          <p className="font-bold">Nova caixinha</p>
          <p className="text-[11px] text-[color:var(--text-muted)]">
            Meta, reserva, gasto — cria e define a regra
          </p>
        </div>
        <IconCaret size={22} className="caret" />
      </summary>

      <div className="edit-panel">
        <form action={createBucket} className="flex flex-col gap-3">
          <div className="row">
            <div className="flex flex-col gap-1">
              <label>Emoji</label>
              <input name="emoji" maxLength={4} placeholder="💰" />
            </div>
            <div className="flex flex-col gap-1">
              <label>Nome</label>
              <input name="name" required placeholder="Ex: Viagem" />
            </div>
          </div>

          <div className="row">
            <div className="flex flex-col gap-1">
              <label>Tipo</label>
              <select name="kind" defaultValue="goal">
                <option value="goal">Meta</option>
                <option value="sinking">Reserva</option>
                <option value="spending">Gasto</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label>Meta (AUD)</label>
              <input
                name="targetAmount"
                inputMode="decimal"
                placeholder="opcional"
              />
            </div>
          </div>

          <div className="row">
            <div className="flex flex-col gap-1">
              <label>Como enche</label>
              <select name="ruleType" defaultValue="percent">
                <option value="percent">% do salário</option>
                <option value="fixed">$ fixo/sem</option>
                <option value="fill_to_target">Encher até meta</option>
                <option value="fill_paced">Encher até à data</option>
                <option value="none">Manual</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label>Valor da regra</label>
              <input
                name="ruleValue"
                inputMode="decimal"
                placeholder="ex: 20"
              />
            </div>
          </div>

          <div className="row">
            <div className="flex flex-col gap-1">
              <label>Meta até</label>
              <input name="targetDate" type="date" />
            </div>
            <div className="flex flex-col gap-1">
              <label>Limite/semana</label>
              <input
                name="weeklyCap"
                inputMode="decimal"
                placeholder="opcional"
              />
            </div>
          </div>

          <button type="submit" className="primary">
            Criar caixinha
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

// Silence unused import when RULE_LABEL is only referenced by a possible
// future line — keep the map close to where the enum lives.
void RULE_LABEL;

export const dynamic = "force-dynamic";
