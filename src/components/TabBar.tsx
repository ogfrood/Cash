"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  IconBill,
  IconBuckets,
  IconHome,
  IconSettings,
  IconWallet,
} from "./Icons";

type Tab = {
  href: string;
  label: string;
  Icon: (p: { size?: number; className?: string }) => React.ReactElement;
  /** Prefixes that also activate this tab (e.g. `/caixinhas/[id]`). */
  match?: string[];
};

const tabs: Tab[] = [
  { href: "/", label: "Painel", Icon: IconHome },
  {
    href: "/caixinhas",
    label: "Caixinhas",
    Icon: IconBuckets,
    match: ["/caixinhas"],
  },
  { href: "/dividas", label: "Dívidas", Icon: IconWallet, match: ["/dividas"] },
  { href: "/contas", label: "Contas", Icon: IconBill, match: ["/contas"] },
  {
    href: "/config",
    label: "Ajustes",
    Icon: IconSettings,
    match: ["/config"],
  },
];

export function TabBar() {
  const pathname = usePathname() ?? "/";

  return (
    <nav className="tabbar" aria-label="Navegação principal">
      <ul className="mx-auto flex max-w-[520px] justify-between px-2">
        {tabs.map(({ href, label, Icon, match }) => {
          const active =
            href === "/"
              ? pathname === "/"
              : (match ?? [href]).some((p) => pathname.startsWith(p));
          return (
            <li key={href} className="flex-1">
              <Link
                href={href}
                className="flex flex-col items-center gap-1 py-1"
                style={{ color: active ? "var(--accent)" : "var(--text-muted)" }}
              >
                <Icon size={22} />
                <span className="text-[11px] font-medium">{label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
