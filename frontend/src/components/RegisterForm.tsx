"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, getJson } from "@/lib/api";
import { useAuth } from "./AuthProvider";
import { Notice, Spinner } from "./Notice";

interface Notice_ { version: string; text: string }

export function RegisterForm() {
  const { register } = useAuth();
  const router = useRouter();
  const [notice, setNotice] = useState<Notice_ | null>(null);
  const [noticeError, setNoticeError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getJson<Notice_>("/api/v1/consent/notice")
      .then((n) => { if (!cancelled) setNotice(n); })
      .catch((e) => { if (!cancelled) setNoticeError(e instanceof ApiError ? e.message : "Could not load the data-use notice."); });
    return () => { cancelled = true; };
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!email.trim()) { setError("Enter your email."); return; }
    if (password.length < 10) { setError("Use a password of at least 10 characters (a short phrase works well)."); return; }
    if (!accepted || !notice) { setError("You must read and accept the data-use notice."); return; }
    setBusy(true);
    try {
      await register(email.trim(), password, notice.version);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally { setBusy(false); }
  }

  return (
    <form onSubmit={onSubmit} noValidate aria-busy={busy} className="mx-auto max-w-xl space-y-4">
      <p className="text-sm text-slate-600 dark:text-slate-300">Public registration creates an <strong>applicant</strong> account. Use a fictional email address and a password you do not use anywhere else.</p>
      <div>
        <label htmlFor="reg-email" className="block text-sm font-medium">Email</label>
        <input id="reg-email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900" />
      </div>
      <div>
        <label htmlFor="reg-password" className="block text-sm font-medium">Password</label>
        <input id="reg-password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} aria-describedby="reg-pw-hint"
          className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900" />
        <p id="reg-pw-hint" className="mt-1 text-xs text-slate-500">At least 10 characters. Longer is better than complicated.</p>
      </div>
      <section aria-labelledby="notice-h" className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
        <h2 id="notice-h" className="text-sm font-semibold">Data-use notice</h2>
        {!notice && !noticeError && <Spinner label="Loading notice…" />}
        {noticeError && <Notice tone="error" title="Notice unavailable">{noticeError}</Notice>}
        {notice && <div tabIndex={0} aria-label="Data-use notice text" className="mt-2 max-h-48 overflow-y-auto whitespace-pre-line text-sm">{notice.text}</div>}
      </section>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-1" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} />
        <span>I have read and accept the data-use notice above.</span>
      </label>
      {error && <Notice tone="error" title="Could not register">{error}</Notice>}
      <button type="submit" disabled={busy} className="rounded-md bg-sky-700 px-5 py-2 font-medium text-white hover:bg-sky-800 disabled:opacity-60">
        {busy ? "Creating account…" : "Create account"}
      </button>
      <p className="text-sm text-slate-600 dark:text-slate-300">Already registered? <Link className="underline" href="/login">Log in</Link>.</p>
    </form>
  );
}
