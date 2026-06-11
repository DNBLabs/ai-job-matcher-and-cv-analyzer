/**
 * Detect a cold API (scaled-to-zero Container App) and surface a warming state.
 *
 * On mount the hook probes `/health`. If the API answers quickly it reports
 * `ready`; if the probe fails or the API stays silent past `thresholdMs` it
 * reports `warming` and keeps retrying on `intervalMs` until the API wakes up.
 * The dashboard uses this to show a "warming up" banner for the 30–60s cold
 * start documented in the budget plan.
 */
import { useEffect, useState } from "react";
import { pingHealth } from "../api/client";

export type WarmupStatus = "checking" | "warming" | "ready";

export interface WarmupOptions {
  /** Show `warming` if the API has not responded within this window. */
  thresholdMs?: number;
  /** Delay between retries while the API is cold. */
  intervalMs?: number;
}

export interface WarmupState {
  status: WarmupStatus;
}

/**
 * Probe the API health endpoint until it is reachable.
 *
 * @param options - threshold for showing the warming state and retry interval.
 */
export function useApiWarmup(options: WarmupOptions = {}): WarmupState {
  const { thresholdMs = 1500, intervalMs = 2000 } = options;
  const [status, setStatus] = useState<WarmupStatus>("checking");

  useEffect(() => {
    let active = true;
    let retry: ReturnType<typeof setTimeout> | undefined;

    // If the API has not answered by the threshold, assume a cold start.
    const thresholdTimer = setTimeout(() => {
      if (active) {
        setStatus((current) => (current === "ready" ? current : "warming"));
      }
    }, thresholdMs);

    const probe = async (): Promise<void> => {
      const healthy = await pingHealth();
      if (!active) {
        return;
      }
      if (healthy) {
        clearTimeout(thresholdTimer);
        setStatus("ready");
        return;
      }
      setStatus("warming");
      retry = setTimeout(() => void probe(), intervalMs);
    };

    void probe();

    return () => {
      active = false;
      clearTimeout(thresholdTimer);
      if (retry) {
        clearTimeout(retry);
      }
    };
  }, [thresholdMs, intervalMs]);

  return { status };
}
