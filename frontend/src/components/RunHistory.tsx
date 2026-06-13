import { Link } from "react-router-dom";
import type { Run, RunStatus } from "../api/client";

const STATUS_LABELS: Record<RunStatus, string> = {
  queued: "Queued",
  scraping: "Scraping",
  scoring: "Scoring",
  complete: "Complete",
  failed: "Failed",
  cancelled: "Cancelled",
};

/** Shown when a run references a CV the user has since soft-deleted. */
const DELETED_CV_LABEL = "Deleted CV";

/**
 * Past Analysis Runs for the signed-in user: CV name, Job Search summary,
 * status, and date, each linking to the run detail view.
 *
 * CV names are resolved from the active CV list passed in `cvNames`; runs whose
 * CV has been soft-deleted still appear (run metadata is retained) and fall back
 * to a "Deleted CV" label.
 */
export interface RunHistoryProps {
  runs: Run[];
  cvNames: Map<string, string>;
}

function searchSummary(run: Run): string {
  const where = run.job_search.remote ? "Remote" : run.job_search.location;
  return `${run.job_search.role} — ${where}`;
}

export function RunHistory({ runs, cvNames }: RunHistoryProps) {
  if (runs.length === 0) {
    return <p className="empty-state">No runs yet.</p>;
  }

  return (
    <ul className="run-list">
      {runs.map((run) => (
        <li key={run.id}>
          <span className="run-cv-name">{cvNames.get(run.cv_id) ?? DELETED_CV_LABEL}</span>
          <Link to={`/runs/${run.id}`}>{searchSummary(run)}</Link>
          <span className={`run-status status-${run.status}`}>
            {STATUS_LABELS[run.status]}
          </span>
          <span className="run-date">
            {new Date(run.created_at).toLocaleDateString()}
          </span>
        </li>
      ))}
    </ul>
  );
}
