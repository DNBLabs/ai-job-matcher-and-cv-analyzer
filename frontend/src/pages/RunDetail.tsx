import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getRunResults, type RunStatus } from "../api/client";
import { isTerminalStatus, useRunPolling } from "../hooks/useRunPolling";

const STATUS_LABELS: Record<RunStatus, string> = {
  queued: "Queued",
  scraping: "Scraping job boards",
  scoring: "Scoring matches",
  complete: "Complete",
  failed: "Failed",
  cancelled: "Cancelled",
};

const PROGRESS_ORDER: RunStatus[] = ["queued", "scraping", "scoring", "complete"];

/**
 * Analysis Run detail: polls the run status until it is terminal, surfacing
 * progress and — on completion — the number of scored results with a link to
 * the full results view (built in Task 22).
 */
export function RunDetail() {
  const { runId } = useParams<{ runId: string }>();
  const { run, error, isPolling } = useRunPolling(runId ?? null);
  const [resultCount, setResultCount] = useState<number | null>(null);

  useEffect(() => {
    if (run?.status !== "complete") {
      return;
    }
    let active = true;
    void (async () => {
      try {
        const results = await getRunResults(run.id);
        if (active) {
          setResultCount(results.length);
        }
      } catch {
        // Leave the count unset; the status itself already reads "Complete".
      }
    })();
    return () => {
      active = false;
    };
  }, [run?.status, run?.id]);

  if (!run) {
    return (
      <main className="run-detail">
        <h1>Analysis run</h1>
        <p role="status">Loading run…</p>
      </main>
    );
  }

  const stepIndex = PROGRESS_ORDER.indexOf(run.status);

  return (
    <main className="run-detail">
      <header>
        <h1>Analysis run</h1>
        <Link to="/dashboard">Back to dashboard</Link>
      </header>

      <p className="run-criteria">
        {run.job_search.role} — {run.job_search.remote ? "Remote" : run.job_search.location}
      </p>

      <p className="run-status" aria-live="polite">
        Status: <strong>{STATUS_LABELS[run.status]}</strong>
      </p>

      {isPolling && <p role="status">Checking for updates…</p>}
      {error && <p className="form-error">{error}</p>}

      {!isTerminalStatus(run.status) && stepIndex >= 0 && (
        <ol className="run-progress">
          {PROGRESS_ORDER.slice(0, 3).map((step, index) => (
            <li key={step} className={index <= stepIndex ? "done" : ""}>
              {STATUS_LABELS[step]}
            </li>
          ))}
        </ol>
      )}

      {run.status === "complete" && (
        <section className="run-complete">
          <p>
            {resultCount === null
              ? "Loading results…"
              : `${resultCount} ${resultCount === 1 ? "result" : "results"} found.`}
          </p>
          <Link to={`/runs/${run.id}/results`}>View results</Link>
        </section>
      )}

      {run.status === "failed" && (
        <p role="alert" className="form-error">
          {run.failure_message ?? "This run failed. Please try again later."}
        </p>
      )}
    </main>
  );
}
