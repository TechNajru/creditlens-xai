"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, getJson } from "@/lib/api";
import type { AppSummary } from "@/lib/types";
import { money, pct } from "@/lib/format";
import { Notice, Spinner } from "./Notice";
import { StatusBadge } from "./StatusBadge";

export function ApplicantDashboard() {
  const [state, setState] = useState<{ apps?: AppSummary[]; error?: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    getJson<{ applications: AppSummary[] }>("/api/v1/applications")
      .then((r) => { if (!cancelled) setState({ apps: r.applications }); })
      .catch((e) => { if (!cancelled) setState({ error: e instanceof ApiError ? e.message : "Could not load your applications." }); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-600 dark:text-slate-300">Your demonstration applications and their status. Nothing here is a real loan decision.</p>
        <Link href="/applications/new" className="rounded-md bg-sky-700 px-4 py-2 text-sm font-medium text-white hover:bg-sky-800">New application</Link>
      </div>
      {!state && <Spinner label="Loading your applications…" />}
      {state?.error && <Notice tone="error" title="Could not load applications">{state.error}</Notice>}
      {state?.apps && state.apps.length === 0 && (
        <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-600 dark:border-slate-700 dark:text-slate-400">
          No applications yet. Start one with “New application”.
        </p>
      )}
      {state?.apps && state.apps.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Your applications</caption>
            <thead><tr className="border-b border-slate-300 dark:border-slate-700">
              <th scope="col" className="py-1 pr-3">Created</th><th scope="col" className="pr-3">Loan amount</th><th scope="col" className="pr-3">Tenure</th>
              <th scope="col" className="pr-3">Status</th><th scope="col" className="pr-3">Simulated probability</th><th scope="col" className="pr-3">Demo decision</th><th scope="col"><span className="sr-only">Open</span></th>
            </tr></thead>
            <tbody>
              {state.apps.map((a) => (
                <tr key={a.id} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="py-2 pr-3 whitespace-nowrap">{a.created_at.slice(0, 10)}</td>
                  <td className="pr-3 tabular-nums">{money(a.loan_amount)}</td><td className="pr-3">{a.tenure_months} months</td>
                  <td className="pr-3"><StatusBadge status={a.status} /></td>
                  <td className="pr-3 tabular-nums">{a.probability === null ? "—" : pct(a.probability)}</td>
                  <td className="pr-3">{a.decision ? a.decision.replace("demo_", "") : "—"}</td>
                  <td><Link className="underline" href={`/applications/${a.id}`} aria-label={`Open application from ${a.created_at.slice(0, 10)}`}>Open</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
