import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Run, RunStatus } from "../api/client";
import { isTerminalStatus, useRunPolling } from "./useRunPolling";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, getRun: vi.fn() };
});

import { getRun } from "../api/client";

function runWith(status: RunStatus): Run {
  return {
    id: "r-1",
    cv_id: "cv-1",
    status,
    job_search: { role: "Engineer", location: "London", remote: false },
    created_at: "2026-06-11T00:00:00Z",
  };
}

describe("isTerminalStatus", () => {
  it("treats complete/failed/cancelled as terminal", () => {
    expect(isTerminalStatus("complete")).toBe(true);
    expect(isTerminalStatus("failed")).toBe(true);
    expect(isTerminalStatus("cancelled")).toBe(true);
  });

  it("treats queued/scraping/scoring as non-terminal", () => {
    expect(isTerminalStatus("queued")).toBe(false);
    expect(isTerminalStatus("scraping")).toBe(false);
    expect(isTerminalStatus("scoring")).toBe(false);
  });
});

describe("useRunPolling", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("fetches immediately and keeps polling while the run is active", async () => {
    vi.mocked(getRun).mockResolvedValue(runWith("queued"));

    const { result } = renderHook(() => useRunPolling("r-1", 3000));

    await act(async () => {
      await Promise.resolve();
    });

    expect(getRun).toHaveBeenCalledWith("r-1");
    expect(result.current.run?.status).toBe("queued");
    expect(result.current.isPolling).toBe(true);
  });

  it("polls again after the interval and stops once terminal", async () => {
    vi.mocked(getRun)
      .mockResolvedValueOnce(runWith("scraping"))
      .mockResolvedValueOnce(runWith("complete"));

    const { result } = renderHook(() => useRunPolling("r-1", 3000));

    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.run?.status).toBe("scraping");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(result.current.run?.status).toBe("complete");
    expect(result.current.isPolling).toBe(false);

    // No further polling after a terminal status.
    const callsAfterComplete = vi.mocked(getRun).mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9000);
    });
    expect(vi.mocked(getRun).mock.calls.length).toBe(callsAfterComplete);
  });

  it("surfaces an error but keeps polling on a transient failure", async () => {
    vi.mocked(getRun)
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce(runWith("complete"));

    const { result } = renderHook(() => useRunPolling("r-1", 3000));

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.error).not.toBeNull();
    expect(result.current.isPolling).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(result.current.run?.status).toBe("complete");
    expect(result.current.error).toBeNull();
  });

  it("does nothing when runId is null", async () => {
    const { result } = renderHook(() => useRunPolling(null, 3000));

    await act(async () => {
      await Promise.resolve();
    });

    expect(getRun).not.toHaveBeenCalled();
    expect(result.current.isPolling).toBe(false);
  });
});
