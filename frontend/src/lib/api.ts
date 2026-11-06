export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type ApiErrorKind = "network" | "timeout" | "http";

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
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("The request took too long and was cancelled. Please try again.", null, "timeout");
    }
    throw new ApiError(`Cannot reach the API at ${API_BASE}. Is the backend running?`, null, "network");
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

export const postForm = <T,>(path: string, form: FormData) => request<T>(path, { method: "POST", body: form });
