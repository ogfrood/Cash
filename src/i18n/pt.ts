/**
 * Every user-facing string in one place. Flat and typed so a missing key is a
 * TypeScript error, not a broken page. Portuguese only for now — this app has
 * a single user.
 */
export const pt = {
  app: {
    name: "Cash",
    greetingMorning: "Bom dia",
    greetingAfternoon: "Boa tarde",
    greetingEvening: "Boa noite",
  },
  nav: {
    dashboard: "Painel",
    buckets: "Caixinhas",
    shifts: "Turnos",
    bills: "Contas",
    settings: "Ajustes",
  },
  cashflow: {
    title: "Esta semana",
    subtitle: "Fluxo do salário",
    in: "Entra",
    out: "Sai",
    left: "Sobra",
    forecast: "Previsto",
    actual: "Real",
  },
  buckets: {
    title: "Caixinhas",
    add: "Nova caixinha",
    goal: "Meta",
    of: "de",
    projected: "Previsão",
    onTrack: "No ritmo",
    behind: "Atrasado",
    weeklyRate: "por semana",
    weeksToGo: "sem.",
    empty: "Sem caixinhas ainda. Cria a primeira.",
    percentOfSalary: "do salário",
    detail: "Detalhes",
    kinds: {
      goal: "Meta",
      sinking: "Reserva",
      spending: "Gasto",
      overflow: "Sobra livre",
    },
  },
  adhoc: {
    title: "Trabalho avulso",
    add: "Nova entrada",
    kind: "Tipo",
    amount: "Valor",
    date: "Data",
    source: "De onde veio",
    taxSetAside: "Reservar para imposto",
    kinds: {
      abn: "ABN / freelance",
      informal: "Informal / dinheiro",
      tip: "Gorjeta",
      bonus: "Bónus",
      other: "Outro",
    },
    hint: "Turnos do Tanda entram sozinhos pelo email. Isto é para o que fica de fora.",
  },
  bills: {
    title: "Contas",
    upcoming: "A vir",
    weeklyReserve: "Reserva/sem.",
    add: "Nova conta",
    dueIn: (days: number) =>
      days === 0 ? "Hoje" : days === 1 ? "Amanhã" : `Em ${days} dias`,
    cadence: {
      weekly: "Semanal",
      fortnightly: "Quinzenal",
      monthly: "Mensal",
      quarterly: "Trimestral",
      yearly: "Anual",
    },
  },
  progression: {
    title: "Progressão salarial",
    subtitle: "Últimas 8 semanas",
    ytdGross: "Bruto no ano",
    ytdTax: "Imposto retido",
    ytdSuper: "Super acumulado",
    towardsCap: "Até $45.000",
  },
  common: {
    save: "Guardar",
    cancel: "Cancelar",
    edit: "Editar",
    delete: "Apagar",
    total: "Total",
    forecast: "Previsto",
    ok: "OK",
  },
};
