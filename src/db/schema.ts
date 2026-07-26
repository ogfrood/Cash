/**
 * Schema conventions
 * ------------------
 *  - Money  : integer cents, `...Cents`. Never a float.
 *  - Rates  : basis points, `...Bp` (10000 = 100%).
 *  - Dates  : `YYYY-MM-DD` text for calendar dates (Brisbane-local).
 *  - Instants: integer unix-ms for real points in time.
 *
 * The single most important rule here: **bucket balances are never stored**.
 * A balance is always SUM(ledger_entries.amount_cents) for that bucket. That
 * makes every number reproducible and makes it impossible for a balance to
 * drift out of agreement with its own history.
 */

import { sql } from "drizzle-orm";
import {
  index,
  integer,
  real,
  sqliteTable,
  text,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";

const pk = () => integer("id").primaryKey({ autoIncrement: true });
const createdAt = () =>
  integer("created_at", { mode: "timestamp_ms" })
    .notNull()
    .default(sql`(unixepoch() * 1000)`);

/* ------------------------------------------------------------------ *
 * Employers and pay rates
 * ------------------------------------------------------------------ */

export const employers = sqliteTable("employers", {
  id: pk(),
  name: text("name").notNull(),
  isActive: integer("is_active", { mode: "boolean" }).notNull().default(true),
  notes: text("notes"),
  createdAt: createdAt(),
});

/**
 * Rosters arrive from "SOHO Rivermakers Pty Ltd" while payslips come from
 * "Round Circle Services Pty Ltd" and "GGHRCSR QLD Pty Ltd". Aliases are how
 * we tie those to one employer.
 */
export const employerAliases = sqliteTable(
  "employer_aliases",
  {
    id: pk(),
    employerId: integer("employer_id")
      .notNull()
      .references(() => employers.id, { onDelete: "cascade" }),
    matchType: text("match_type", {
      enum: ["roster_sender", "payslip_entity", "venue"],
    }).notNull(),
    value: text("value").notNull(),
  },
  (t) => [uniqueIndex("employer_aliases_value_idx").on(t.matchType, t.value)],
);

/**
 * A set of rates effective over a date range. A pay rise creates a NEW row
 * rather than editing the old one, so historical weeks keep recomputing to
 * the numbers that were actually true at the time.
 */
export const payRateSets = sqliteTable("pay_rate_sets", {
  id: pk(),
  employerId: integer("employer_id")
    .notNull()
    .references(() => employers.id, { onDelete: "cascade" }),
  label: text("label").notNull(),
  employmentType: text("employment_type", {
    enum: ["casual", "part_time", "full_time"],
  })
    .notNull()
    .default("casual"),
  baseRateCents: integer("base_rate_cents").notNull(),
  effectiveFrom: text("effective_from").notNull(),
  effectiveTo: text("effective_to"),
  createdAt: createdAt(),
});

/**
 * One penalty band. `daysMask` is a bitmask with bit 0 = Monday .. bit 6 =
 * Sunday. `startMinute`/`endMinute` are minutes from local midnight.
 *
 * `rateCentsOverride` is the preferred field: Joshua types the literal $/hr
 * printed on his payslip for each band. That sidesteps every question about
 * how the award compounds casual loading, and makes forecast and actual
 * reconcile exactly. `multiplierBp` stays as a convenience for initial setup.
 */
export const payRateRules = sqliteTable("pay_rate_rules", {
  id: pk(),
  rateSetId: integer("rate_set_id")
    .notNull()
    .references(() => payRateSets.id, { onDelete: "cascade" }),
  label: text("label").notNull(),
  priority: integer("priority").notNull().default(0),
  daysMask: integer("days_mask").notNull().default(0b1111111),
  startMinute: integer("start_minute").notNull().default(0),
  endMinute: integer("end_minute").notNull().default(1440),
  appliesOnPublicHoliday: text("applies_on_public_holiday", {
    enum: ["only", "never", "ignore"],
  })
    .notNull()
    .default("ignore"),
  multiplierBp: integer("multiplier_bp"),
  rateCentsOverride: integer("rate_cents_override"),
  /** Overtime does not attract super; ordinary time earnings do. */
  excludeFromOte: integer("exclude_from_ote", { mode: "boolean" })
    .notNull()
    .default(false),
});

export const publicHolidays = sqliteTable(
  "public_holidays",
  {
    id: pk(),
    date: text("date").notNull(),
    name: text("name").notNull(),
    region: text("region").notNull().default("QLD"),
    isCustom: integer("is_custom", { mode: "boolean" }).notNull().default(false),
  },
  (t) => [uniqueIndex("public_holidays_date_idx").on(t.date, t.region)],
);

/* ------------------------------------------------------------------ *
 * Email ingest
 * ------------------------------------------------------------------ */

export const emailIngest = sqliteTable(
  "email_ingest",
  {
    id: pk(),
    /** RFC822 Message-ID. The primary defence against reprocessing. */
    messageId: text("message_id").notNull(),
    source: text("source", { enum: ["tanda", "xero"] }).notNull(),
    kind: text("kind", { enum: ["roster", "payslip"] }).notNull(),
    fromAddr: text("from_addr").notNull(),
    subject: text("subject").notNull(),
    receivedAt: integer("received_at", { mode: "timestamp_ms" }).notNull(),
    /** Hash of normalised content: catches resends with a fresh Message-ID. */
    contentHash: text("content_hash").notNull(),
    status: text("status", {
      enum: ["parsed", "duplicate", "quarantined", "ignored"],
    }).notNull(),
    error: text("error"),
    rawPath: text("raw_path"),
    attachmentPath: text("attachment_path"),
    processedAt: integer("processed_at", { mode: "timestamp_ms" }),
    createdAt: createdAt(),
  },
  (t) => [
    uniqueIndex("email_ingest_message_id_idx").on(t.messageId),
    index("email_ingest_hash_idx").on(t.contentHash),
    index("email_ingest_status_idx").on(t.status),
  ],
);

/**
 * One roster email that was actually applied. Tanda re-sends a revised roster
 * for the same week repeatedly (21.5h -> 29.5h -> 33.5h), so exactly one
 * import per week is `isActive`; the rest are history.
 */
export const rosterImports = sqliteTable(
  "roster_imports",
  {
    id: pk(),
    emailIngestId: integer("email_ingest_id")
      .notNull()
      .references(() => emailIngest.id, { onDelete: "cascade" }),
    employerId: integer("employer_id")
      .notNull()
      .references(() => employers.id),
    weekStart: text("week_start").notNull(),
    /** From the footer: "Roster as of 2:59 AM, 24 Jul". Orders revisions. */
    rosterAsOf: integer("roster_as_of", { mode: "timestamp_ms" }).notNull(),
    /** From the subject line: "33.5 hours over 5 Shifts". A free checksum. */
    declaredHours: real("declared_hours"),
    declaredShiftCount: integer("declared_shift_count"),
    /** Hash of the normalised shift tuples; identical hash = exact resend. */
    shiftSetHash: text("shift_set_hash").notNull(),
    isActive: integer("is_active", { mode: "boolean" }).notNull().default(false),
    supersededByImportId: integer("superseded_by_import_id"),
    needsReview: integer("needs_review", { mode: "boolean" })
      .notNull()
      .default(false),
    reviewNote: text("review_note"),
    createdAt: createdAt(),
  },
  (t) => [index("roster_imports_week_idx").on(t.employerId, t.weekStart)],
);

export const shifts = sqliteTable(
  "shifts",
  {
    id: pk(),
    employerId: integer("employer_id")
      .notNull()
      .references(() => employers.id),
    rosterImportId: integer("roster_import_id").references(
      () => rosterImports.id,
      { onDelete: "cascade" },
    ),
    startUtc: integer("start_utc", { mode: "timestamp_ms" }).notNull(),
    endUtc: integer("end_utc", { mode: "timestamp_ms" }).notNull(),
    weekStart: text("week_start").notNull(),
    unpaidBreakMinutes: integer("unpaid_break_minutes").notNull().default(0),
    /** Authoritative paid time. Tanda's "7.0 hrs" pill is already net of break. */
    paidMinutes: integer("paid_minutes").notNull(),
    breakInferred: integer("break_inferred", { mode: "boolean" })
      .notNull()
      .default(false),
    role: text("role"),
    section: text("section"),
    detail: text("detail"),
    externalUid: text("external_uid"),
    source: text("source", { enum: ["ics", "html", "manual"] }).notNull(),
    status: text("status", { enum: ["active", "superseded", "cancelled"] })
      .notNull()
      .default("active"),
    /** A hand-edited shift is never clobbered by a later roster import. */
    isLocked: integer("is_locked", { mode: "boolean" }).notNull().default(false),
    createdAt: createdAt(),
  },
  (t) => [
    index("shifts_week_idx").on(t.weekStart, t.status),
    index("shifts_employer_start_idx").on(t.employerId, t.startUtc),
  ],
);

/* ------------------------------------------------------------------ *
 * Pay periods, payslips, tax
 * ------------------------------------------------------------------ */

export const payPeriods = sqliteTable(
  "pay_periods",
  {
    id: pk(),
    employerId: integer("employer_id").references(() => employers.id),
    weekStart: text("week_start").notNull(),
    weekEnd: text("week_end").notNull(),
    payDate: text("pay_date"),

    forecastGrossCents: integer("forecast_gross_cents"),
    forecastTaxCents: integer("forecast_tax_cents"),
    forecastNetCents: integer("forecast_net_cents"),
    forecastSuperCents: integer("forecast_super_cents"),
    forecastMinutes: integer("forecast_minutes"),
    forecastComputedAt: integer("forecast_computed_at", {
      mode: "timestamp_ms",
    }),

    actualGrossCents: integer("actual_gross_cents"),
    actualTaxCents: integer("actual_tax_cents"),
    actualNetCents: integer("actual_net_cents"),
    actualSuperCents: integer("actual_super_cents"),

    /** Manual override, used before shift forecasting exists (Phase 1). */
    manualNetCents: integer("manual_net_cents"),

    status: text("status", { enum: ["forecast", "reconciled", "disputed"] })
      .notNull()
      .default("forecast"),
    createdAt: createdAt(),
  },
  (t) => [uniqueIndex("pay_periods_week_idx").on(t.employerId, t.weekEnd)],
);

export const payslips = sqliteTable("payslips", {
  id: pk(),
  payPeriodId: integer("pay_period_id").references(() => payPeriods.id),
  employerId: integer("employer_id")
    .notNull()
    .references(() => employers.id),
  emailIngestId: integer("email_ingest_id").references(() => emailIngest.id),
  periodStart: text("period_start").notNull(),
  periodEnd: text("period_end").notNull(),
  payDate: text("pay_date"),
  grossCents: integer("gross_cents").notNull(),
  paygCents: integer("payg_cents").notNull(),
  netCents: integer("net_cents").notNull(),
  superCents: integer("super_cents"),
  ytdGrossCents: integer("ytd_gross_cents"),
  ytdTaxCents: integer("ytd_tax_cents"),
  pdfPath: text("pdf_path"),
  rawText: text("raw_text"),
  /** 0..100: fraction of the required fields the parser actually found. */
  parseConfidence: integer("parse_confidence").notNull().default(100),
  needsReview: integer("needs_review", { mode: "boolean" })
    .notNull()
    .default(false),
  createdAt: createdAt(),
});

export const payslipLines = sqliteTable("payslip_lines", {
  id: pk(),
  payslipId: integer("payslip_id")
    .notNull()
    .references(() => payslips.id, { onDelete: "cascade" }),
  lineType: text("line_type", {
    enum: ["earning", "deduction", "tax", "super", "other"],
  }).notNull(),
  description: text("description").notNull(),
  hours: real("hours"),
  rateCents: integer("rate_cents"),
  amountCents: integer("amount_cents").notNull(),
});

export const taxSettings = sqliteTable("tax_settings", {
  id: pk(),
  fyLabel: text("fy_label").notNull(),
  status: text("status", { enum: ["WHM", "RESIDENT", "FOREIGN"] })
    .notNull()
    .default("WHM"),
  superGuaranteeBp: integer("super_guarantee_bp").notNull().default(1200),
  withholdingMethod: text("withholding_method", {
    enum: ["cumulative", "annualised"],
  })
    .notNull()
    .default("annualised"),
});

/* ------------------------------------------------------------------ *
 * Ad-hoc income (side gigs, ABN work, informal cash, tips)
 * ------------------------------------------------------------------ */

/**
 * A one-off income event that is NOT part of a Tanda/Xero pay cycle:
 *  - ABN work invoiced separately;
 *  - informal cash for a shift covered outside payroll;
 *  - a tip pool payout;
 *  - anything else that lands in the bank but did not come from a shift.
 *
 * Kept distinct from `payPeriods` because it has no roster, no PAYG
 * withholding by an employer, and Joshua has to set aside his own tax on ABN
 * income — the app should surface that separately, not merge it into net pay.
 */
export const adhocIncome = sqliteTable(
  "adhoc_income",
  {
    id: pk(),
    date: text("date").notNull(),
    amountCents: integer("amount_cents").notNull(),
    kind: text("kind", {
      enum: ["abn", "informal", "tip", "bonus", "other"],
    }).notNull(),
    source: text("source"),
    /** Tax the user chose to set aside for this entry (usually 15–30%). */
    taxSetAsideCents: integer("tax_set_aside_cents").notNull().default(0),
    weekStart: text("week_start").notNull(),
    notes: text("notes"),
    /** Allocation run that consumed this entry, if any. */
    allocatedRunId: integer("allocated_run_id"),
    createdAt: createdAt(),
  },
  (t) => [
    index("adhoc_income_week_idx").on(t.weekStart),
    index("adhoc_income_date_idx").on(t.date),
  ],
);

/* ------------------------------------------------------------------ *
 * Fixed costs
 * ------------------------------------------------------------------ */

export const fixedExpenses = sqliteTable("fixed_expenses", {
  id: pk(),
  name: text("name").notNull(),
  category: text("category"),
  amountCents: integer("amount_cents").notNull(),
  cadence: text("cadence", {
    enum: ["weekly", "fortnightly", "monthly", "quarterly", "yearly"],
  }).notNull(),
  /** First (or next) occurrence; occurrences are generated forward from here. */
  anchorDate: text("anchor_date").notNull(),
  /** The sinking-fund bucket this expense accrues into. */
  sinkingBucketId: integer("sinking_bucket_id"),
  isActive: integer("is_active", { mode: "boolean" }).notNull().default(true),
  notes: text("notes"),
  createdAt: createdAt(),
});

export const expenseOccurrences = sqliteTable(
  "expense_occurrences",
  {
    id: pk(),
    fixedExpenseId: integer("fixed_expense_id")
      .notNull()
      .references(() => fixedExpenses.id, { onDelete: "cascade" }),
    dueDate: text("due_date").notNull(),
    amountCents: integer("amount_cents").notNull(),
    status: text("status", { enum: ["scheduled", "paid", "skipped"] })
      .notNull()
      .default("scheduled"),
    paidDate: text("paid_date"),
    paidAmountCents: integer("paid_amount_cents"),
  },
  (t) => [
    uniqueIndex("expense_occurrences_due_idx").on(t.fixedExpenseId, t.dueDate),
    index("expense_occurrences_status_idx").on(t.status, t.dueDate),
  ],
);

/* ------------------------------------------------------------------ *
 * Buckets ("caixinhas") and the ledger
 * ------------------------------------------------------------------ */

export const buckets = sqliteTable("buckets", {
  id: pk(),
  name: text("name").notNull(),
  emoji: text("emoji"),
  colorHex: text("color_hex"),
  kind: text("kind", { enum: ["goal", "sinking", "spending", "overflow"] })
    .notNull()
    .default("goal"),
  targetCents: integer("target_cents"),
  targetDate: text("target_date"),
  ruleType: text("rule_type", {
    enum: ["percent", "fixed", "fill_to_target", "fill_paced", "none"],
  })
    .notNull()
    .default("none"),
  /** Basis points for `percent`, cents for `fixed`. Ignored otherwise. */
  ruleValue: integer("rule_value").notNull().default(0),
  weeklyCapCents: integer("weekly_cap_cents"),
  /** Lower runs first in the waterfall. */
  priority: integer("priority").notNull().default(100),
  sortIndex: integer("sort_index").notNull().default(0),
  isArchived: integer("is_archived", { mode: "boolean" })
    .notNull()
    .default(false),
  createdAt: createdAt(),
});

export const allocationRuns = sqliteTable(
  "allocation_runs",
  {
    id: pk(),
    payPeriodId: integer("pay_period_id").references(() => payPeriods.id),
    weekStart: text("week_start").notNull(),
    basis: text("basis", { enum: ["forecast", "actual", "manual"] }).notNull(),
    incomeCents: integer("income_cents").notNull(),
    fixedCostCents: integer("fixed_cost_cents").notNull(),
    allocatableCents: integer("allocatable_cents").notNull(),
    status: text("status", { enum: ["committed", "reversed"] })
      .notNull()
      .default("committed"),
    /** Set on the inverse run written when an earlier run is reversed. */
    reversesRunId: integer("reverses_run_id"),
    createdAt: createdAt(),
    reversedAt: integer("reversed_at", { mode: "timestamp_ms" }),
  },
  (t) => [index("allocation_runs_week_idx").on(t.weekStart, t.status)],
);

/**
 * The append-only source of truth for every bucket balance.
 * `amountCents` is signed: positive puts money in, negative takes it out.
 */
export const ledgerEntries = sqliteTable(
  "ledger_entries",
  {
    id: pk(),
    bucketId: integer("bucket_id")
      .notNull()
      .references(() => buckets.id, { onDelete: "cascade" }),
    allocationRunId: integer("allocation_run_id").references(
      () => allocationRuns.id,
      { onDelete: "cascade" },
    ),
    expenseOccurrenceId: integer("expense_occurrence_id").references(
      () => expenseOccurrences.id,
      { onDelete: "set null" },
    ),
    date: text("date").notNull(),
    amountCents: integer("amount_cents").notNull(),
    kind: text("kind", {
      enum: [
        "allocation",
        "bill_paid",
        "adjustment",
        "transfer_in",
        "transfer_out",
      ],
    }).notNull(),
    note: text("note"),
    createdAt: createdAt(),
  },
  (t) => [index("ledger_entries_bucket_idx").on(t.bucketId, t.date)],
);

/* ------------------------------------------------------------------ *
 * Debts (pay-down goals, the mirror of savings goals)
 * ------------------------------------------------------------------ */

/**
 * Loans, credit-card balances, "I owe a mate $200". Every debt has a
 * principal, a running balance derived from principal minus payments, and an
 * optional daily-target amount so the app can plot a straight-line payoff.
 *
 * Interest is deliberately NOT modelled yet — a real APR needs its own
 * amortisation logic that adds a compounded interest entry every period, and
 * getting that right is worth a whole feature of its own. For now the user
 * enters their current balance directly and logs payments against it.
 */
export const debts = sqliteTable("debts", {
  id: pk(),
  name: text("name").notNull(),
  emoji: text("emoji"),
  kind: text("kind", {
    enum: ["credit_card", "loan", "personal", "bnpl", "other"],
  })
    .notNull()
    .default("personal"),
  /** Original amount owed. Never changes. */
  principalCents: integer("principal_cents").notNull(),
  /** Best-effort snapshot of what is owed today. Payments do NOT auto-update
   * this — the source of truth is `principal − Σ payments`, computed by
   * queries; this column is only a manual override when the user reconciles
   * with a statement that includes interest or fees. */
  balanceOverrideCents: integer("balance_override_cents"),
  /** APR in basis points; informational only for now. */
  aprBp: integer("apr_bp"),
  /** Minimum required each month (credit-card style). Informational. */
  minMonthlyCents: integer("min_monthly_cents"),
  /** How much the user wants to put aside every day toward this debt. */
  dailyTargetCents: integer("daily_target_cents").notNull().default(0),
  /** Optional goal date to be debt-free. */
  targetDate: text("target_date"),
  priority: integer("priority").notNull().default(100),
  sortIndex: integer("sort_index").notNull().default(0),
  isActive: integer("is_active", { mode: "boolean" }).notNull().default(true),
  notes: text("notes"),
  createdAt: createdAt(),
});

/**
 * Every payment against a debt. Append-only, so the debt's history is
 * reproducible — same principle as `ledgerEntries` for buckets.
 */
export const debtPayments = sqliteTable(
  "debt_payments",
  {
    id: pk(),
    debtId: integer("debt_id")
      .notNull()
      .references(() => debts.id, { onDelete: "cascade" }),
    date: text("date").notNull(),
    amountCents: integer("amount_cents").notNull(),
    note: text("note"),
    createdAt: createdAt(),
  },
  (t) => [index("debt_payments_debt_idx").on(t.debtId, t.date)],
);

/* ------------------------------------------------------------------ *
 * App settings (single row)
 * ------------------------------------------------------------------ */

export const appSettings = sqliteTable("app_settings", {
  id: pk(),
  lastSyncAt: integer("last_sync_at", { mode: "timestamp_ms" }),
  defaultBreakMinutes: integer("default_break_minutes").notNull().default(30),
  defaultBreakThresholdMinutes: integer("default_break_threshold_minutes")
    .notNull()
    .default(300),
});

export type AdhocIncome = typeof adhocIncome.$inferSelect;
export type NewAdhocIncome = typeof adhocIncome.$inferInsert;
export type Debt = typeof debts.$inferSelect;
export type NewDebt = typeof debts.$inferInsert;
export type DebtPayment = typeof debtPayments.$inferSelect;
export type Bucket = typeof buckets.$inferSelect;
export type NewBucket = typeof buckets.$inferInsert;
export type LedgerEntry = typeof ledgerEntries.$inferSelect;
export type FixedExpense = typeof fixedExpenses.$inferSelect;
export type Shift = typeof shifts.$inferSelect;
export type PayPeriod = typeof payPeriods.$inferSelect;
export type Payslip = typeof payslips.$inferSelect;
export type PayRateRule = typeof payRateRules.$inferSelect;
export type PayRateSet = typeof payRateSets.$inferSelect;
