"use client";
import Link from "next/link";
import type { ReactNode } from "react";
import type { Role } from "@/lib/types";
import { useAuth } from "./AuthProvider";
import { Notice, Spinner } from "./Notice";

/** Client-side convenience only. The API enforces every permission again on the server. */
export function RequireAuth({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { user, loading, error } = useAuth();
  if (loading) return <Spinner label="Checking your session…" />;
  if (!user) {
    return (
      <Notice tone="warning" title="Please log in">
        {error ? <p>{error}</p> : <p>You need an account to use this page.</p>}
        <p className="mt-1"><Link className="underline" href="/login">Log in</Link> or <Link className="underline" href="/register">create an applicant account</Link>.</p>
      </Notice>
    );
  }
  if (roles && !roles.includes(user.role)) {
    return <Notice tone="error" title="Not permitted">Your account role (<strong>{user.role}</strong>) cannot open this page.</Notice>;
  }
  return <>{children}</>;
}
