/**
 * A single-line area chart driven by a series of numbers. No library — an SVG
 * polyline, a soft gradient below, and one dot on the last point.
 *
 * Deliberately dependency-free: dropping in Recharts for a hero chart on the
 * dashboard is not worth 100kb of bundle.
 */
type Props = {
  values: number[];
  width?: number;
  height?: number;
  color?: string;
  className?: string;
};

export function Sparkline({
  values,
  width = 320,
  height = 120,
  color = "var(--accent)",
  className,
}: Props) {
  if (values.length < 2) {
    return (
      <div
        style={{ width, height }}
        className="grid place-items-center text-[13px] text-[color:var(--text-dim)]"
      >
        Sem histórico ainda
      </div>
    );
  }

  const pad = 6;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const stepX = (width - pad * 2) / (values.length - 1);

  const points = values.map((v, i) => {
    const x = pad + i * stepX;
    const y = pad + (1 - (v - min) / range) * (height - pad * 2);
    return [x, y] as const;
  });

  const line = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x},${y}`).join(" ");
  const area = `${line} L${points.at(-1)![0]},${height} L${points[0][0]},${height} Z`;
  const gradId = `spark-grad-${Math.random().toString(36).slice(2, 8)}`;

  const [lastX, lastY] = points.at(-1)!;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradId})`} />
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={lastX} cy={lastY} r={5} fill={color} />
      <circle cx={lastX} cy={lastY} r={2} fill="#000" />
    </svg>
  );
}
