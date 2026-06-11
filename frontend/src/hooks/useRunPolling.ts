/**
 * Poll an Analysis Run's status until it reaches a terminal state.
 *
 * Used by the run-detail page: it fetches the run immediately, then re-fetches
 * on a fixed interval while the run is still active (Queued → Scraping →
 * Scoring), stopping once the run is Complete, Failed, or Cancelled. A recursive
 * `setTimeout` (rather than `setInterval`) prevents overlapping requests when a
 * fetch is slow.
 */
import { useEffect, useState } from "react";
import { getRun, type Run, type RunStatus } from "../api/client";

const TERMINAL_STATUSES: ReadonlySet<RunStatus> = new Set<RunStatus>([
  "complete",
  "failed",
  "cancelled",
]);

/** Whether a run status is terminal (no further transitions, polling can stop). */
export function isTerminalStatus(status: RunStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

export interface RunPollingState {
  /** Latest run snapshot, or `null` before the first successful fetch. */
  run: Run | null;
  /** A user-facing message when a poll fails; cleared on the next success. */
  error: string | null;
  /** `true` while the run is being polled; `false` once terminal or idle. */
  isPolling: boolean;
}

const POLL_ERROR_MESSAGE = "We couldn't refresh the run status. Retrying…";

/**
 * Poll {@link getRun} for `runId` every `intervalMs` until the run is terminal.
 *
 * @param runId - the run to watch, or `null` to disable polling.
 * @param intervalMs - delay between polls; defaults to 3s.
 */
export function useRunPolling(runId: string | null, intervalMs = 3000): RunPollingState {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) {
      return;
    }

    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const tick = async (): Promise<void> => {
      try {
        const next = await getRun(runId);
        if (!active) {
          return;
        }
        setRun(next);
        setError(null);
        if (isTerminalStatus(next.status)) {
          return;
        }
      } catch {
        if (!active) {
          return;
        }
        setError(POLL_ERROR_MESSAGE);
      }
      if (active) {
        timer = setTimeout(() => void tick(), intervalMs);
      }
    };

    void tick();

    return () => {
      active = false;
      if (timer) {
        clearTimeout(timer);
      }
    };
  }, [runId, intervalMs]);

  // Derived rather than stored, so the effect never calls setState synchronously:
  // polling is active while a run is being watched and has not gone terminal.
  const isPolling = runId !== null && (run === null || !isTerminalStatus(run.status));

  return { run, error, isPolling };
}
