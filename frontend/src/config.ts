/**
 * Runtime configuration for the SPA.
 *
 * The API origin is injected at build time via `VITE_API_BASE_URL` and falls
 * back to the local Compose API for development.
 */
export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ||
  "http://localhost:8000";
