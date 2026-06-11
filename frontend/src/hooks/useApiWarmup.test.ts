import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useApiWarmup } from "./useApiWarmup";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, pingHealth: vi.fn() };
});

import { pingHealth } from "../api/client";

describe("useApiWarmup", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("reports ready when the API responds on the first probe", async () => {
    vi.mocked(pingHealth).mockResolvedValue(true);

    const { result } = renderHook(() => useApiWarmup({ thresholdMs: 1500, intervalMs: 2000 }));

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.status).toBe("ready");
  });

  it("shows warming while the API is cold, then ready once it wakes", async () => {
    vi.mocked(pingHealth)
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true);

    const { result } = renderHook(() => useApiWarmup({ thresholdMs: 1500, intervalMs: 2000 }));

    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.status).toBe("warming");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(result.current.status).toBe("ready");
  });
});
