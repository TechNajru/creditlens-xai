"use client";
import { useCallback, useEffect, useState } from "react";
import { ApiError, getJson, patchJson, postJson } from "@/lib/api";
import type { AdminModel, AdminUser, AuditEventView, MonitoringData, Role } from "@/lib/types";
import { pct } from "@/lib/format";
import { useAuth } from "./AuthProvider";
import { Notice, Spinner } from "./Notice";

const TABS = ["Users", "Models", "Monitoring", "Audit"] as const;
type Tab = (typeof TABS)[number];
const fmtShare = (v: number | null) => (v === null ? "—" : pct(v, 0));

function useLoad<T>(path: string, version: number) {
  const [state, setState] = useState<{ version: number; data?: T; error?: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    getJson<T>(path)
      .then((data) => { if (!cancelled) setState({ version, data }); })
      .catch((e) => { if (!cancelled) setState({ version, error: e instanceof ApiError ? e.message : "Could not load." }); });
    return () => { cancelled = true; };
  }, [path, version]);
  return state && state.version === version ? state : null;
}

function Guard({ s, children }: { s: { data?: unknown; error?: string } | null; children: React.ReactNode }) {
  if (!s) return <Spinner label="Loading…" />;
  if (s.error) return <Notice tone="error" title="Could not load">{s.error}</Notice>;
  return <>{children}</>;
}

function UsersTab() {
  const { user: me } = useAuth();
  const [v, setV] = useState(0);
  const s = useLoad<{ users: AdminUser[] }>("/api/v1/admin/users", v);
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [role, setRole] = useState<Role>("reviewer");
  const [msg, setMsg] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const run = useCallback(async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); setMsg({ tone: "success", text: ok }); setV((x) => x + 1); }
    catch (e) { setMsg({ tone: "error", text: e instanceof ApiError ? e.message : "Something went wrong." }); }
  }, []);
  return (
    <div className="space-y-4">
      {msg && <Notice tone={msg.tone} title={msg.tone === "error" ? "Error" : "Done"}>{msg.text}</Notice>}
      <Guard s={s}>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Users</caption>
            <thead><tr className="border-b border-slate-300 dark:border-slate-700"><th scope="col" className="py-1 pr-3">Email</th><th scope="col" className="pr-3">Role</th><th scope="col" className="pr-3">Active</th><th scope="col" className="pr-3">Applications</th></tr></thead>
            <tbody>{s?.data?.users.map((u) => (
              <tr key={u.id} className="border-b border-slate-100 dark:border-slate-800">
                <td className="py-1 pr-3">{u.email}{me?.id === u.id ? " (you)" : ""}</td>
                <td className="pr-3">
                  <select aria-label={`Role for ${u.email}`} value={u.role} disabled={me?.id === u.id}
                    onChange={(e) => run(() => patchJson(`/api/v1/admin/users/${u.id}`, { role: e.target.value }), `Role updated for ${u.email}. They must log in again.`)}
                    className="rounded border border-slate-300 bg-white px-1 py-0.5 dark:border-slate-600 dark:bg-slate-900">
                    <option value="applicant">applicant</option><option value="reviewer">reviewer</option><option value="admin">admin</option>
                  </select>
                </td>
                <td className="pr-3"><input type="checkbox" aria-label={`Active: ${u.email}`} checked={u.is_active} disabled={me?.id === u.id}
                  onChange={(e) => run(() => patchJson(`/api/v1/admin/users/${u.id}`, { is_active: e.target.checked }), `${u.email} ${e.target.checked ? "activated" : "deactivated"}.`)} /></td>
                <td className="pr-3 tabular-nums">{u.applications}</td>
              </tr>))}</tbody>
          </table>
        </div>
      </Guard>
      <form className="grid gap-3 rounded-lg border border-slate-200 p-3 md:grid-cols-4 dark:border-slate-700"
        onSubmit={(e) => { e.preventDefault(); run(() => postJson("/api/v1/admin/users", { email, password, role }), `Created ${email}.`).then(() => setPassword("")); }}>
        <div><label htmlFor="nu-email" className="block text-sm">New user email</label><input id="nu-email" value={email} onChange={(e) => setEmail(e.target.value)} className="w-full rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900" /></div>
        <div><label htmlFor="nu-pass" className="block text-sm">Password (10+ characters)</label><input id="nu-pass" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900" /></div>
        <div><label htmlFor="nu-role" className="block text-sm">Role</label><select id="nu-role" value={role} onChange={(e) => setRole(e.target.value as Role)} className="w-full rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900"><option value="reviewer">reviewer</option><option value="admin">admin</option><option value="applicant">applicant</option></select></div>
        <div className="flex items-end"><button type="submit" className="rounded-md bg-sky-700 px-4 py-1.5 text-sm font-medium text-white">Create user</button></div>
      </form>
    </div>
  );
}

function ModelsTab() {
  const [v, setV] = useState(0);
  const s = useLoad<{ models: AdminModel[] }>("/api/v1/admin/models", v);
  const [msg, setMsg] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const run = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); setMsg({ tone: "success", text: ok }); setV((x) => x + 1); }
    catch (e) { setMsg({ tone: "error", text: e instanceof ApiError ? e.message : "Something went wrong." }); }
  };
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600 dark:text-slate-300">Applications are scored by the <strong>active simulation</strong> model. Register the latest trained file first, then activate the version you approve. Activation applies to new assessments only.</p>
      <div className="flex gap-3">
        {(["simulation", "public"] as const).map((t) => (
          <button key={t} type="button" onClick={() => run(() => postJson("/api/v1/admin/models/register", { track: t }), `Registered the current ${t} model file (if it was new).`)}
            className="rounded-md border border-slate-400 px-3 py-1 text-sm">Register current {t} model</button>
        ))}
      </div>
      {msg && <Notice tone={msg.tone} title={msg.tone === "error" ? "Error" : "Done"}>{msg.text}</Notice>}
      <Guard s={s}>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Model versions</caption>
            <thead><tr className="border-b border-slate-300 dark:border-slate-700"><th scope="col" className="py-1 pr-3">Track</th><th scope="col" className="pr-3">Version</th><th scope="col" className="pr-3">Checksum</th><th scope="col" className="pr-3">Trained</th><th scope="col" className="pr-3">State</th><th scope="col"><span className="sr-only">Action</span></th></tr></thead>
            <tbody>{s?.data?.models.map((m) => (
              <tr key={m.id} className="border-b border-slate-100 dark:border-slate-800">
                <td className="py-1 pr-3">{m.track}</td><td className="pr-3 break-all">{m.version}</td><td className="pr-3 font-mono text-xs">{m.artifact_sha256.slice(0, 12)}</td>
                <td className="pr-3">{String(m.summary.trained_at_utc ?? "—").slice(0, 10)}</td>
                <td className="pr-3 font-medium">{m.is_active ? "ACTIVE" : "inactive"}</td>
                <td>{!m.is_active && <button type="button" onClick={() => run(() => postJson(`/api/v1/admin/models/${m.id}/activate`, {}), `Activated ${m.version}.`)} className="rounded border border-emerald-700 px-2 py-0.5 text-emerald-800 dark:text-emerald-200">Activate</button>}</td>
              </tr>))}</tbody>
          </table>
        </div>
      </Guard>
    </div>
  );
}

function MonitoringTab() {
  const s = useLoad<MonitoringData>("/api/v1/admin/monitoring", 0);
  const m = s?.data;
  return (
    <Guard s={s}>
      {m && (
        <div className="space-y-5">
          <Notice tone="warning" title="What this can and cannot show"><ul className="list-disc pl-5">{m.notes.map((n) => <li key={n}>{n}</li>)}</ul></Notice>
          <dl className="grid gap-3 md:grid-cols-4">
            {Object.entries(m.applications_by_status).map(([k, n]) => <div key={k} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700"><dt className="text-xs text-slate-500">{k.replace(/_/g, " ")}</dt><dd className="text-xl font-semibold tabular-nums">{n}</dd></div>)}
            {Object.keys(m.applications_by_status).length === 0 && <p className="text-sm">No applications yet.</p>}
          </dl>
          <p className="text-sm">Official assessments: {m.assessments.official} · previews: {m.assessments.preview} · by model: {Object.entries(m.assessments.official_by_model_version).map(([k, n]) => `${k} (${n})`).join(", ") || "—"}</p>
          {m.prediction_distribution ? (
            <div>
              <h3 className="font-semibold">Predicted probability distribution (official assessments, n={m.prediction_distribution.n})</h3>
              <p className="text-sm">mean {pct(m.prediction_distribution.mean)} · p10 {pct(m.prediction_distribution.p10)} · median {pct(m.prediction_distribution.p50)} · p90 {pct(m.prediction_distribution.p90)}</p>
              <div className="mt-2 flex h-24 items-end gap-1" role="img" aria-label="Histogram of predicted probabilities in 10 bins">
                {m.prediction_distribution.histogram_10_bins.map((c, i) => { const max = Math.max(...m.prediction_distribution!.histogram_10_bins, 1); return <div key={i} title={`${i * 10}–${(i + 1) * 10}%: ${c}`} className="flex-1 rounded-t bg-sky-600" style={{ height: `${(c / max) * 100}%`, minHeight: c ? 4 : 1 }} />; })}
              </div>
              <div className="flex justify-between text-xs text-slate-500"><span>0%</span><span>100%</span></div>
            </div>
          ) : <p className="text-sm">No official assessments yet.</p>}
          <p className="text-sm">Submitted: {m.input_missingness.submitted_applications} · credit history unknown: {fmtShare(m.input_missingness.credit_history_unknown_share)} · no transaction file: {fmtShare(m.input_missingness.no_cashflow_file_share)}</p>
          <p className="text-sm">Reviewer decisions: {m.review.decisions} · approved share {fmtShare(m.review.approved_share)} · override share {fmtShare(m.review.override_share)}</p>
        </div>
      )}
    </Guard>
  );
}

function AuditTab() {
  const s = useLoad<{ events: AuditEventView[] }>("/api/v1/admin/audit?limit=100", 0);
  const [verify, setVerify] = useState<{ ok: boolean; checked: number; first_bad_event_id: number | null } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="space-y-4">
      <button type="button" onClick={async () => { setErr(null); try { setVerify(await getJson("/api/v1/admin/audit/verify")); } catch (e) { setErr(e instanceof ApiError ? e.message : "Verification failed to run."); } }}
        className="rounded-md bg-sky-700 px-4 py-2 text-sm font-medium text-white">Verify audit chain</button>
      {err && <Notice tone="error" title="Could not verify">{err}</Notice>}
      {verify && (verify.ok
        ? <Notice tone="success" title="Audit chain intact">{verify.checked} events checked; every hash matches.</Notice>
        : <Notice tone="error" title="Audit chain BROKEN">Event {verify.first_bad_event_id} (or an earlier edit) does not match its recorded hash.</Notice>)}
      <Guard s={s}>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Recent audit events</caption>
            <thead><tr className="border-b border-slate-300 dark:border-slate-700"><th scope="col" className="py-1 pr-3">Time</th><th scope="col" className="pr-3">Role</th><th scope="col" className="pr-3">Action</th><th scope="col" className="pr-3">Entity</th><th scope="col">Details</th></tr></thead>
            <tbody>{s?.data?.events.map((e) => (
              <tr key={e.id} className="border-b border-slate-100 align-top dark:border-slate-800"><td className="py-1 pr-3 whitespace-nowrap">{e.ts.replace("T", " ").replace("Z", "")}</td><td className="pr-3">{e.actor_role}</td><td className="pr-3">{e.action}</td><td className="pr-3">{e.entity_type} {e.entity_id.slice(0, 8)}</td><td className="text-xs">{Object.entries(e.details).map(([k, v]) => `${k}=${String(v)}`).join(", ")}</td></tr>))}</tbody>
          </table>
        </div>
      </Guard>
      <p className="text-xs text-slate-500">The audit log stores ids, event types and enum values only: never transaction text, emails or passwords.</p>
    </div>
  );
}

export function AdminConsole() {
  const [tab, setTab] = useState<Tab>("Users");
  return (
    <div className="space-y-6">
      <p className="text-sm text-slate-600 dark:text-slate-300">Administrators manage users, model versions and system monitoring. They cannot open applicants&apos; applications.</p>
      <div role="tablist" aria-label="Admin sections" className="flex flex-wrap gap-2">
        {TABS.map((t) => <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={`rounded-md border px-3 py-1.5 text-sm ${tab === t ? "border-sky-700 bg-sky-700 text-white" : "border-slate-300 dark:border-slate-600"}`}>{t}</button>)}
      </div>
      {tab === "Users" && <UsersTab />}{tab === "Models" && <ModelsTab />}{tab === "Monitoring" && <MonitoringTab />}{tab === "Audit" && <AuditTab />}
    </div>
  );
}
