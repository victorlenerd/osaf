"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Logo from "@/components/Logo";

const NAV = [
  { href: "/", label: "Search" },
  { href: "/about", label: "About" },
];

export default function Header() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-20 border-b line backdrop-blur-md" style={{ background: "color-mix(in oklab, var(--bg) 88%, transparent)" }}>
      <div className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2" aria-label="Afefehub home">
          <Logo size={26} />
          <span className="font-display text-xl font-semibold tracking-tight" style={{ color: "var(--brand)" }}>
            Afefehub
          </span>
        </Link>
        <nav aria-label="Primary" className="flex items-center gap-1 text-sm">
          {NAV.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className="rounded-full px-3 py-1.5 font-medium transition-colors hover:bg-[var(--line)]"
                style={active ? { background: "var(--brand)", color: "var(--bg)" } : undefined}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
