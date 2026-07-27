/** Minimal SVG icon set. Stroke-based so they scale to any size + colour. */

type P = { size?: number; className?: string };

const wrap = (
  size: number | undefined,
  className: string | undefined,
  children: React.ReactNode,
) => (
  <svg
    width={size ?? 22}
    height={size ?? 22}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    aria-hidden
  >
    {children}
  </svg>
);

export const IconHome = ({ size, className }: P) =>
  wrap(
    size,
    className,
    <>
      <path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z" />
    </>,
  );

export const IconBuckets = ({ size, className }: P) =>
  wrap(
    size,
    className,
    <>
      <path d="M4 8h16l-1.5 11a2 2 0 0 1-2 1.7H7.5a2 2 0 0 1-2-1.7z" />
      <path d="M7 8V6a5 5 0 0 1 10 0v2" />
    </>,
  );

export const IconShifts = ({ size, className }: P) =>
  wrap(
    size,
    className,
    <>
      <rect x="3" y="4" width="18" height="17" rx="2" />
      <path d="M3 9h18M8 2v4M16 2v4" />
    </>,
  );

export const IconBill = ({ size, className }: P) =>
  wrap(
    size,
    className,
    <>
      <path d="M5 3h14v18l-3-2-2 2-2-2-2 2-2-2-3 2z" />
      <path d="M9 8h6M9 12h6M9 16h4" />
    </>,
  );

export const IconSettings = ({ size, className }: P) =>
  wrap(
    size,
    className,
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </>,
  );

export const IconPlus = ({ size, className }: P) =>
  wrap(size, className, <><path d="M12 5v14M5 12h14" /></>);

export const IconArrowRight = ({ size, className }: P) =>
  wrap(size, className, <><path d="M5 12h14M13 6l6 6-6 6" /></>);

export const IconCheck = ({ size, className }: P) =>
  wrap(size, className, <><path d="M5 13l4 4L19 7" /></>);

export const IconWallet = ({ size, className }: P) =>
  wrap(
    size,
    className,
    <>
      <rect x="3" y="6" width="18" height="14" rx="3" />
      <path d="M16 13h2M3 10h18" />
    </>,
  );

export const IconCaret = ({ size, className }: P) =>
  wrap(size, className, <><path d="M6 9l6 6 6-6" /></>);

export const IconTrash = ({ size, className }: P) =>
  wrap(
    size,
    className,
    <>
      <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M6 6l1 14a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-14" />
    </>,
  );

export const IconBriefcase = ({ size, className }: P) =>
  wrap(
    size,
    className,
    <>
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18" />
    </>,
  );
