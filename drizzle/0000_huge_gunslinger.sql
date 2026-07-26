CREATE TABLE `adhoc_income` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`date` text NOT NULL,
	`amount_cents` integer NOT NULL,
	`kind` text NOT NULL,
	`source` text,
	`tax_set_aside_cents` integer DEFAULT 0 NOT NULL,
	`week_start` text NOT NULL,
	`notes` text,
	`allocated_run_id` integer,
	`created_at` integer DEFAULT (unixepoch() * 1000) NOT NULL
);
--> statement-breakpoint
CREATE INDEX `adhoc_income_week_idx` ON `adhoc_income` (`week_start`);--> statement-breakpoint
CREATE INDEX `adhoc_income_date_idx` ON `adhoc_income` (`date`);--> statement-breakpoint
CREATE TABLE `allocation_runs` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`pay_period_id` integer,
	`week_start` text NOT NULL,
	`basis` text NOT NULL,
	`income_cents` integer NOT NULL,
	`fixed_cost_cents` integer NOT NULL,
	`allocatable_cents` integer NOT NULL,
	`status` text DEFAULT 'committed' NOT NULL,
	`reverses_run_id` integer,
	`created_at` integer DEFAULT (unixepoch() * 1000) NOT NULL,
	`reversed_at` integer,
	FOREIGN KEY (`pay_period_id`) REFERENCES `pay_periods`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `allocation_runs_week_idx` ON `allocation_runs` (`week_start`,`status`);--> statement-breakpoint
CREATE TABLE `app_settings` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`last_sync_at` integer,
	`default_break_minutes` integer DEFAULT 30 NOT NULL,
	`default_break_threshold_minutes` integer DEFAULT 300 NOT NULL
);
--> statement-breakpoint
CREATE TABLE `buckets` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`name` text NOT NULL,
	`emoji` text,
	`color_hex` text,
	`kind` text DEFAULT 'goal' NOT NULL,
	`target_cents` integer,
	`target_date` text,
	`rule_type` text DEFAULT 'none' NOT NULL,
	`rule_value` integer DEFAULT 0 NOT NULL,
	`weekly_cap_cents` integer,
	`priority` integer DEFAULT 100 NOT NULL,
	`sort_index` integer DEFAULT 0 NOT NULL,
	`is_archived` integer DEFAULT false NOT NULL,
	`created_at` integer DEFAULT (unixepoch() * 1000) NOT NULL
);
--> statement-breakpoint
CREATE TABLE `debt_payments` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`debt_id` integer NOT NULL,
	`date` text NOT NULL,
	`amount_cents` integer NOT NULL,
	`note` text,
	`created_at` integer DEFAULT (unixepoch() * 1000) NOT NULL,
	FOREIGN KEY (`debt_id`) REFERENCES `debts`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `debt_payments_debt_idx` ON `debt_payments` (`debt_id`,`date`);--> statement-breakpoint
CREATE TABLE `debts` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`name` text NOT NULL,
	`emoji` text,
	`kind` text DEFAULT 'personal' NOT NULL,
	`principal_cents` integer NOT NULL,
	`balance_override_cents` integer,
	`apr_bp` integer,
	`min_monthly_cents` integer,
	`daily_target_cents` integer DEFAULT 0 NOT NULL,
	`target_date` text,
	`priority` integer DEFAULT 100 NOT NULL,
	`sort_index` integer DEFAULT 0 NOT NULL,
	`is_active` integer DEFAULT true NOT NULL,
	`notes` text,
	`created_at` integer DEFAULT (unixepoch() * 1000) NOT NULL
);
--> statement-breakpoint
CREATE TABLE `email_ingest` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`message_id` text NOT NULL,
	`source` text NOT NULL,
	`kind` text NOT NULL,
	`from_addr` text NOT NULL,
	`subject` text NOT NULL,
	`received_at` integer NOT NULL,
	`content_hash` text NOT NULL,
	`status` text NOT NULL,
	`error` text,
	`raw_path` text,
	`attachment_path` text,
	`processed_at` integer,
	`created_at` integer DEFAULT (unixepoch() * 1000) NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `email_ingest_message_id_idx` ON `email_ingest` (`message_id`);--> statement-breakpoint
CREATE INDEX `email_ingest_hash_idx` ON `email_ingest` (`content_hash`);--> statement-breakpoint
CREATE INDEX `email_ingest_status_idx` ON `email_ingest` (`status`);--> statement-breakpoint
CREATE TABLE `employer_aliases` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`employer_id` integer NOT NULL,
	`match_type` text NOT NULL,
	`value` text NOT NULL,
	FOREIGN KEY (`employer_id`) REFERENCES `employers`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `employer_aliases_value_idx` ON `employer_aliases` (`match_type`,`value`);--> statement-breakpoint
CREATE TABLE `employers` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`name` text NOT NULL,
	`is_active` integer DEFAULT true NOT NULL,
	`notes` text,
	`created_at` integer DEFAULT (unixepoch() * 1000) NOT NULL
);
--> statement-breakpoint
CREATE TABLE `expense_occurrences` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`fixed_expense_id` integer NOT NULL,
	`due_date` text NOT NULL,
	`amount_cents` integer NOT NULL,
	`status` text DEFAULT 'scheduled' NOT NULL,
	`paid_date` text,
	`paid_amount_cents` integer,
	FOREIGN KEY (`fixed_expense_id`) REFERENCES `fixed_expenses`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `expense_occurrences_due_idx` ON `expense_occurrences` (`fixed_expense_id`,`due_date`);--> statement-breakpoint
CREATE INDEX `expense_occurrences_status_idx` ON `expense_occurrences` (`status`,`due_date`);--> statement-breakpoint
CREATE TABLE `fixed_expenses` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`name` text NOT NULL,
	`category` text,
	`amount_cents` integer NOT NULL,
	`cadence` text NOT NULL,
	`anchor_date` text NOT NULL,
	`sinking_bucket_id` integer,
	`is_active` integer DEFAULT true NOT NULL,
	`notes` text,
	`created_at` integer DEFAULT (unixepoch() * 1000) NOT NULL
);
--> statement-breakpoint
CREATE TABLE `ledger_entries` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`bucket_id` integer NOT NULL,
	`allocation_run_id` integer,
	`expense_occurrence_id` integer,
	`date` text NOT NULL,
	`amount_cents` integer NOT NULL,
	`kind` text NOT NULL,
	`note` text,
	`created_at` integer DEFAULT (unixepoch() * 1000) NOT NULL,
	FOREIGN KEY (`bucket_id`) REFERENCES `buckets`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`allocation_run_id`) REFERENCES `allocation_runs`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`expense_occurrence_id`) REFERENCES `expense_occurrences`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE INDEX `ledger_entries_bucket_idx` ON `ledger_entries` (`bucket_id`,`date`);--> statement-breakpoint
CREATE TABLE `pay_periods` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`employer_id` integer,
	`week_start` text NOT NULL,
	`week_end` text NOT NULL,
	`pay_date` text,
	`forecast_gross_cents` integer,
	`forecast_tax_cents` integer,
	`forecast_net_cents` integer,
	`forecast_super_cents` integer,
	`forecast_minutes` integer,
	`forecast_computed_at` integer,
	`actual_gross_cents` integer,
	`actual_tax_cents` integer,
	`actual_net_cents` integer,
	`actual_super_cents` integer,
	`manual_net_cents` integer,
	`status` text DEFAULT 'forecast' NOT NULL,
	`created_at` integer DEFAULT (unixepoch() * 1000) NOT NULL,
	FOREIGN KEY (`employer_id`) REFERENCES `employers`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `pay_periods_week_idx` ON `pay_periods` (`employer_id`,`week_end`);--> statement-breakpoint
CREATE TABLE `pay_rate_rules` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`rate_set_id` integer NOT NULL,
	`label` text NOT NULL,
	`priority` integer DEFAULT 0 NOT NULL,
	`days_mask` integer DEFAULT 127 NOT NULL,
	`start_minute` integer DEFAULT 0 NOT NULL,
	`end_minute` integer DEFAULT 1440 NOT NULL,
	`applies_on_public_holiday` text DEFAULT 'ignore' NOT NULL,
	`multiplier_bp` integer,
	`rate_cents_override` integer,
	`exclude_from_ote` integer DEFAULT false NOT NULL,
	FOREIGN KEY (`rate_set_id`) REFERENCES `pay_rate_sets`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `pay_rate_sets` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`employer_id` integer NOT NULL,
	`label` text NOT NULL,
	`employment_type` text DEFAULT 'casual' NOT NULL,
	`base_rate_cents` integer NOT NULL,
	`effective_from` text NOT NULL,
	`effective_to` text,
	`created_at` integer DEFAULT (unixepoch() * 1000) NOT NULL,
	FOREIGN KEY (`employer_id`) REFERENCES `employers`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `payslip_lines` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`payslip_id` integer NOT NULL,
	`line_type` text NOT NULL,
	`description` text NOT NULL,
	`hours` real,
	`rate_cents` integer,
	`amount_cents` integer NOT NULL,
	FOREIGN KEY (`payslip_id`) REFERENCES `payslips`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `payslips` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`pay_period_id` integer,
	`employer_id` integer NOT NULL,
	`email_ingest_id` integer,
	`period_start` text NOT NULL,
	`period_end` text NOT NULL,
	`pay_date` text,
	`gross_cents` integer NOT NULL,
	`payg_cents` integer NOT NULL,
	`net_cents` integer NOT NULL,
	`super_cents` integer,
	`ytd_gross_cents` integer,
	`ytd_tax_cents` integer,
	`pdf_path` text,
	`raw_text` text,
	`parse_confidence` integer DEFAULT 100 NOT NULL,
	`needs_review` integer DEFAULT false NOT NULL,
	`created_at` integer DEFAULT (unixepoch() * 1000) NOT NULL,
	FOREIGN KEY (`pay_period_id`) REFERENCES `pay_periods`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`employer_id`) REFERENCES `employers`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`email_ingest_id`) REFERENCES `email_ingest`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `public_holidays` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`date` text NOT NULL,
	`name` text NOT NULL,
	`region` text DEFAULT 'QLD' NOT NULL,
	`is_custom` integer DEFAULT false NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `public_holidays_date_idx` ON `public_holidays` (`date`,`region`);--> statement-breakpoint
CREATE TABLE `roster_imports` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`email_ingest_id` integer NOT NULL,
	`employer_id` integer NOT NULL,
	`week_start` text NOT NULL,
	`roster_as_of` integer NOT NULL,
	`declared_hours` real,
	`declared_shift_count` integer,
	`shift_set_hash` text NOT NULL,
	`is_active` integer DEFAULT false NOT NULL,
	`superseded_by_import_id` integer,
	`needs_review` integer DEFAULT false NOT NULL,
	`review_note` text,
	`created_at` integer DEFAULT (unixepoch() * 1000) NOT NULL,
	FOREIGN KEY (`email_ingest_id`) REFERENCES `email_ingest`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`employer_id`) REFERENCES `employers`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `roster_imports_week_idx` ON `roster_imports` (`employer_id`,`week_start`);--> statement-breakpoint
CREATE TABLE `shifts` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`employer_id` integer NOT NULL,
	`roster_import_id` integer,
	`start_utc` integer NOT NULL,
	`end_utc` integer NOT NULL,
	`week_start` text NOT NULL,
	`unpaid_break_minutes` integer DEFAULT 0 NOT NULL,
	`paid_minutes` integer NOT NULL,
	`break_inferred` integer DEFAULT false NOT NULL,
	`role` text,
	`section` text,
	`detail` text,
	`external_uid` text,
	`source` text NOT NULL,
	`status` text DEFAULT 'active' NOT NULL,
	`is_locked` integer DEFAULT false NOT NULL,
	`created_at` integer DEFAULT (unixepoch() * 1000) NOT NULL,
	FOREIGN KEY (`employer_id`) REFERENCES `employers`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`roster_import_id`) REFERENCES `roster_imports`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `shifts_week_idx` ON `shifts` (`week_start`,`status`);--> statement-breakpoint
CREATE INDEX `shifts_employer_start_idx` ON `shifts` (`employer_id`,`start_utc`);--> statement-breakpoint
CREATE TABLE `tax_settings` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`fy_label` text NOT NULL,
	`status` text DEFAULT 'WHM' NOT NULL,
	`super_guarantee_bp` integer DEFAULT 1200 NOT NULL,
	`withholding_method` text DEFAULT 'annualised' NOT NULL
);
