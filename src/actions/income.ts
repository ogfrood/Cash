"use server";

import { revalidatePath } from "next/cache";
import { and, eq } from "drizzle-orm";
import { z } from "zod";

import { db, schema } from "@/db";
import { dollarsToCents } from "@/lib/money";
import { addLocalDays, weekEnd, weekStart } from "@/lib/time";

const ManualNetSchema = z.object({
  weekStart: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Data inválida"),
  amount: z.string().min(1, "Valor obrigatório"),
});

/**
 * Set (or override) the net-pay figure for a week manually.
 *
 * Falls through to `manualNetCents` on `payPeriods`; the shift-based forecast
 * (once it exists) will still populate `forecast*Cents` alongside, and the UI
 * prefers `actual` > `forecast` > `manual`. This is the Phase 1 shortcut so
 * Joshua can drive the app before the email ingest is wired up.
 */
export async function setManualNet(formData: FormData) {
  const parsed = ManualNetSchema.parse({
    weekStart: formData.get("weekStart"),
    amount: formData.get("amount"),
  });
  const ws = weekStart(parsed.weekStart);
  const we = weekEnd(ws);
  const cents = dollarsToCents(parsed.amount);

  const existing = db
    .select()
    .from(schema.payPeriods)
    .where(and(eq(schema.payPeriods.weekEnd, we)))
    .all();

  if (existing.length > 0) {
    db.update(schema.payPeriods)
      .set({ manualNetCents: cents })
      .where(eq(schema.payPeriods.id, existing[0].id))
      .run();
  } else {
    db.insert(schema.payPeriods)
      .values({
        weekStart: ws,
        weekEnd: we,
        manualNetCents: cents,
        status: "forecast",
      })
      .run();
  }

  revalidatePath("/");
  revalidatePath("/turnos");
}

// Unused import trap-door — kept to signal `addLocalDays` is available if we
// later want to auto-populate several weeks at once.
void addLocalDays;
