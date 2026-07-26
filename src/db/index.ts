import "server-only";

import Database from "better-sqlite3";
import { drizzle } from "drizzle-orm/better-sqlite3";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

import * as schema from "./schema";

const DB_PATH = resolve(process.env.DATABASE_PATH ?? "./data/cash.db");

function createClient() {
  mkdirSync(dirname(DB_PATH), { recursive: true });
  const sqlite = new Database(DB_PATH);
  // WAL keeps reads from blocking on the write of an allocation commit.
  sqlite.pragma("journal_mode = WAL");
  sqlite.pragma("foreign_keys = ON");
  return drizzle(sqlite, { schema });
}

// Next dev hot-reloads modules; without this each reload opens another handle
// to the same file and they eventually contend on the write lock.
const globalForDb = globalThis as unknown as {
  __cashDb?: ReturnType<typeof createClient>;
};

export const db = globalForDb.__cashDb ?? createClient();

if (process.env.NODE_ENV !== "production") {
  globalForDb.__cashDb = db;
}

export { schema };
