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

/** Named CV PDF metadata returned by the CV endpoints. */
export interface Cv {
  id: string;
  name: string;
  uploaded_at: string;
}

/** One AI-suggested job title with its supporting rationale. */
export interface SuggestedTitle {
  title: string;
  rationale: string;
}

/** Response payload for POST /cvs/{id}/suggest-titles. */
export interface TitleSuggestions {
  titles: SuggestedTitle[];
}

/** Analysis Run lifecycle status mirrored from the backend enum. */
export type RunStatus =
  | "queued"
  | "scraping"
  | "scoring"
  | "complete"
  | "failed"
  | "cancelled";

/** Optional Job Search filters. */
export interface JobSearchFilters {
  experience_level?: string | null;
  employment_type?: string | null;
}

/** Job Search criteria pairing one CV with one Analysis Run. */
export interface JobSearchCriteria {
  role: string;
  location: string;
  remote: boolean;
  filters?: JobSearchFilters | null;
}

/** Public Analysis Run metadata. */
export interface Run {
  id: string;
  cv_id: string;
  status: RunStatus;
  job_search: JobSearchCriteria;
  source_failures?: Record<string, unknown> | null;
  failure_message?: string | null;
  created_at: string;
  completed_at?: string | null;
}

/** Remaining daily quota and concurrency state for the signed-in user. */
export interface RunQuota {
  remaining: number | null;
  concurrent_blocked: boolean;
}

/** Full AI breakdown stored on each Job Match Result. */
export interface JobMatchBreakdown {
  match_score: number;
  interview_likelihood: "High" | "Medium" | "Low";
  matched_skills: string[];
  skill_gaps: string[];
  red_flags: string[];
  talking_points: string[];
}

/** One scored listing returned by GET /runs/{id}/results. */
export interface JobMatchResult {
  id: string;
  source: string;
  external_id: string;
  title: string;
  company: string;
  url: string;
  match_score: number;
  interview_likelihood: "High" | "Medium" | "Low";
  breakdown: JobMatchBreakdown;
  created_at: string;
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

/**
 * Issue a JSON request and parse the body, throwing {@link ApiError} on non-OK.
 *
 * @throws {ApiError} carrying the HTTP status for any non-2xx response.
 */
async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  errorMessage = "Request failed",
): Promise<T> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage);
  }
  return (await response.json()) as T;
}

/** List the signed-in user's active (non-deleted) CVs. */
export function listCvs(): Promise<Cv[]> {
  return requestJson<Cv[]>("/cvs", {}, "Failed to load your CVs");
}

/**
 * Upload a named CV PDF as multipart form data.
 *
 * The browser sets the multipart boundary, so this call must not send a JSON
 * `Content-Type`; it bypasses {@link apiFetch} for that reason.
 *
 * @throws {ApiError} on validation failure (400) or other non-2xx responses.
 */
export async function uploadCv(name: string, file: File): Promise<Cv> {
  const form = new FormData();
  form.append("name", name);
  form.append("file", file);
  const response = await fetch(`${API_BASE_URL}/cvs`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  if (!response.ok) {
    throw new ApiError(response.status, "Could not upload the CV");
  }
  return (await response.json()) as Cv;
}

/** Soft-delete an owned CV; idempotent on the server. */
export async function deleteCv(cvId: string): Promise<void> {
  const response = await apiFetch(`/cvs/${cvId}`, { method: "DELETE" });
  if (!response.ok) {
    throw new ApiError(response.status, "Could not delete the CV");
  }
}

/** Request sync AI Suggested Job Titles for an owned CV. */
export function suggestTitles(cvId: string): Promise<TitleSuggestions> {
  return requestJson<TitleSuggestions>(
    `/cvs/${cvId}/suggest-titles`,
    { method: "POST" },
    "Could not suggest job titles",
  );
}

/** List the signed-in user's Analysis Runs, newest first. */
export function listRuns(): Promise<Run[]> {
  return requestJson<Run[]>("/runs", {}, "Failed to load your runs");
}

/** Fetch a single Analysis Run by id (used by status polling). */
export function getRun(runId: string): Promise<Run> {
  return requestJson<Run>(`/runs/${runId}`, {}, "Failed to load the run");
}

/**
 * Start a new Analysis Run for an owned CV and Job Search criteria.
 *
 * @throws {ApiError} carrying the status on validation (400) or quota/concurrency (429).
 */
export function createRun(cvId: string, jobSearch: JobSearchCriteria): Promise<Run> {
  return requestJson<Run>(
    "/runs",
    {
      method: "POST",
      body: JSON.stringify({ cv_id: cvId, job_search: jobSearch }),
    },
    "Could not start the run",
  );
}

/** Fetch ranked Job Match Results for a completed Analysis Run. */
export function getRunResults(runId: string): Promise<JobMatchResult[]> {
  return requestJson<JobMatchResult[]>(
    `/runs/${runId}/results`,
    {},
    "Failed to load run results",
  );
}

/** Fetch remaining daily quota and concurrency state. */
export function getRunQuota(): Promise<RunQuota> {
  return requestJson<RunQuota>("/runs/quota", {}, "Failed to load run quota");
}

/**
 * Probe the API health endpoint for cold-start detection.
 *
 * @returns `true` when the API responds OK; `false` when it is unreachable
 *   (e.g. a scaled-to-zero Container App still warming up).
 */
export async function pingHealth(): Promise<boolean> {
  try {
    const response = await apiFetch("/health");
    return response.ok;
  } catch {
    return false;
  }
}
