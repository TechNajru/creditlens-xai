// Local development: call the API directly (CORS + cookies on localhost).
// Production on Vercel: set NEXT_PUBLIC_API_URL=/ so calls are same-origin and Vercel proxies /api/* to the backend
// (see next.config.ts). That keeps the session cookie first-party, which SameSite=Lax requires.
const rawBase = process.env.NEXT_PUBLIC_API_URL;
export const API_BASE = rawBase === undefined ? "http://localhost:8000" : rawBase.replace(/\/+$/, "");

export type ApiErrorKind = "network" | "timeout" | "http";

// The CSRF token lives only in memory (never localStorage/sessionStorage). It is returned by /auth/login,
// /auth/register and /auth/me, and sent back in a header on every non-GET request.
let csrfToken: string | null = null;
export const setCsrfToken = (token: string | null) => { csrfToken = token; };

export class ApiError extends Error {
  status: number | null;
  kind: ApiErrorKind;
  constructor(message: string, status: number | null, kind: ApiErrorKind) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.kind = kind;
  }
}

function detailToMessage(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail) && "message" in detail) {
    const d = detail as { message: string; problems?: string[] };
    return d.problems?.length ? `${d.message} ${d.problems.join("; ")}` : d.message;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const loc = Array.isArray(d?.loc) ? d.loc.filter((p: unknown) => p !== "body").join(".") : "";
        return loc ? `${loc}: ${d?.msg ?? "invalid"}` : String(d?.msg ?? "invalid");
      })
      .join("; ");
  }
  return `Request failed (HTTP ${status})`;
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 30000): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (method !== "GET" && csrfToken) headers.set("X-CSRF-Token", csrfToken);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: "include", signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("The request took too long and was cancelled. Please try again.", null, "timeout");
    }
    throw new ApiError(`Cannot reach the API${API_BASE ? ` at ${API_BASE}` : ""}. Is the backend running?`, null, "network");
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = (await res.json())?.detail;
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(detailToMessage(detail, res.status), res.status, "http");
  }
  return (await res.json()) as T;
}

export const getJson = <T,>(path: string) => request<T>(path);

export const postJson = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const patchJson = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const deleteReq = <T,>(path: string) => request<T>(path, { method: "DELETE" });

export const postForm = <T,>(path: string, form: FormData) => request<T>(path, { method: "POST", body: form });
