/**
 * Job Search option lists mirrored from the backend allowlist
 * (`backend/app/domain/job_search.py`). The server re-validates every field on
 * POST /runs; these constants only drive the picker UI.
 */

/** Location value representing a remote (non-geographic) search. */
export const REMOTE_LOCATION = "Remote";

/** Supported UK cities for on-site Job Searches, alphabetically ordered. */
export const UK_CITIES: readonly string[] = [
  "Belfast",
  "Birmingham",
  "Brighton",
  "Bristol",
  "Cambridge",
  "Cardiff",
  "Coventry",
  "Edinburgh",
  "Glasgow",
  "Leeds",
  "Leicester",
  "Liverpool",
  "London",
  "Manchester",
  "Newcastle",
  "Nottingham",
  "Oxford",
  "Reading",
  "Sheffield",
  "Southampton",
];

/** Experience-level filter options (value/label pairs). */
export const EXPERIENCE_LEVELS: readonly { value: string; label: string }[] = [
  { value: "entry", label: "Entry" },
  { value: "mid", label: "Mid" },
  { value: "senior", label: "Senior" },
  { value: "lead", label: "Lead" },
  { value: "executive", label: "Executive" },
];

/** Employment-type filter options (value/label pairs). */
export const EMPLOYMENT_TYPES: readonly { value: string; label: string }[] = [
  { value: "full_time", label: "Full-time" },
  { value: "part_time", label: "Part-time" },
  { value: "contract", label: "Contract" },
  { value: "temporary", label: "Temporary" },
  { value: "internship", label: "Internship" },
];
