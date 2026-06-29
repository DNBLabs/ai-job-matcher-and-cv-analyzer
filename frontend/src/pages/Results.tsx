import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getRun, getRunResults, type JobMatchResult, type Run } from "../api/client";
import { ResultCard } from "../components/ResultCard";

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
    <main className="results-page">
      <header className="results-header">
        <h1>Results</h1>
        {runId && (
          <Link to={`/runs/${runId}`}>Back to run</Link>
        )}
      </header>

      {!loaded && <p role="status">Loading results…</p>}

      {hasSourceFailures && (
        <p role="alert" className="source-failure-banner">
          Some job sources failed — results may be incomplete.
        </p>
      )}

      {loaded && (
        <section className="results-filters" aria-label="Filters">
          <fieldset className="results-filter-group">
            <legend>Interview Likelihood</legend>
            {LIKELIHOODS.map((l) => (
              <label key={l} className="results-filter-option">
                <input
                  type="checkbox"
                  checked={likelihoodFilter.has(l)}
                  onChange={() => toggleLikelihood(l)}
                />
                {LIKELIHOOD_LABELS[l]}
              </label>
            ))}
          </fieldset>

          {sources.length > 1 && (
            <fieldset className="results-filter-group">
              <legend>Job Source</legend>
              {sources.map((s) => (
                <label key={s} className="results-filter-option">
                  <input
                    type="checkbox"
                    checked={sourceFilter.has(s)}
                    onChange={() => toggleSource(s)}
                  />
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </label>
              ))}
            </fieldset>
          )}

          <div className="results-filter-group">
            <label htmlFor="min-score" className="results-filter-legend">
              Min score
            </label>
            <input
              id="min-score"
              type="number"
              min={0}
              max={100}
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              className="min-score-input"
            />
          </div>
        </section>
      )}

      {loaded && filtered.length === 0 && results.length > 0 && (
        <p className="empty-state">No results match the current filters.</p>
      )}

      <ul className="results-list">
        {filtered.map((result) => (
          <li key={result.id}>
            <ResultCard result={result} />
          </li>
        ))}
      </ul>
    </main>
  );
}
