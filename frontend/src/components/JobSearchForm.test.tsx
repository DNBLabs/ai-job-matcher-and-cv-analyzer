import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JobSearchForm } from "./JobSearchForm";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, createRun: vi.fn(), getRunQuota: vi.fn() };
});

import { ApiError, createRun, getRunQuota } from "../api/client";

const queuedRun = {
  id: "r-1",
  cv_id: "cv-1",
  status: "queued" as const,
  job_search: { role: "Engineer", location: "London", remote: false },
  created_at: "2026-06-11T00:00:00Z",
};

describe("JobSearchForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("displays remaining quota before starting a run", async () => {
    vi.mocked(getRunQuota).mockResolvedValue({ remaining: 2, concurrent_blocked: false });
    vi.mocked(createRun).mockResolvedValue(queuedRun);

    render(<JobSearchForm cvId="cv-1" initialRole="Engineer" onStarted={vi.fn()} />);

    await waitFor(() => expect(screen.getByText(/2 runs left today/i)).toBeInTheDocument());
  });

  it("starts a run with the entered criteria and reports it", async () => {
    vi.mocked(getRunQuota).mockResolvedValue({ remaining: 3, concurrent_blocked: false });
    vi.mocked(createRun).mockResolvedValue(queuedRun);
    const onStarted = vi.fn();

    render(<JobSearchForm cvId="cv-1" initialRole="Engineer" onStarted={onStarted} />);
    await waitFor(() => expect(screen.getByText(/3 runs left today/i)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/location/i), { target: { value: "London" } });
    fireEvent.click(screen.getByRole("button", { name: /start analysis run/i }));

    await waitFor(() => expect(onStarted).toHaveBeenCalledWith(queuedRun));
    expect(createRun).toHaveBeenCalledWith("cv-1", {
      role: "Engineer",
      location: "London",
      remote: false,
    });
  });

  it("sends a Remote search when the remote toggle is on", async () => {
    vi.mocked(getRunQuota).mockResolvedValue({ remaining: 1, concurrent_blocked: false });
    vi.mocked(createRun).mockResolvedValue(queuedRun);
    const onStarted = vi.fn();

    render(<JobSearchForm cvId="cv-1" initialRole="Engineer" onStarted={onStarted} />);
    await waitFor(() => expect(screen.getByText(/1 run left today/i)).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText(/remote/i));
    fireEvent.click(screen.getByRole("button", { name: /start analysis run/i }));

    await waitFor(() =>
      expect(createRun).toHaveBeenCalledWith("cv-1", {
        role: "Engineer",
        location: "Remote",
        remote: true,
      }),
    );
  });

  it("blocks starting when a run is already active", async () => {
    vi.mocked(getRunQuota).mockResolvedValue({ remaining: 2, concurrent_blocked: true });

    render(<JobSearchForm cvId="cv-1" initialRole="Engineer" onStarted={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /start analysis run/i })).toBeDisabled(),
    );
    expect(screen.getByText(/already running/i)).toBeInTheDocument();
  });

  it("surfaces a quota error returned on submit", async () => {
    vi.mocked(getRunQuota).mockResolvedValue({ remaining: 3, concurrent_blocked: false });
    vi.mocked(createRun).mockRejectedValue(new ApiError(429, "quota"));

    render(<JobSearchForm cvId="cv-1" initialRole="Engineer" onStarted={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/3 runs left today/i)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/location/i), { target: { value: "London" } });
    fireEvent.click(screen.getByRole("button", { name: /start analysis run/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
