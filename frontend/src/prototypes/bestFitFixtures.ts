/**
 * PROTOTYPE FIXTURES — throwaway, delete with the rest of `src/prototypes/`.
 *
 * The best-fit backend does not exist yet (wayfinder #99 is still deciding it),
 * so every variant reads from these hand-written fixtures instead of the API.
 * Shapes deliberately mirror what #100/#104 decided the real payloads will be:
 * `roles: string[]`, a nullable `matched_role` per result, and a (role, source)
 * failure grid.
 */

export interface ProtoSuggestion {
  title: string;
  rationale: string;
}

export interface ProtoResult {
  id: string;
  source: string;
  title: string;
  company: string;
  url: string;
  match_score: number;
  interview_likelihood: "high" | "medium" | "low";
  /** #104: first-seen role only — the full matching set is NOT stored. */
  matched_role: string | null;
}

export interface ProtoOutcome {
  role: string;
  source: string;
  ok: boolean;
  detail?: string;
}

export const SUGGESTED_TITLES: ProtoSuggestion[] = [
  {
    title: "IT Support Engineer",
    rationale: "Three years on an MSP helpdesk, ticket triage and endpoint support.",
  },
  {
    title: "Junior Software Developer",
    rationale: "Python and TypeScript side projects, CI pipelines, test-driven work.",
  },
  {
    title: "Platform Engineer",
    rationale: "Azure deployments, infrastructure-as-code, container experience.",
  },
  {
    title: "Technical Support Specialist",
    rationale: "Customer-facing escalation handling and documentation writing.",
  },
  {
    title: "DevOps Engineer",
    rationale: "GitHub Actions, release automation, monitoring and alerting.",
  },
];

/** The point of the whole feature: the best job hides under a lower-ranked title. */
export const RESULTS: ProtoResult[] = [
  {
    id: "r1",
    source: "reed",
    title: "Junior Platform Engineer",
    company: "Northwind Cloud",
    url: "#",
    match_score: 91,
    interview_likelihood: "high",
    matched_role: "Platform Engineer",
  },
  {
    id: "r2",
    source: "adzuna",
    title: "Graduate Software Developer",
    company: "Lumen Labs",
    url: "#",
    match_score: 88,
    interview_likelihood: "medium",
    matched_role: "Junior Software Developer",
  },
  {
    id: "r3",
    source: "adzuna",
    title: "DevOps Engineer (Entry Level)",
    company: "Harbourline",
    url: "#",
    match_score: 88,
    interview_likelihood: "high",
    matched_role: "DevOps Engineer",
  },
  {
    id: "r4",
    source: "reed",
    title: "2nd Line Support Engineer",
    company: "Bramble MSP",
    url: "#",
    match_score: 84,
    interview_likelihood: "high",
    matched_role: "IT Support Engineer",
  },
  {
    id: "r5",
    source: "adzuna",
    title: "Application Support Analyst",
    company: "Kestrel Health",
    url: "#",
    match_score: 79,
    interview_likelihood: "medium",
    matched_role: "Technical Support Specialist",
  },
  {
    id: "r6",
    source: "adzuna",
    title: "Junior Site Reliability Engineer",
    company: "Corvid Systems",
    url: "#",
    match_score: 76,
    interview_likelihood: "low",
    matched_role: "Platform Engineer",
  },
  {
    id: "r7",
    source: "reed",
    title: "IT Technician",
    company: "Fenwick Group",
    url: "#",
    match_score: 71,
    interview_likelihood: "medium",
    matched_role: "IT Support Engineer",
  },
  {
    id: "r8",
    source: "adzuna",
    title: "Automation Engineer",
    company: "Sable Freight",
    url: "#",
    match_score: 68,
    interview_likelihood: "low",
    matched_role: null,
  },
];

export const SELECTED_ROLES = SUGGESTED_TITLES.map((s) => s.title);

/**
 * #104's (role, source) grid. Reed failed for exactly one role — the case that
 * makes today's "Some job sources failed" banner misleading.
 */
export const PARTIAL_FAILURE_GRID: ProtoOutcome[] = SELECTED_ROLES.flatMap((role) => [
  { role, source: "adzuna", ok: true },
  {
    role,
    source: "reed",
    ok: role !== "Technical Support Specialist",
    detail: role === "Technical Support Specialist" ? "timed out after 20s" : undefined,
  },
]);

/** The case where a banner genuinely is warranted: Reed down for every role. */
export const TOTAL_FAILURE_GRID: ProtoOutcome[] = SELECTED_ROLES.flatMap((role) => [
  { role, source: "adzuna", ok: true },
  { role, source: "reed", ok: false, detail: "503 from provider" },
]);
