import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getRunResults, type RunStatus } from "../api/client";
import { isTerminalStatus, useRunPolling } from "../hooks/useRunPolling";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { cn } from "../lib/utils";

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
      <main className="mx-auto max-w-3xl px-4 text-foreground">
        <h1 className="text-2xl font-semibold">Analysis run</h1>
        <p role="status">Loading run…</p>
      </main>
    );
  }

  const stepIndex = PROGRESS_ORDER.indexOf(run.status);

  return (
    <main className="mx-auto max-w-3xl px-4 text-foreground">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Analysis run</h1>
        <Button variant="link" asChild>
          <Link to="/dashboard">Back to dashboard</Link>
        </Button>
      </header>

      <p className="mt-4 text-muted-foreground">
        {run.job_search.role} — {run.job_search.remote ? "Remote" : run.job_search.location}
      </p>

      <div className="mt-4" aria-live="polite">
        Status: <Badge>{STATUS_LABELS[run.status]}</Badge>
      </div>

      {isPolling && <p role="status">Checking for updates…</p>}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {!isTerminalStatus(run.status) && stepIndex >= 0 && (
        <ol className="mt-4 flex list-none gap-2 p-0">
          {PROGRESS_ORDER.slice(0, 3).map((step, index) => (
            <li
              key={step}
              className={cn(
                "flex-1 rounded-md px-2 py-1.5 text-center text-xs",
                index <= stepIndex
                  ? "bg-primary/10 font-medium text-primary"
                  : "bg-muted text-muted-foreground",
              )}
            >
              {STATUS_LABELS[step]}
            </li>
          ))}
        </ol>
      )}

      {run.status === "complete" && (
        <section className="mt-6 space-y-3">
          <p className="text-muted-foreground">
            {resultCount === null
              ? "Loading results…"
              : `${resultCount} ${resultCount === 1 ? "result" : "results"} found.`}
          </p>
          <Button asChild>
            <Link to={`/runs/${run.id}/results`}>View results</Link>
          </Button>
        </section>
      )}

      {run.status === "failed" && (
        <Alert variant="destructive" className="mt-4">
          <AlertDescription>
            {run.failure_message ?? "This run failed. Please try again later."}
          </AlertDescription>
        </Alert>
      )}
    </main>
  );
}
