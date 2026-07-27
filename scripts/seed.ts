/**
 * Seed the local DB with the bare minimum for the app to work:
 *  - default tax settings for the current FY,
 *  - one row of app settings,
 *  - a single overflow bucket named "Livre" that the allocation engine
 *    needs to catch the remainder each week.
 *
 * Everything else — employers, caixinhas, contas, dívidas, pay periods —
 * the user creates through the UI. Idempotent: safe to re-run any time
 * (wipes and reinstates the seeded rows, but leaves user-created data).
 *
 * If you want a fully clean slate including your own edits, delete
 * `data/cash.db` first and then run `npm run db:migrate && npm run db:seed`.
 */
import Database from "better-sqlite3";
import { drizzle } from "drizzle-orm/better-sqlite3";
import { eq } from "drizzle-orm";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

import * as schema from "../src/db/schema";

const dbPath = resolve(process.env.DATABASE_PATH ?? "./data/cash.db");
mkdirSync(dirname(dbPath), { recursive: true });
const sqlite = new Database(dbPath);
sqlite.pragma("journal_mode = WAL");
sqlite.pragma("foreign_keys = ON");
const db = drizzle(sqlite, { schema });

console.log(`Semeando ${dbPath} com defaults mínimos.`);

// Ensure at least one row of app settings exists.
const existingSettings = db.select().from(schema.appSettings).all();
if (existingSettings.length === 0) {
  db.insert(schema.appSettings).values({}).run();
}

// Ensure tax settings for the current FY exist. Do not overwrite if the user
// has already customised them.
const existingTax = db
  .select()
  .from(schema.taxSettings)
  .where(eq(schema.taxSettings.fyLabel, "2026-27"))
  .all();
if (existingTax.length === 0) {
  db.insert(schema.taxSettings)
    .values({
      fyLabel: "2026-27",
      status: "WHM",
      superGuaranteeBp: 1200,
      withholdingMethod: "annualised",
    })
    .run();
}

// Ensure exactly one overflow bucket exists. If none, create "Livre".
const existingOverflow = db
  .select()
  .from(schema.buckets)
  .where(eq(schema.buckets.kind, "overflow"))
  .all();
if (existingOverflow.length === 0) {
  db.insert(schema.buckets)
    .values({
      name: "Livre",
      emoji: "💚",
      kind: "overflow",
      ruleType: "none",
      priority: 999,
      sortIndex: 999,
    })
    .run();
}

console.log("Seed concluído.");
sqlite.close();
