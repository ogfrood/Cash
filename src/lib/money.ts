/**
 * Money is ALWAYS integer cents. Never a float.
 *
 * Floats are the number one source of bugs in financial software: 0.1 + 0.2
 * is not 0.3, and a budget app that silently loses a cent per allocation
 * drifts out of balance over a year. Every amount in this codebase is an
 * integer number of cents, named with a `Cents` suffix, and only converted to
 * a decimal string at the very edge, for display.
 *
 * Percentages use basis points (bp) for the same reason: 10000 bp = 100%.
 */

export const BP_SCALE = 10_000;

/**
 * Convert dollars (as typed by a human, e.g. "1234.56") to integer cents.
 *
 * Parsed digit-by-digit off the string, never via `Number` + rounding. Going
 * through a float loses the boundary cases: 1.005 is stored as
 * 1.00499999999999989, so `(1.005).toFixed(2)` is "1.00" and the cent
 * disappears. Reading the decimal digits directly makes the half-up rounding
 * exact for every input a human can type.
 */
export function dollarsToCents(input: string | number): number {
  const raw = typeof input === "number" ? String(input) : input.trim();
  if (raw === "") return 0;

  // Accept both "1.234,56" (pt-BR) and "1,234.56" (en-AU) as typed.
  const normalised = normaliseDecimalInput(raw);

  const m = /^(-?)(\d*)(?:\.(\d*))?$/.exec(normalised);
  if (!m || (m[2] === "" && !m[3])) {
    throw new Error(`Valor monetário inválido: ${input}`);
  }

  const [, sign, intPart, fracPart = ""] = m;
  const frac2 = (fracPart + "00").slice(0, 2);
  let cents = Number(intPart || "0") * 100 + Number(frac2);

  // Round half up on the third decimal digit.
  if (fracPart.length > 2 && Number(fracPart[2]) >= 5) cents += 1;

  return sign === "-" ? -cents : cents;
}

/**
 * Figure out which separator is the decimal one.
 *
 * When both `,` and `.` appear, whichever comes last is the decimal — thousands
 * separators never come after the decimal point. With just one separator it is
 * genuinely ambiguous ("1.234" is $1.23 in en-AU and $1234 in pt-BR): if there
 * are exactly three digits after it we treat it as thousands, otherwise as
 * decimal. This is the heuristic accounting apps use.
 */
function normaliseDecimalInput(raw: string): string {
  const cleaned = raw.replace(/[^\d.,-]/g, "");
  const lastComma = cleaned.lastIndexOf(",");
  const lastDot = cleaned.lastIndexOf(".");
  if (lastComma === -1 && lastDot === -1) return cleaned;

  const hasBoth = lastComma !== -1 && lastDot !== -1;
  let decimalSep: string;
  if (hasBoth) {
    decimalSep = lastComma > lastDot ? "," : ".";
  } else {
    const sep = lastComma !== -1 ? "," : ".";
    const trailing = cleaned.split(sep).at(-1) ?? "";
    // Exactly three digits after a lone separator → thousands, not decimal.
    decimalSep = trailing.length === 3 ? "" : sep;
  }

  const thousandsSep = decimalSep === "," ? "." : decimalSep === "." ? "," : "";
  let out = cleaned;
  if (thousandsSep) out = out.split(thousandsSep).join("");
  if (decimalSep && decimalSep !== ".") out = out.replace(decimalSep, ".");
  if (!decimalSep) out = out.split(/[,.]/).join("");
  return out;
}

const AUD = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "AUD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Format cents for display, e.g. 123456 -> "A$ 1.234,56". */
export function fmtAUD(cents: number): string {
  return AUD.format(cents / 100);
}

/** Format cents without the currency symbol, e.g. 123456 -> "1.234,56". */
export function fmtAmount(cents: number): string {
  return (cents / 100).toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Apply a basis-point rate to an amount, rounding half away from zero. */
export function applyBp(cents: number, bp: number): number {
  return roundHalfAwayFromZero((cents * bp) / BP_SCALE);
}

/** Format basis points as a percentage, e.g. 1500 -> "15%". */
export function fmtBp(bp: number): string {
  return `${(bp / 100).toLocaleString("pt-BR", {
    maximumFractionDigits: 2,
  })}%`;
}

/**
 * `Math.round` rounds -0.5 to -0 (toward positive infinity), which makes
 * negative amounts round differently from positive ones. For money we want
 * symmetry, so 0.5 always rounds away from zero.
 */
export function roundHalfAwayFromZero(value: number): number {
  return value < 0 ? -Math.round(-value) : Math.round(value);
}

/**
 * Split `total` cents across `weights`, distributing the rounding remainder so
 * the parts sum to exactly `total`. Largest fractional parts get the spare
 * cents first (the Hamilton / largest-remainder method).
 */
export function splitByWeights(total: number, weights: number[]): number[] {
  const totalWeight = weights.reduce((a, b) => a + b, 0);
  if (totalWeight === 0) return weights.map(() => 0);

  const exact = weights.map((w) => (total * w) / totalWeight);
  const floors = exact.map((v) => Math.floor(v));
  let remainder = total - floors.reduce((a, b) => a + b, 0);

  const order = exact
    .map((v, i) => ({ i, frac: v - Math.floor(v) }))
    .sort((a, b) => b.frac - a.frac);

  const out = [...floors];
  for (const { i } of order) {
    if (remainder <= 0) break;
    out[i] += 1;
    remainder -= 1;
  }
  return out;
}
