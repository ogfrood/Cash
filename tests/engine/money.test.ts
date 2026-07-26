import { describe, expect, it } from "vitest";
import fc from "fast-check";

import {
  applyBp,
  dollarsToCents,
  fmtAUD,
  roundHalfAwayFromZero,
  splitByWeights,
} from "@/lib/money";

describe("dollarsToCents", () => {
  it("parses plain decimals", () => {
    expect(dollarsToCents("1234.56")).toBe(123456);
    expect(dollarsToCents("0.01")).toBe(1);
    expect(dollarsToCents("30")).toBe(3000);
  });

  it("parses pt-BR formatting (dot thousands, comma decimal)", () => {
    expect(dollarsToCents("1.234,56")).toBe(123456);
    expect(dollarsToCents("1.234")).toBe(123400);
  });

  it("parses en-AU formatting (comma thousands, dot decimal)", () => {
    expect(dollarsToCents("1,234.56")).toBe(123456);
  });

  it("survives the classic float traps", () => {
    // 0.1 + 0.2 territory: these must not drift by a cent.
    expect(dollarsToCents("0.1") + dollarsToCents("0.2")).toBe(30);
    // Two-decimal inputs must round to the exact cent.
    expect(dollarsToCents("1.99")).toBe(199);
    expect(dollarsToCents("276.92")).toBe(27692);
  });

  it("handles negatives and blanks", () => {
    expect(dollarsToCents("-45.20")).toBe(-4520);
    expect(dollarsToCents("")).toBe(0);
  });

  it("rejects nonsense", () => {
    expect(() => dollarsToCents("abc-.-")).toThrow();
  });
});

describe("roundHalfAwayFromZero", () => {
  it("is symmetric across zero", () => {
    expect(roundHalfAwayFromZero(2.5)).toBe(3);
    expect(roundHalfAwayFromZero(-2.5)).toBe(-3);
    // Math.round(-2.5) is -2, which would make negative amounts round
    // differently from positive ones.
    expect(Math.round(-2.5)).toBe(-2);
  });
});

describe("applyBp", () => {
  it("applies a basis-point rate", () => {
    expect(applyBp(10_000_00, 1500)).toBe(1_500_00); // 15% of $10,000
    expect(applyBp(100_00, 1200)).toBe(12_00); // 12% super
  });
});

describe("splitByWeights", () => {
  it("distributes the rounding remainder so parts sum to the total", () => {
    expect(splitByWeights(100, [1, 1, 1])).toEqual([34, 33, 33]);
  });

  it("returns zeros when all weights are zero", () => {
    expect(splitByWeights(100, [0, 0])).toEqual([0, 0]);
  });

  it("always sums to the total (property)", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10_000_00 }),
        fc.array(fc.integer({ min: 0, max: 1000 }), {
          minLength: 1,
          maxLength: 12,
        }),
        (total, weights) => {
          const parts = splitByWeights(total, weights);
          const sum = parts.reduce((a, b) => a + b, 0);
          const totalWeight = weights.reduce((a, b) => a + b, 0);
          return totalWeight === 0 ? sum === 0 : sum === total;
        },
      ),
    );
  });
});

describe("fmtAUD", () => {
  it("formats in pt-BR with the AUD symbol", () => {
    // Intl uses a non-breaking space between symbol and number, and renders
    // AUD as "AU$" in pt-BR — unambiguous, which is what we want.
    expect(fmtAUD(123456).replace(/\s/g, " ")).toBe("AU$ 1.234,56");
    expect(fmtAUD(0).replace(/\s/g, " ")).toBe("AU$ 0,00");
  });
});
