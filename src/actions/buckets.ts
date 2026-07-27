"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { eq } from "drizzle-orm";
import { z } from "zod";

import { db, schema } from "@/db";
import { dollarsToCents } from "@/lib/money";

const KindSchema = z.enum(["goal", "sinking", "spending", "overflow"]);
const RuleSchema = z.enum([
  "percent",
  "fixed",
  "fill_to_target",
  "fill_paced",
  "none",
]);

const BucketFields = z.object({
  name: z.string().min(1, "Nome obrigatório").max(60),
  emoji: z.string().max(4).optional(),
  kind: KindSchema,
  targetAmount: z.string().optional(),
  targetDate: z.string().optional(),
  ruleType: RuleSchema,
  ruleValue: z.string().optional(),
  weeklyCap: z.string().optional(),
  priority: z.string().optional(),
});

function parseBucketFields(fd: FormData) {
  const parsed = BucketFields.parse({
    name: fd.get("name"),
    emoji: fd.get("emoji") ?? undefined,
    kind: fd.get("kind"),
    targetAmount: fd.get("targetAmount") ?? undefined,
    targetDate: fd.get("targetDate") ?? undefined,
    ruleType: fd.get("ruleType"),
    ruleValue: fd.get("ruleValue") ?? undefined,
    weeklyCap: fd.get("weeklyCap") ?? undefined,
    priority: fd.get("priority") ?? undefined,
  });

  // `ruleValue` means different things per ruleType: cents for `fixed`, basis
  // points for `percent`, ignored otherwise. Keep the coercion in one place.
  let ruleValue = 0;
  if (parsed.ruleType === "fixed" && parsed.ruleValue) {
    ruleValue = dollarsToCents(parsed.ruleValue);
  } else if (parsed.ruleType === "percent" && parsed.ruleValue) {
    // User types "20" meaning 20%; store as basis points.
    const bp = Math.round(Number(parsed.ruleValue.replace(",", ".")) * 100);
    if (!Number.isFinite(bp) || bp < 0) {
      throw new Error("Percentagem inválida");
    }
    ruleValue = bp;
  }

  return {
    name: parsed.name,
    emoji: parsed.emoji || null,
    kind: parsed.kind,
    targetCents: parsed.targetAmount
      ? dollarsToCents(parsed.targetAmount)
      : null,
    targetDate: parsed.targetDate || null,
    ruleType: parsed.ruleType,
    ruleValue,
    weeklyCapCents: parsed.weeklyCap ? dollarsToCents(parsed.weeklyCap) : null,
    priority: parsed.priority ? Number(parsed.priority) : 100,
  };
}

export async function createBucket(formData: FormData) {
  const values = parseBucketFields(formData);
  db.insert(schema.buckets).values(values).run();
  revalidatePath("/caixinhas");
  revalidatePath("/");
}

export async function updateBucket(formData: FormData) {
  const id = Number(formData.get("id"));
  if (!Number.isInteger(id) || id <= 0) throw new Error("Caixinha inválida");
  const values = parseBucketFields(formData);
  db.update(schema.buckets)
    .set(values)
    .where(eq(schema.buckets.id, id))
    .run();
  revalidatePath("/caixinhas");
  revalidatePath("/");
}

export async function deleteBucket(formData: FormData) {
  const id = Number(formData.get("id"));
  if (!Number.isInteger(id) || id <= 0) throw new Error("Caixinha inválida");
  // Ledger entries cascade-delete; the audit trail for a deleted bucket goes
  // with it. If we ever need "archive instead of delete", flip `isArchived`.
  db.delete(schema.buckets).where(eq(schema.buckets.id, id)).run();
  revalidatePath("/caixinhas");
  revalidatePath("/");
  redirect("/caixinhas");
}

const AdjustSchema = z.object({
  bucketId: z.string().min(1),
  amount: z.string().min(1),
  kind: z.enum(["allocation", "adjustment"]),
  note: z.string().max(200).optional(),
});

/** Manually deposit into (positive) or take out of (negative) a bucket. */
export async function adjustBucket(formData: FormData) {
  const parsed = AdjustSchema.parse({
    bucketId: formData.get("bucketId"),
    amount: formData.get("amount"),
    kind: formData.get("kind") ?? "adjustment",
    note: formData.get("note") ?? undefined,
  });
  const cents = dollarsToCents(parsed.amount);
  const today = new Date().toISOString().slice(0, 10);

  db.insert(schema.ledgerEntries)
    .values({
      bucketId: Number(parsed.bucketId),
      date: today,
      amountCents: cents,
      kind: parsed.kind,
      note: parsed.note || null,
    })
    .run();
  revalidatePath("/caixinhas");
  revalidatePath("/");
}
