import { Link } from "react-router-dom";
import type { Run, RunStatus } from "../api/client";
import { Badge } from "./ui/badge";
import { Card } from "./ui/card";
import { cn } from "../lib/utils";

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

function statusBadgeClass(status: RunStatus): string {
  switch (status) {
    case "complete":
      return "border-transparent bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400";
    case "failed":
      return "border-transparent bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400";
    case "cancelled":
      return "border-transparent bg-muted text-muted-foreground";
    default:
      return "border-transparent bg-secondary text-secondary-foreground";
  }
}

export function RunHistory({ runs, cvNames }: RunHistoryProps) {
  if (runs.length === 0) {
    return <p className="text-sm text-muted-foreground">No runs yet.</p>;
  }

  return (
    <ul className="mt-2 flex list-none flex-col gap-2 p-0">
      {runs.map((run) => (
        <li key={run.id}>
          <Card className="flex min-w-0 flex-wrap items-center gap-3 p-3 sm:flex-nowrap">
            <span className="min-w-0 shrink font-medium">
              {cvNames.get(run.cv_id) ?? DELETED_CV_LABEL}
            </span>
            <Link
              to={`/runs/${run.id}`}
              className="min-w-0 flex-1 truncate font-medium"
            >
              {searchSummary(run)}
            </Link>
            <Badge className={cn(statusBadgeClass(run.status))}>
              {STATUS_LABELS[run.status]}
            </Badge>
            <span className="shrink-0 text-sm text-muted-foreground">
              {new Date(run.created_at).toLocaleDateString()}
            </span>
          </Card>
        </li>
      ))}
    </ul>
  );
}
