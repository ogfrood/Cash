import Link from "next/link";

import { ProgressRing } from "@/components/ProgressRing";
import { IconPlus } from "@/components/Icons";
import {
  activeBuckets,
  bucketBalances,
  recentPayPeriods,
  weeklyContributions,
} from "@/db/queries";
import { pt } from "@/i18n/pt";
import { bucketProgress } from "@/lib/engine/allocation";
import { fmtAUD } from "@/lib/money";

const TODAY = "2026-07-26";

export default async function CaixinhasPage() {
  const buckets = activeBuckets();
  const balances = bucketBalances();
  const periods = recentPayPeriods(1);
  const lastNet =
    periods.at(-1)?.actualNetCents ??
    periods.at(-1)?.forecastNetCents ??
    periods.at(-1)?.manualNetCents ??
    0;

  const goal = buckets.filter((b) => b.kind === "goal");
  const sinking = buckets.filter((b) => b.kind === "sinking");
  const overflow = buckets.filter((b) => b.kind === "overflow");

  return (
    <div className="flex flex-col gap-5">
      <header className="flex items-center justify-between pt-2">
        <h1 className="text-3xl font-extrabold tracking-tight">
          {pt.buckets.title}
        </h1>
        <Link href="/caixinhas/nova" className="pill pill-accent">
          <IconPlus size={16} />
          Nova
        </Link>
      </header>

      <p className="text-sm text-[color:var(--text-muted)] -mt-3">
        {buckets.length} caixinhas · {fmtAUD(sumBalances(balances))} guardados
      </p>

      {goal.length > 0 && (
        <section className="flex flex-col gap-3">
          <p className="eyebrow px-1">Metas</p>
          <div className="grid grid-cols-2 gap-3">
            {goal.map((b) => (
              <BucketCard
                key={b.id}
                bucket={b}
                balance={balances[b.id] ?? 0}
                lastNet={lastNet}
              />
            ))}
          </div>
        </section>
      )}

      {sinking.length > 0 && (
        <section className="flex flex-col gap-3">
          <p className="eyebrow px-1">Reservas para contas</p>
          <ul className="flex flex-col gap-2">
            {sinking.map((b) => (
              <SinkingRow
                key={b.id}
                bucket={b}
                balance={balances[b.id] ?? 0}
              />
            ))}
          </ul>
        </section>
      )}

      {overflow.length > 0 && (
        <section className="flex flex-col gap-3">
          <p className="eyebrow px-1">Livre</p>
          {overflow.map((b) => (
            <div
              key={b.id}
              className="card flex items-center gap-4"
              style={{ borderColor: "var(--accent-dim)" }}
            >
              <span className="text-3xl">{b.emoji}</span>
              <div className="flex-1">
                <p className="font-bold">{b.name}</p>
                <p className="text-xs text-[color:var(--text-muted)]">
                  Tudo que sobra depois das metas
                </p>
              </div>
              <p className="num-lg" style={{ color: "var(--accent)" }}>
                {fmtAUD(balances[b.id] ?? 0)}
              </p>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}

function sumBalances(balances: Record<number, number>): number {
  return Object.values(balances).reduce((a, b) => a + b, 0);
}

function BucketCard({
  bucket,
  balance,
  lastNet,
}: {
  bucket: ReturnType<typeof activeBuckets>[number];
  balance: number;
  lastNet: number;
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
  const share =
    lastNet > 0 && progress.avgWeeklyCents > 0
      ? Math.round((progress.avgWeeklyCents / lastNet) * 100)
      : 0;

  return (
    <Link href={`/caixinhas/${bucket.id}`} className="card flex flex-col gap-3">
      <div className="flex items-start justify-between">
        <span className="text-2xl">{bucket.emoji ?? "💰"}</span>
        {progress.onTrack !== null && (
          <span
            className={`pill ${progress.onTrack ? "pill-accent" : "pill-warn"}`}
            style={{ fontSize: 10, padding: "3px 8px" }}
          >
            {progress.onTrack ? pt.buckets.onTrack : pt.buckets.behind}
          </span>
        )}
      </div>
      <div>
        <p className="font-bold text-sm">{bucket.name}</p>
        <p className="num-lg mt-1">{fmtAUD(balance)}</p>
        {bucket.targetCents && (
          <p className="text-[11px] text-[color:var(--text-muted)] mt-0.5">
            de {fmtAUD(bucket.targetCents)}
          </p>
        )}
      </div>
      <div className="h-1.5 rounded-full bg-[color:var(--surface-3)] overflow-hidden">
        <div
          className="h-full"
          style={{
            width: `${Math.round((progress.progress ?? 0) * 100)}%`,
            background: "var(--accent)",
          }}
        />
      </div>
      <div className="flex items-baseline justify-between text-[11px]">
        <span className="text-[color:var(--text-muted)]">
          {progress.avgWeeklyCents > 0
            ? `${fmtAUD(progress.avgWeeklyCents)}/sem`
            : "—"}
        </span>
        {share > 0 && (
          <span style={{ color: "var(--accent)" }}>
            {share}% {pt.buckets.percentOfSalary}
          </span>
        )}
      </div>
    </Link>
  );
}

function SinkingRow({
  bucket,
  balance,
}: {
  bucket: ReturnType<typeof activeBuckets>[number];
  balance: number;
}) {
  return (
    <li className="card card-tight flex items-center gap-3">
      <span className="text-xl">{bucket.emoji ?? "📦"}</span>
      <div className="flex-1">
        <p className="text-sm font-medium">{bucket.name}</p>
        <p className="text-[11px] text-[color:var(--text-muted)]">Reserva</p>
      </div>
      <p
        className="num font-semibold text-sm"
        style={{
          color: balance < 0 ? "var(--danger)" : "var(--text)",
        }}
      >
        {fmtAUD(balance)}
      </p>
    </li>
  );
}

export const dynamic = "force-dynamic";
