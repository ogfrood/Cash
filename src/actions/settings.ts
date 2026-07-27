"use server";

import { revalidatePath } from "next/cache";
import { eq } from "drizzle-orm";
import { z } from "zod";

import { db, schema } from "@/db";

const TaxSchema = z.object({
  fyLabel: z.string().min(1),
  status: z.enum(["WHM", "RESIDENT", "FOREIGN"]),
  superPercent: z.string().min(1),
  withholdingMethod: z.enum(["cumulative", "annualised"]),
});

export async function updateTaxSettings(formData: FormData) {
  const parsed = TaxSchema.parse({
    fyLabel: formData.get("fyLabel"),
    status: formData.get("status"),
    superPercent: formData.get("superPercent"),
    withholdingMethod: formData.get("withholdingMethod"),
  });

  const superBp = Math.round(
    Number(parsed.superPercent.replace(",", ".")) * 100,
  );
  if (!Number.isFinite(superBp) || superBp < 0 || superBp > 10000) {
    throw new Error("Super Guarantee inválido");
  }

  const existing = db
    .select()
    .from(schema.taxSettings)
    .where(eq(schema.taxSettings.fyLabel, parsed.fyLabel))
    .all();

  if (existing.length > 0) {
    db.update(schema.taxSettings)
      .set({
        status: parsed.status,
        superGuaranteeBp: superBp,
        withholdingMethod: parsed.withholdingMethod,
      })
      .where(eq(schema.taxSettings.id, existing[0].id))
      .run();
  } else {
    db.insert(schema.taxSettings)
      .values({
        fyLabel: parsed.fyLabel,
        status: parsed.status,
        superGuaranteeBp: superBp,
        withholdingMethod: parsed.withholdingMethod,
      })
      .run();
  }

  revalidatePath("/config");
  revalidatePath("/");
}

const BreakSchema = z.object({
  defaultBreakMinutes: z.string().min(1),
  defaultBreakThresholdMinutes: z.string().min(1),
});

export async function updateBreakDefaults(formData: FormData) {
  const parsed = BreakSchema.parse({
    defaultBreakMinutes: formData.get("defaultBreakMinutes"),
    defaultBreakThresholdMinutes: formData.get("defaultBreakThresholdMinutes"),
  });

  const rows = db.select().from(schema.appSettings).all();
  const values = {
    defaultBreakMinutes: Number(parsed.defaultBreakMinutes),
    defaultBreakThresholdMinutes: Number(parsed.defaultBreakThresholdMinutes),
  };
  if (rows.length > 0) {
    db.update(schema.appSettings)
      .set(values)
      .where(eq(schema.appSettings.id, rows[0].id))
      .run();
  } else {
    db.insert(schema.appSettings).values(values).run();
  }

  revalidatePath("/config");
}
