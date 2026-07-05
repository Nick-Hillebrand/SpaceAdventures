const ACCESS_TOKEN_KEY = "space-adventures-access-token";

// NOTE: JWT is stored in localStorage. XSS on the frontend would allow token
// extraction — this is mitigated by a strict CSP header in production (see
// Architecture/10-security.md).
export function getAccessToken(): string | null {
  try {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAccessToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(ACCESS_TOKEN_KEY, token);
    else localStorage.removeItem(ACCESS_TOKEN_KEY);
  } catch {
    /* localStorage unavailable — no-op */
  }
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

export async function apiGet<T>(path: string): Promise<T> {
  const token = getAccessToken();
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(path, { headers });
  if (!response.ok) {
    throw await parseError(response);
  }
  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const token = getAccessToken();
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(path, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return response.json() as Promise<T>;
}
