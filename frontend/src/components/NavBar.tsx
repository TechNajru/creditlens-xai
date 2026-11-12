"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { Role } from "@/lib/types";
import { homeFor, useAuth } from "./AuthProvider";

const TOOLS = [
  { href: "/assess", label: "Loan simulation", roles: ["applicant"] },
  { href: "/assess-public", label: "Public-data model", roles: ["applicant", "reviewer", "admin"] },
  { href: "/scenarios", label: "What-if & alternatives", roles: ["applicant"] },
  { href: "/cashflow", label: "Cash-flow upload", roles: ["applicant"] },
  { href: "/models", label: "Model evaluation", roles: ["applicant", "reviewer", "admin"] },
  { href: "/fairness", label: "Fairness audit", roles: ["reviewer", "admin"] },
] as const;

export function NavBar() {
  const path = usePathname();
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const links: { href: string; label: string }[] = [];
  if (user) {
    if (user.role === "applicant") links.push({ href: "/dashboard", label: "My applications" });
    if (user.role === "reviewer") links.push({ href: "/review", label: "Review queue" });
    if (user.role === "admin") links.push({ href: "/admin", label: "Admin" });
    for (const t of TOOLS) if ((t.roles as readonly Role[]).includes(user.role)) links.push(t);
  }
  const link = (l: { href: string; label: string }) => (
    <Link key={l.href} href={l.href} aria-current={path === l.href ? "page" : undefined}
      className={`text-sm hover:underline ${path === l.href ? "font-semibold underline" : "text-slate-600 dark:text-slate-300"}`}>{l.label}</Link>
  );
  return (
    <header className="border-b border-slate-200 dark:border-slate-800">
      <nav aria-label="Main" className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3">
        <Link href={user ? homeFor(user.role) : "/"} className="mr-2 text-lg font-bold">CreditLens XAI</Link>
        {links.map(link)}
        <div className="ml-auto flex items-center gap-3 text-sm">
          {loading ? null : user ? (
            <>
              <span className="text-slate-600 dark:text-slate-300">{user.email} <span className="rounded bg-slate-200 px-1.5 py-0.5 text-xs text-slate-900">{user.role}</span></span>
              <button type="button" onClick={async () => { await logout(); router.push("/"); }} className="rounded-md border border-slate-300 px-3 py-1 hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-800">Log out</button>
            </>
          ) : (
            <>{link({ href: "/login", label: "Log in" })}{link({ href: "/register", label: "Register" })}</>
          )}
        </div>
      </nav>
    </header>
  );
}
