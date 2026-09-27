/** Minimal typed HTTP client for the GradeOps API (auth header, errors, 401 handling). */
import { apiUrl, API_PREFIX } from "./api";
import { clearToken, getToken } from "./auth";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

export type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  json?: unknown;
  form?: FormData;
  query?: Query;
  signal?: AbortSignal;
};

export function buildPath(path: string, query?: Query): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") qs.set(key, String(value));
  }
  const suffix = qs.toString();
  return `${API_PREFIX}${path}${suffix ? `?${suffix}` : ""}`;
}

export function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object") {
    const detail = (body as Record<string, unknown>).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0] as { msg?: string; loc?: unknown[] };
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : undefined;
      return field ? `${String(field)}: ${first.msg ?? "invalid"}` : first.msg ?? fallback;
    }
    if (detail && typeof detail === "object" && typeof (detail as { message?: unknown }).message === "string") {
      return (detail as { message: string }).message;
    }
  }
  return fallback;
}

/** Called when the API reports that the session is no longer valid. */
function handleUnauthorized() {
  if (typeof window === "undefined") return;
  clearToken();
  const here = window.location.pathname + window.location.search;
  if (!window.location.pathname.startsWith("/login")) {
    window.location.assign(`/login?next=${encodeURIComponent(here)}`);
  }
}

export async function rawRequest(path: string, opts: RequestOptions = {}): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  }
  const res = await fetch(apiUrl(buildPath(path, opts.query)), {
    method: opts.method ?? (body ? "POST" : "GET"),
    headers,
    body,
    cache: "no-store",
    signal: opts.signal,
  });
  if (res.status === 401 && token) handleUnauthorized();
  if (!res.ok) {
    let parsed: unknown = null;
    try {
      parsed = await res.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, errorMessage(parsed, res.statusText || `HTTP ${res.status}`));
  }
  return res;
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await rawRequest(path, opts);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
