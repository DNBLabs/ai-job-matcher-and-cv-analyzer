import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import {
  PARTIAL_FAILURE_GRID,
  RESULTS,
  SELECTED_ROLES,
  SUGGESTED_TITLES,
  TOTAL_FAILURE_GRID,
  type ProtoOutcome,
} from "./bestFitFixtures";

/**
 * PROTOTYPE — THROWAWAY REFERENCE for wayfinder ticket #105. Delete this whole
 * folder (`src/prototypes/`) and its route in `App.tsx` when the real feature
 * lands; it exists only so /plan and /imp have something concrete to build
 * against while the backend for multi-title runs doesn't exist yet.
 *
 * Three variants (A/B/C) were reviewed on 2026-07-21 and the reviewer picked a
 * mix, which is what this file now renders — the losing variants and the
 * variant switcher have been deleted:
 *
 * - Entry    — C's two-door fork ("I know what I want" vs "Decide for me").
 * - Waiting  — C's centred spinner + framing, over A's per-title progress list.
 * - Results  — B's podium + chip filters, with A's per-card provenance line
 *              and B's quantified, expandable failure banner.
 *
 * Every screen reads hand-written fixtures; nothing is wired to the API.
 * URL params: `?screen=entry|waiting|results&failure=none|partial|total`
 */

type Screen = "entry" | "waiting" | "results";
type FailureMode = "none" | "partial" | "total";

const SCREENS: Screen[] = ["entry", "waiting", "results"];
const FAILURES: FailureMode[] = ["none", "partial", "total"];

const FAILURE_LABELS: Record<FailureMode, string> = {
  none: "clean run",
  partial: "Reed failed for 1 of 5 titles",
  total: "Reed failed for every title",
};

export function BestFitPrototype() {
  const [params, setParams] = useSearchParams();
  const screen = (params.get("screen") as Screen | null) ?? "entry";
  const failure = (params.get("failure") as FailureMode | null) ?? "partial";

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    next.set(key, value);
    setParams(next, { replace: true });
  }

  const grid =
    failure === "total" ? TOTAL_FAILURE_GRID : failure === "partial" ? PARTIAL_FAILURE_GRID : [];

  return (
    <>
      <div className="border-b-2 border-lime-400 bg-zinc-900 px-4 py-2 text-xs text-white">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-x-4 gap-y-2">
          <span className="font-semibold uppercase tracking-wide text-lime-400">Prototype</span>
          <span>ticket #105 — agreed design, fixture data only</span>

          <span className="ml-auto flex items-center gap-1">
            {SCREENS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setParam("screen", s)}
                className={`rounded px-2 py-0.5 capitalize ${screen === s ? "bg-lime-400 text-zinc-900" : "hover:bg-white/15"}`}
              >
                {s}
              </button>
            ))}
          </span>

          {screen === "results" && (
            <span className="flex items-center gap-1">
              <span className="text-white/60">failures:</span>
              {FAILURES.map((f) => (
                <button
                  key={f}
                  type="button"
                  title={FAILURE_LABELS[f]}
                  onClick={() => setParam("failure", f)}
                  className={`rounded px-2 py-0.5 ${failure === f ? "bg-lime-400 text-zinc-900" : "hover:bg-white/15"}`}
                >
                  {f}
                </button>
              ))}
            </span>
          )}
        </div>
      </div>

      {screen === "entry" && <EntryScreen />}
      {screen === "waiting" && <WaitingScreen />}
      {screen === "results" && <ResultsScreen grid={grid} />}
    </>
  );
}

/**
 * Variant C's fork. The two doors are stated before any title list, so the
 * choice between "search what I asked for" and "decide for me" is explicit.
 * The custom-title box lives ONLY on the single-title door — best fit searches
 * the AI suggestions and nothing else.
 */
function EntryScreen() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-semibold">How should we search?</h1>
      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <section className="flex flex-col rounded-xl border p-5">
          <h2 className="text-lg font-semibold">I know what I want</h2>
          <p className="mt-2 flex-1 text-sm text-muted-foreground">
            Search a single job title. Fastest, and you control exactly what comes back.
          </p>
          <select className="mt-4 rounded-md border bg-background px-3 py-2 text-sm">
            {SUGGESTED_TITLES.map((s) => (
              <option key={s.title}>{s.title}</option>
            ))}
            <option>Something else…</option>
          </select>
          <Button variant="outline" className="mt-3">
            Search this title
          </Button>
        </section>

        <section className="flex flex-col rounded-xl border-2 border-primary p-5">
          <h2 className="text-lg font-semibold">Decide for me</h2>
          <p className="mt-2 flex-1 text-sm text-muted-foreground">
            Search all {SUGGESTED_TITLES.length} titles we found in your CV and rank everything
            together. Slower, and the winner is often a title you&apos;d never have searched.
          </p>
          <ul className="mt-3 list-none space-y-1 p-0 text-xs text-muted-foreground">
            {SUGGESTED_TITLES.map((s) => (
              <li key={s.title}>· {s.title}</li>
            ))}
          </ul>
          <Button className="mt-4">Find my best fit</Button>
        </section>
      </div>
      <p className="mt-4 text-center text-xs text-muted-foreground">
        Either way this uses 1 of your 3 runs today.
      </p>
    </div>
  );
}

/**
 * C's centred spinner and "we'll email you" framing, over A's per-title
 * progress list — the list is what makes the longer wall-clock legible rather
 * than just slow.
 */
function WaitingScreen() {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center px-4 py-12 text-center">
      <div className="h-14 w-14 animate-spin rounded-full border-4 border-muted border-t-primary" />
      <h1 className="mt-6 text-xl font-semibold">Searching {SELECTED_ROLES.length} titles</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Because we&apos;re searching every title, this takes longer than a normal run — usually 3
        to 6 minutes. It&apos;s the only run that can be going at once, so we&apos;ll email you the
        moment it lands.
      </p>

      <ol className="mt-6 flex w-full list-none flex-col gap-2 p-0 text-left">
        {SELECTED_ROLES.map((role, i) => (
          <li key={role} className="flex items-center gap-3 rounded-md border px-3 py-2 text-sm">
            <span className="w-5 text-center">{i < 2 ? "✓" : i === 2 ? "⟳" : "·"}</span>
            <span className={i > 2 ? "text-muted-foreground" : ""}>{role}</span>
            <span className="ml-auto text-xs text-muted-foreground">
              {i < 2 ? "24 jobs" : i === 2 ? "searching…" : "queued"}
            </span>
          </li>
        ))}
      </ol>

      <div className="mt-6 flex gap-3">
        <Button variant="outline">Cancel and free up my run</Button>
        <Button variant="ghost">Back to dashboard</Button>
      </div>
    </div>
  );
}

/**
 * B's podium over a chip-filtered list, plus A's per-card provenance line.
 *
 * The failure surface is B's: a *quantified* count of incomplete (role, source)
 * searches with an expandable breakdown. It replaces today's "Some job sources
 * failed", whose problem was never that it fired too often but that it never
 * said how much was missing.
 */
function ResultsScreen({ grid }: { grid: ProtoOutcome[] }) {
  const [roleFilter, setRoleFilter] = useState<string | null>(null);
  const [showFailureDetail, setShowFailureDetail] = useState(false);

  const failed = grid.filter((o) => !o.ok);
  const visible = roleFilter ? RESULTS.filter((r) => r.matched_role === roleFilter) : RESULTS;
  const podium = visible.slice(0, 3);
  const rest = visible.slice(3);

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-semibold">Results</h1>
      <p className="mt-1 text-muted-foreground">
        We searched {SELECTED_ROLES.length} titles and scored {RESULTS.length} jobs.
      </p>

      {failed.length > 0 && (
        <Alert variant="warning" className="mt-4">
          <AlertDescription>
            <span>
              {failed.length} of {grid.length} searches didn&apos;t complete.
            </span>{" "}
            <button
              type="button"
              className="underline"
              onClick={() => setShowFailureDetail((v) => !v)}
            >
              {showFailureDetail ? "Hide detail" : "Show detail"}
            </button>
            {showFailureDetail && (
              <ul className="mt-2 list-disc pl-5 text-sm">
                {failed.map((o) => (
                  <li key={`${o.role}-${o.source}`}>
                    <span className="capitalize">{o.source}</span> for “{o.role}” — {o.detail}
                  </li>
                ))}
              </ul>
            )}
          </AlertDescription>
        </Alert>
      )}

      <section className="mt-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Our top {podium.length} for you
        </h2>
        <ol className="mt-3 flex list-none flex-col gap-3 p-0">
          {podium.map((r, i) => (
            <li
              key={r.id}
              className="flex gap-4 rounded-lg border-2 border-primary/40 bg-primary/5 px-5 py-4"
            >
              <span className="text-2xl font-bold text-primary">{i + 1}</span>
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{r.title}</p>
                <p className="text-sm text-muted-foreground">{r.company}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {r.match_score} match ·{" "}
                  <span className="capitalize">{r.interview_likelihood}</span> likelihood ·{" "}
                  <span className="capitalize">{r.source}</span>
                  {r.matched_role && <> · found under “{r.matched_role}”</>}
                </p>
              </div>
              <Button size="sm">Apply</Button>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-8">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setRoleFilter(null)}
            className={`rounded-full border px-3 py-1 text-xs ${roleFilter === null ? "bg-foreground text-background" : ""}`}
          >
            All {SELECTED_ROLES.length} titles
          </button>
          {SELECTED_ROLES.map((role) => (
            <button
              key={role}
              type="button"
              onClick={() => setRoleFilter(role)}
              className={`rounded-full border px-3 py-1 text-xs ${roleFilter === role ? "bg-foreground text-background" : ""}`}
            >
              {role} ({RESULTS.filter((r) => r.matched_role === role).length})
            </button>
          ))}
        </div>

        <ul className="mt-4 flex list-none flex-col gap-2 p-0">
          {rest.map((r) => (
            <li key={r.id} className="flex items-center gap-3 rounded-md border px-4 py-3">
              <span className="w-10 text-lg font-semibold text-primary">{r.match_score}</span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{r.title}</p>
                <p className="truncate text-sm text-muted-foreground">
                  {r.company}
                  {r.matched_role && (
                    <span className="text-muted-foreground"> · found under “{r.matched_role}”</span>
                  )}
                </p>
              </div>
              <span className="text-xs capitalize text-muted-foreground">{r.source}</span>
            </li>
          ))}
          {rest.length === 0 && (
            <li className="text-sm text-muted-foreground">Nothing else under this title.</li>
          )}
        </ul>
      </section>
    </div>
  );
}
