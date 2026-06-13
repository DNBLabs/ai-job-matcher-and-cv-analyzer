import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RunStatus } from "../api/client";
import { RunDetail } from "./RunDetail";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, getRun: vi.fn(), getRunResults: vi.fn() };
});

import { getRun, getRunResults } from "../api/client";

function runWith(status: RunStatus) {
  return {
    id: "r-1",
    cv_id: "cv-1",
    status,
    job_search: { role: "Engineer", location: "London", remote: false },
    created_at: "2026-06-11T00:00:00Z",
  };
}

function renderRunDetail() {
  return render(
    <MemoryRouter initialEntries={["/runs/r-1"]}>
      <Routes>
        <Route path="/runs/:runId" element={<RunDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RunDetail", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the current run status from polling", async () => {
    vi.mocked(getRun).mockResolvedValue(runWith("scraping"));

    renderRunDetail();

    await waitFor(() =>
      expect(
        screen.getByText("Scraping job boards", { selector: "strong" }),
      ).toBeInTheDocument(),
    );
  });

  it("announces completion and loads the result count", async () => {
    vi.mocked(getRun).mockResolvedValue(runWith("complete"));
    vi.mocked(getRunResults).mockResolvedValue([
      {
        id: "j-1",
        source: "adzuna",
        external_id: "a1",
        title: "Engineer",
        company: "Acme",
        url: "https://example.com",
        match_score: 80,
        interview_likelihood: "high",
        breakdown: {
          match_score: 80,
          interview_likelihood: "high",
          matched_skills: [],
          skill_gaps: [],
          red_flags: [],
          talking_points: [],
        },
        created_at: "2026-06-11T00:00:00Z",
      },
    ]);

    renderRunDetail();

    await waitFor(() => expect(screen.getByText(/complete/i)).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText(/1 result/i)).toBeInTheDocument());
  });

  it("shows a failure message when the run failed", async () => {
    vi.mocked(getRun).mockResolvedValue({
      ...runWith("failed"),
      failure_message: "Scraping failed — try again later",
    });

    renderRunDetail();

    await waitFor(() =>
      expect(screen.getByText(/scraping failed/i)).toBeInTheDocument(),
    );
  });
});
