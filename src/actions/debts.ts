"use server";

import { redirect } from "next/navigation";
import { z } from "zod";

import { db, schema } from "@/db";
import { dollarsToCents } from "@/lib/money";

const DebtSchema = z.object({
  name: z.string().min(1, "Nome obrigatório").max(80),
  kind: z.enum(["credit_card", "loan", "personal", "bnpl", "other"]),
  principal: z.string().min(1),
  currentBalance: z.string().optional(),
  dailyTarget: z.string().min(1),
  targetDate: z.string().optional(),
  emoji: z.string().max(4).optional(),
});

export async function createDebt(formData: FormData) {
  const parsed = DebtSchema.parse({
    name: formData.get("name"),
    kind: formData.get("kind"),
    principal: formData.get("principal"),
    currentBalance: formData.get("currentBalance") ?? undefined,
    dailyTarget: formData.get("dailyTarget"),
    targetDate: formData.get("targetDate") ?? undefined,
    emoji: formData.get("emoji") ?? undefined,
  });

  db.insert(schema.debts)
    .values({
      name: parsed.name,
      kind: parsed.kind,
      emoji: parsed.emoji || null,
      principalCents: dollarsToCents(parsed.principal),
      balanceOverrideCents: parsed.currentBalance
        ? dollarsToCents(parsed.currentBalance)
        : null,
      dailyTargetCents: dollarsToCents(parsed.dailyTarget),
      targetDate: parsed.targetDate || null,
    })
    .run();

  redirect("/dividas");
}

const PaymentSchema = z.object({
  debtId: z.string().min(1),
  amount: z.string().min(1),
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  note: z.string().max(200).optional(),
});

export async function logDebtPayment(formData: FormData) {
  const parsed = PaymentSchema.parse({
    debtId: formData.get("debtId"),
    amount: formData.get("amount"),
    date: formData.get("date"),
    note: formData.get("note") ?? undefined,
  });

  db.insert(schema.debtPayments)
    .values({
      debtId: Number(parsed.debtId),
      amountCents: dollarsToCents(parsed.amount),
      date: parsed.date,
      note: parsed.note || null,
    })
    .run();

  redirect("/dividas");
}
