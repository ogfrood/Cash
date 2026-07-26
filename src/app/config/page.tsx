export default function ConfigPage() {
  return (
    <div className="flex flex-col gap-5">
      <header className="pt-2">
        <h1 className="text-3xl font-extrabold tracking-tight">Ajustes</h1>
      </header>
      <section className="card">
        <p className="eyebrow mb-2">Estatuto fiscal</p>
        <p className="text-lg font-semibold">
          Working Holiday Maker (417/462)
        </p>
        <p className="text-xs text-[color:var(--text-muted)] mt-1">
          15% até $45.000 · FY 2026-27
        </p>
      </section>
      <section className="card">
        <p className="eyebrow mb-2">Email — sincronização</p>
        <p className="text-sm">Ainda por configurar (IMAP)</p>
      </section>
      <section className="card">
        <p className="eyebrow mb-2">Empregadores</p>
        <p className="text-sm">SOHO Rivermakers</p>
      </section>
    </div>
  );
}
