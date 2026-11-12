"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, getJson } from "@/lib/api";
import type { ReviewQueueRow } from "@/lib/types";
import { money, pct } from "@/lib/format";
import { Notice, Spinner } from "./Notice";
import { StatusBadge } from "./StatusBadge";

const FILTERS = [["manual_review", "Waiting for review"], ["info_requested", "Waiting for applicant"], ["final_demo_decision", "Decided"], ["all", "All"]] as const;

export function ReviewQueue() {
  const [filter, setFilter] = useState<string>("manual_review");
  const [state, setState] = useState<{ filter: string; rows?: ReviewQueueRow[]; error?: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    getJson<{ applications: ReviewQueueRow[] }>(`/api/v1/reviews/queue?status=${filter}`)
      .then((r) => { if (!cancelled) setState({ filter, rows: r.applications }); })
      .catch((e) => { if (!cancelled) setState({ filter, error: e instanceof ApiError ? e.message : "Could not load the queue." }); });
    return () => { cancelled = true; };
  }, [filter]);

  const loading = !state || state.filter !== filter;
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600 dark:text-slate-300">Applicants appear as pseudonymous references. You record <strong>demonstration</strong> decisions only. You cannot review your own application.</p>
      <div role="tablist" aria-label="Queue filter" className="flex flex-wrap gap-2">
        {FILTERS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={filter === key} onClick={() => setFilter(key)}
            className={`rounded-md border px-3 py-1.5 text-sm ${filter === key ? "border-sky-700 bg-sky-700 text-white" : "border-slate-300 dark:border-slate-600"}`}>{label}</button>
        ))}
      </div>
      {loading && <Spinner label="Loading the queue…" />}
      {!loading && state?.error && <Notice tone="error" title="Could not load the queue">{state.error}</Notice>}
      {!loading && state?.rows && state.rows.length === 0 && <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-600 dark:border-slate-700">Nothing in this list.</p>}
      {!loading && state?.rows && state.rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Applications for review</caption>
            <thead><tr className="border-b border-slate-300 dark:border-slate-700">
              <th scope="col" className="py-1 pr-3">Applicant</th><th scope="col" className="pr-3">Submitted</th><th scope="col" className="pr-3">Loan</th>
              <th scope="col" className="pr-3">Status</th><th scope="col" className="pr-3">Simulated probability</th><th scope="col" className="pr-3">Policy</th>
              <th scope="col" className="pr-3">Flags</th><th scope="col"><span className="sr-only">Open</span></th>
            </tr></thead>
            <tbody>
              {state.rows.map((a) => (
                <tr key={a.id} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="py-2 pr-3 font-medium">{a.applicant_ref}</td><td className="pr-3 whitespace-nowrap">{a.submitted_at?.slice(0, 10) ?? "—"}</td>
                  <td className="pr-3 tabular-nums">{money(a.loan_amount)} / {a.tenure_months} mo</td><td className="pr-3"><StatusBadge status={a.status} /></td>
                  <td className="pr-3 tabular-nums">{a.probability === null ? "—" : pct(a.probability)}</td>
                  <td className="pr-3">{a.policy_passes === null ? "—" : a.policy_passes ? "rules met" : "rules not met"}</td>
                  <td className="pr-3 text-xs">{a.review_reason_codes.filter((c) => c !== "demo_policy_all_cases_reviewed").join(", ") || "—"}</td>
                  <td><Link className="underline" href={`/review/${a.id}`} aria-label={`Review ${a.applicant_ref}`}>Open</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
