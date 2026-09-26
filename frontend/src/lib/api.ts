// Thin fetch wrapper: same-origin cookies, CSRF header on unsafe methods,
// typed errors carrying the API's stable error code.

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

function csrfToken(): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie.split("; ").find((c) => c.startsWith("bdp_csrf="));
  return match ? decodeURIComponent(match.split("=")[1]) : undefined;
}

async function request<T>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") {
    const token = csrfToken();
    if (token) headers["X-CSRF-Token"] = token;
  }
  let payload: BodyInit | undefined;
  if (form) payload = form;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const response = await fetch(`/api/v1${path}`, { method, headers, body: payload, credentials: "same-origin" });
  if (!response.ok) {
    let code = "http_" + response.status;
    let message = response.statusText;
    let details = {};
    try {
      const data = await response.json();
      if (data?.error) ({ code, message, details = {} } = data.error);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, code, message, details);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body: unknown = {}) => request<T>("POST", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
  form: <T>(path: string, form: FormData) => request<T>("POST", path, undefined, form),
};

export function agorotToShekels(agorot: number | null | undefined, locale = "he"): string {
  if (agorot === null || agorot === undefined) return "—";
  return new Intl.NumberFormat(locale === "en" ? "en-IL" : `${locale}-IL`, {
    style: "currency",
    currency: "ILS",
    maximumFractionDigits: 2,
  }).format(agorot / 100);
}

export function formatDateTime(iso: string | null | undefined, locale = "he"): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat(locale === "en" ? "en-GB" : `${locale}-IL`, {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Asia/Jerusalem",
    numberingSystem: "latn",
  }).format(new Date(iso));
}

export function formatDate(iso: string | null | undefined, locale = "he"): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat(locale === "en" ? "en-GB" : `${locale}-IL`, {
    dateStyle: "medium",
    timeZone: "Asia/Jerusalem",
    numberingSystem: "latn",
  }).format(new Date(iso));
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
