"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { eq } from "drizzle-orm";
import { z } from "zod";

import { db, schema } from "@/db";
import { dollarsToCents } from "@/lib/money";

const CadenceSchema = z.enum([
  "weekly",
  "fortnightly",
  "monthly",
  "quarterly",
  "yearly",
]);

const ExpenseFields = z.object({
  name: z.string().min(1, "Nome obrigatório").max(60),
  category: z.string().max(40).optional(),
  amount: z.string().min(1, "Valor obrigatório"),
  cadence: CadenceSchema,
  anchorDate: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Data inválida"),
  sinkingBucketId: z.string().optional(),
  notes: z.string().max(300).optional(),
});

function parseFields(fd: FormData) {
  const parsed = ExpenseFields.parse({
    name: fd.get("name"),
    category: fd.get("category") ?? undefined,
    amount: fd.get("amount"),
    cadence: fd.get("cadence"),
    anchorDate: fd.get("anchorDate"),
    sinkingBucketId: fd.get("sinkingBucketId") ?? undefined,
    notes: fd.get("notes") ?? undefined,
  });

  return {
    name: parsed.name,
    category: parsed.category || null,
    amountCents: dollarsToCents(parsed.amount),
    cadence: parsed.cadence,
    anchorDate: parsed.anchorDate,
    sinkingBucketId:
      parsed.sinkingBucketId && parsed.sinkingBucketId !== ""
        ? Number(parsed.sinkingBucketId)
        : null,
    notes: parsed.notes || null,
  };
}

export async function createExpense(formData: FormData) {
  db.insert(schema.fixedExpenses).values(parseFields(formData)).run();
  revalidatePath("/contas");
  revalidatePath("/");
}

export async function updateExpense(formData: FormData) {
  const id = Number(formData.get("id"));
  if (!Number.isInteger(id) || id <= 0) throw new Error("Conta inválida");
  db.update(schema.fixedExpenses)
    .set(parseFields(formData))
    .where(eq(schema.fixedExpenses.id, id))
    .run();
  revalidatePath("/contas");
  revalidatePath("/");
}

export async function deleteExpense(formData: FormData) {
  const id = Number(formData.get("id"));
  if (!Number.isInteger(id) || id <= 0) throw new Error("Conta inválida");
  db.delete(schema.fixedExpenses).where(eq(schema.fixedExpenses.id, id)).run();
  revalidatePath("/contas");
  revalidatePath("/");
  redirect("/contas");
}
