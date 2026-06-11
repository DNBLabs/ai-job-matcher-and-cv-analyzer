/**
 * Thin fetch wrapper for the backend API.
 *
 * Every request sends the session cookie (`credentials: "include"`); the API
 * issues an HttpOnly cookie that JavaScript cannot read, so authentication
 * state is probed via {@link getCurrentUser} rather than inspected client-side.
 */
import { API_BASE_URL } from "../config";

export interface CurrentUser {
  id: string;
  email: string;
  is_admin: boolean;
}

/** Error carrying the HTTP status of a non-OK API response. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
}

/**
 * Resolve the signed-in account, or `null` when the session is absent/expired.
 *
 * @returns the current user on 200, `null` on 401.
 * @throws {ApiError} for any other non-OK response.
 */
export async function getCurrentUser(): Promise<CurrentUser | null> {
  const response = await apiFetch("/auth/me");
  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new ApiError(response.status, "Failed to load the current user");
  }
  return (await response.json()) as CurrentUser;
}

/**
 * Request a passwordless sign-in link for the given email.
 *
 * Resolves on success; the backend returns a generic message regardless of
 * whether the email is registered (anti-enumeration).
 *
 * @throws {ApiError} on rate limiting (429) or invalid input (400).
 */
export async function requestMagicLink(email: string): Promise<void> {
  const response = await apiFetch("/auth/magic-link", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
  if (!response.ok) {
    throw new ApiError(response.status, "Could not send the sign-in link");
  }
}

/** Sign out the current session; best-effort, errors are ignored by callers. */
export async function logout(): Promise<void> {
  await apiFetch("/auth/logout", { method: "POST" });
}

/** Full URL of the backend Google OAuth entrypoint for a browser redirect. */
export function googleLoginUrl(): string {
  return `${API_BASE_URL}/auth/google/login`;
}
