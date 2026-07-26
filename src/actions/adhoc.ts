"use server";

import { redirect } from "next/navigation";
import { z } from "zod";

import { db, schema } from "@/db";
import { dollarsToCents } from "@/lib/money";
import { weekStart } from "@/lib/time";

const AdhocSchema = z.object({
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Data inválida"),
  amount: z.string().min(1, "Valor obrigatório"),
  kind: z.enum(["abn", "informal", "tip", "bonus", "other"]),
  source: z.string().max(200).optional(),
  taxSetAside: z.string().optional(),
  notes: z.string().max(500).optional(),
});

export async function createAdhoc(formData: FormData) {
  const parsed = AdhocSchema.parse({
    date: formData.get("date"),
    amount: formData.get("amount"),
    kind: formData.get("kind"),
    source: formData.get("source") ?? undefined,
    taxSetAside: formData.get("taxSetAside") ?? undefined,
    notes: formData.get("notes") ?? undefined,
  });

  db.insert(schema.adhocIncome)
    .values({
      date: parsed.date,
      amountCents: dollarsToCents(parsed.amount),
      kind: parsed.kind,
      source: parsed.source || null,
      taxSetAsideCents: parsed.taxSetAside
        ? dollarsToCents(parsed.taxSetAside)
        : 0,
      weekStart: weekStart(parsed.date),
      notes: parsed.notes || null,
    })
    .run();

  redirect("/");
}
