let _accessToken: string | null = null;

const LEGACY_ACCESS_TOKEN_KEY = "space-adventures-access-token";
const LEGACY_REFRESH_TOKEN_KEY = "space-adventures-refresh-token";

// P1.4: tokens used to live in localStorage (an XSS-readable store). The
// access token now lives in memory only and the refresh token in an
// httpOnly cookie set by the backend — purge any leftovers from the old
// scheme so they're never read by mistake.
try {
  localStorage.removeItem(LEGACY_ACCESS_TOKEN_KEY);
  localStorage.removeItem(LEGACY_REFRESH_TOKEN_KEY);
} catch {
  /* localStorage unavailable — no-op */
}

export function getAccessToken(): string | null {
  return _accessToken;
}

export function setAccessToken(token: string | null): void {
  _accessToken = token;
}

export interface ApiError {
  code: string;
  message: string;
  status: number;
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const body = await response.json();
    const err = body?.error ?? body?.detail?.error;
    if (err?.code) return { code: err.code, message: err.message ?? "", status: response.status };
  } catch {
    /* fallthrough */
  }
  return { code: "INTERNAL_ERROR", message: response.statusText, status: response.status };
}

let refreshPromise: Promise<string | null> | null = null;

// Reads the sa_refresh httpOnly cookie server-side (credentials: "include"
// below) — the token itself is never visible to JS.
function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = fetch("/api/v1/auth/refresh", {
      method: "POST",
      credentials: "include",
      headers: { Accept: "application/json" },
    })
      .then(async (response) => {
        if (!response.ok) {
          setAccessToken(null);
          return null;
        }
        const data = (await response.json()) as { access_token: string };
        setAccessToken(data.access_token);
        return data.access_token;
      })
      .catch(() => {
        setAccessToken(null);
        return null;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

async function fetchWithAuth(
  path: string,
  init: RequestInit,
  tokenOverride?: string,
  allowRefresh = true,
): Promise<Response> {
  const token = tokenOverride ?? getAccessToken();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(path, { ...init, headers, credentials: "include" });

  if (response.status === 401 && allowRefresh && !tokenOverride && path !== "/api/v1/auth/refresh") {
    const newToken = await refreshAccessToken();
    if (newToken) {
      return fetchWithAuth(path, init, undefined, false);
    }
  }
  return response;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetchWithAuth(path, { method: "GET" });
  if (!response.ok) {
    throw await parseError(response);
  }
  return response.json() as Promise<T>;
}

export async function apiDelete<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetchWithAuth(path, {
    method: "DELETE",
    ...(body !== undefined
      ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
      : {}),
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  // 204 No Content — no body
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown, tokenOverride?: string): Promise<T> {
  const response = await fetchWithAuth(
    path,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    tokenOverride,
  );
  if (!response.ok) {
    throw await parseError(response);
  }
  return response.json() as Promise<T>;
}
