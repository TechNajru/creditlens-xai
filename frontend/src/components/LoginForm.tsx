"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ApiError } from "@/lib/api";
import { homeFor, useAuth } from "./AuthProvider";
import { Notice } from "./Notice";

export function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!email.trim() || !password) { setError("Enter your email and password."); return; }
    setBusy(true);
    try {
      const user = await login(email.trim(), password);
      router.push(homeFor(user.role));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally { setBusy(false); }
  }

  return (
    <form onSubmit={onSubmit} noValidate aria-busy={busy} className="mx-auto max-w-md space-y-4">
      <div>
        <label htmlFor="login-email" className="block text-sm font-medium">Email</label>
        <input id="login-email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900" />
      </div>
      <div>
        <label htmlFor="login-password" className="block text-sm font-medium">Password</label>
        <input id="login-password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900" />
      </div>
      {error && <Notice tone="error" title="Could not log in">{error}</Notice>}
      <button type="submit" disabled={busy} className="rounded-md bg-sky-700 px-5 py-2 font-medium text-white hover:bg-sky-800 disabled:opacity-60">
        {busy ? "Logging in…" : "Log in"}
      </button>
      <p className="text-sm text-slate-600 dark:text-slate-300">No account? <Link className="underline" href="/register">Register as an applicant</Link>.</p>
    </form>
  );
}
