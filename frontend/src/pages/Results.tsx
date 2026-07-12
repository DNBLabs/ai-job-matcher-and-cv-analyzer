import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getRun, getRunResults, type JobMatchResult, type Run } from "../api/client";
import { ResultCard } from "../components/ResultCard";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";

type Likelihood = "high" | "medium" | "low";

const LIKELIHOODS: Likelihood[] = ["high", "medium", "low"];

const LIKELIHOOD_LABELS: Record<Likelihood, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

function applyFilters(
  results: JobMatchResult[],
  likelihoodFilter: Set<Likelihood>,
  sourceFilter: Set<string>,
  minScore: number,
): JobMatchResult[] {
  return results.filter((r) => {
    if (likelihoodFilter.size > 0 && !likelihoodFilter.has(r.interview_likelihood as Likelihood))
      return false;
    if (sourceFilter.size > 0 && !sourceFilter.has(r.source)) return false;
    if (r.match_score < minScore) return false;
    return true;
  });
}

export function Results() {
  const { runId } = useParams<{ runId: string }>();
  const [run, setRun] = useState<Run | null>(null);
  const [results, setResults] = useState<JobMatchResult[]>([]);
  const [loaded, setLoaded] = useState(false);

  const [likelihoodFilter, setLikelihoodFilter] = useState<Set<Likelihood>>(new Set());
  const [sourceFilter, setSourceFilter] = useState<Set<string>>(new Set());
  const [minScore, setMinScore] = useState(0);

  useEffect(() => {
    if (!runId) return;
    let active = true;
    void (async () => {
      try {
        const [runData, resultData] = await Promise.all([getRun(runId), getRunResults(runId)]);
        if (active) {
          setRun(runData);
          setResults(resultData);
          setLoaded(true);
        }
      } catch {
        if (active) setLoaded(true);
      }
    })();
    return () => {
      active = false;
    };
  }, [runId]);

  const sources = [...new Set(results.map((r) => r.source))].sort();
  const filtered = applyFilters(results, likelihoodFilter, sourceFilter, minScore);

  function toggleLikelihood(value: Likelihood) {
    setLikelihoodFilter((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  }

  function toggleSource(value: string) {
    setSourceFilter((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  }

  const hasSourceFailures =
    run?.status === "complete" &&
    ((run.source_failures as { failures?: unknown[] } | null | undefined)
      ?.failures?.length ?? 0) > 0;

  return (
    <main className="mx-auto max-w-3xl px-4 text-foreground">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Results</h1>
        {runId && (
          <Button variant="link" asChild>
            <Link to={`/runs/${runId}`}>Back to run</Link>
          </Button>
        )}
      </header>

      {!loaded && <p role="status">Loading results…</p>}

      {hasSourceFailures && (
        <Alert
          variant="warning"
          className="mt-4"
          aria-label="Some job sources failed — results may be incomplete."
        >
          <AlertDescription>
            Some job sources failed — results may be incomplete.
          </AlertDescription>
        </Alert>
      )}

      {loaded && (
        <section
          className="mt-6 flex flex-wrap gap-4"
          aria-label="Filters"
        >
          <fieldset className="min-w-0 flex-1 space-y-2 border-0 p-0">
            <legend className="text-sm font-medium text-foreground">Interview Likelihood</legend>
            <div className="flex flex-wrap gap-3">
              {LIKELIHOODS.map((l) => (
                <label key={l} className="flex items-center gap-2 text-sm text-foreground">
                  <input
                    type="checkbox"
                    checked={likelihoodFilter.has(l)}
                    onChange={() => toggleLikelihood(l)}
                  />
                  {LIKELIHOOD_LABELS[l]}
                </label>
              ))}
            </div>
          </fieldset>

          {sources.length > 1 && (
            <fieldset className="min-w-0 flex-1 space-y-2 border-0 p-0">
              <legend className="text-sm font-medium text-foreground">Job Source</legend>
              <div className="flex flex-wrap gap-3">
                {sources.map((s) => (
                  <label key={s} className="flex items-center gap-2 text-sm text-foreground">
                    <input
                      type="checkbox"
                      checked={sourceFilter.has(s)}
                      onChange={() => toggleSource(s)}
                    />
                    {s.charAt(0).toUpperCase() + s.slice(1)}
                  </label>
                ))}
              </div>
            </fieldset>
          )}

          <div className="min-w-0 space-y-2">
            <label htmlFor="min-score" className="text-sm font-medium text-foreground">
              Min score
            </label>
            <Input
              id="min-score"
              type="number"
              min={0}
              max={100}
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              className="w-24"
            />
          </div>
        </section>
      )}

      {loaded && filtered.length === 0 && results.length > 0 && (
        <p className="mt-4 text-muted-foreground">No results match the current filters.</p>
      )}

      <ul className="mt-6 flex list-none flex-col gap-4 p-0">
        {filtered.map((result) => (
          <li key={result.id}>
            <ResultCard result={result} />
          </li>
        ))}
      </ul>
    </main>
  );
}
