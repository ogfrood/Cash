import { fmtBp } from "@/lib/money";

type Props = {
  /** Progress in the range 0..1. Values outside are clamped. */
  value: number;
  size?: number;
  stroke?: number;
  /** Centre content — usually a big number and a small label. */
  children?: React.ReactNode;
  /** Colour override in CSS format. Default: the accent green. */
  color?: string;
};

/**
 * Hand-rolled progress ring. No chart library — a single SVG circle whose
 * dash offset does all the work, so it scales cleanly and animates cheaply.
 */
export function ProgressRing({
  value,
  size = 140,
  stroke = 12,
  children,
  color,
}: Props) {
  const clamped = Math.min(1, Math.max(0, value));
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - clamped);

  return (
    <div
      className="relative inline-flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          className="ring-track"
          cx={size / 2}
          cy={size / 2}
          r={r}
          strokeWidth={stroke}
          fill="none"
        />
        <circle
          className="ring-fill"
          cx={size / 2}
          cy={size / 2}
          r={r}
          strokeWidth={stroke}
          fill="none"
          stroke={color ?? "var(--accent)"}
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        {children ?? (
          <span className="num-lg">{fmtBp(Math.round(clamped * 10000))}</span>
        )}
      </div>
    </div>
  );
}
