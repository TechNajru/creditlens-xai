"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/assess", label: "Loan simulation" },
  { href: "/assess-public", label: "Public-data model" },
  { href: "/scenarios", label: "What-if & alternatives" },
  { href: "/cashflow", label: "Cash-flow upload" },
  { href: "/fairness", label: "Fairness audit" },
  { href: "/models", label: "Model evaluation" },
];

export function NavBar() {
  const path = usePathname();
  return (
    <header className="border-b border-slate-200 dark:border-slate-800">
      <nav aria-label="Main" className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3">
        <Link href="/" className="mr-2 text-lg font-bold">CreditLens XAI</Link>
        {LINKS.slice(1).map((l) => (
          <Link key={l.href} href={l.href} aria-current={path === l.href ? "page" : undefined}
            className={`text-sm hover:underline ${path === l.href ? "font-semibold underline" : "text-slate-600 dark:text-slate-300"}`}>
            {l.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
