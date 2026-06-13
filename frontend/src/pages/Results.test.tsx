import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { JobMatchResult, Run } from "../api/client";
import { Results } from "./Results";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, getRun: vi.fn(), getRunResults: vi.fn() };
});

import { getRun, getRunResults } from "../api/client";

const FIXTURE_RUN: Run = {
  id: "run-1",
  cv_id: "cv-1",
  status: "complete",
  job_search: { role: "Engineer", location: "London", remote: false },
  created_at: "2026-06-13T10:00:00Z",
};

const FIXTURE_RESULTS: JobMatchResult[] = [
  {
    id: "r-1",
    source: "adzuna",
    external_id: "a1",
    title: "Senior Engineer",
    company: "Acme",
    url: "https://adzuna.co.uk/job/1",
    match_score: 80,
    interview_likelihood: "high",
    breakdown: {
      match_score: 80,
      interview_likelihood: "high",
      matched_skills: ["Python"],
      skill_gaps: [],
      red_flags: [],
      talking_points: [],
    },
    created_at: "2026-06-13T10:00:00Z",
  },
  {
    id: "r-2",
    source: "indeed",
    external_id: "i1",
    title: "Junior Dev",
    company: "Startup",
    url: "https://indeed.co.uk/job/2",
    match_score: 45,
    interview_likelihood: "medium",
    breakdown: {
      match_score: 45,
      interview_likelihood: "medium",
      matched_skills: [],
      skill_gaps: ["Go"],
      red_flags: [],
      talking_points: [],
    },
    created_at: "2026-06-13T10:00:00Z",
  },
  {
    id: "r-3",
    source: "indeed",
    external_id: "i2",
    title: "Staff Engineer",
    company: "BigCo",
    url: "https://indeed.co.uk/job/3",
    match_score: 60,
    interview_likelihood: "low",
    breakdown: {
      match_score: 60,
      interview_likelihood: "low",
      matched_skills: [],
      skill_gaps: [],
      red_flags: ["overqualified"],
      talking_points: [],
    },
    created_at: "2026-06-13T10:00:00Z",
  },
];

function renderResults() {
  return render(
    <MemoryRouter initialEntries={["/runs/run-1/results"]}>
      <Routes>
        <Route path="/runs/:runId/results" element={<Results />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Results", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders all results loaded from the API", async () => {
    vi.mocked(getRun).mockResolvedValue(FIXTURE_RUN);
    vi.mocked(getRunResults).mockResolvedValue(FIXTURE_RESULTS);

    renderResults();

    await waitFor(() => expect(screen.getByText("Senior Engineer")).toBeInTheDocument());
    expect(screen.getByText("Junior Dev")).toBeInTheDocument();
    expect(screen.getByText("Staff Engineer")).toBeInTheDocument();
  });

  it("filters to the selected interview likelihood only", async () => {
    vi.mocked(getRun).mockResolvedValue(FIXTURE_RUN);
    vi.mocked(getRunResults).mockResolvedValue(FIXTURE_RESULTS);

    renderResults();
    await waitFor(() => expect(screen.getByText("Senior Engineer")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("checkbox", { name: /^high$/i }));

    expect(screen.getByText("Senior Engineer")).toBeInTheDocument();
    expect(screen.queryByText("Junior Dev")).not.toBeInTheDocument();
    expect(screen.queryByText("Staff Engineer")).not.toBeInTheDocument();
  });

  it("filters to the selected job source only", async () => {
    vi.mocked(getRun).mockResolvedValue(FIXTURE_RUN);
    vi.mocked(getRunResults).mockResolvedValue(FIXTURE_RESULTS);

    renderResults();
    await waitFor(() => expect(screen.getByText("Senior Engineer")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("checkbox", { name: /^adzuna$/i }));

    expect(screen.getByText("Senior Engineer")).toBeInTheDocument();
    expect(screen.queryByText("Junior Dev")).not.toBeInTheDocument();
    expect(screen.queryByText("Staff Engineer")).not.toBeInTheDocument();
  });

  it("filters out results below the minimum match score", async () => {
    vi.mocked(getRun).mockResolvedValue(FIXTURE_RUN);
    vi.mocked(getRunResults).mockResolvedValue(FIXTURE_RESULTS);

    renderResults();
    await waitFor(() => expect(screen.getByText("Senior Engineer")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/min.*score/i), { target: { value: "65" } });

    expect(screen.getByText("Senior Engineer")).toBeInTheDocument();
    expect(screen.queryByText("Junior Dev")).not.toBeInTheDocument();
    expect(screen.queryByText("Staff Engineer")).not.toBeInTheDocument();
  });

  it("composes source and likelihood filters simultaneously", async () => {
    vi.mocked(getRun).mockResolvedValue(FIXTURE_RUN);
    vi.mocked(getRunResults).mockResolvedValue(FIXTURE_RESULTS);

    renderResults();
    await waitFor(() => expect(screen.getByText("Senior Engineer")).toBeInTheDocument());

    // indeed + low → only Staff Engineer (r-3) should remain
    fireEvent.click(screen.getByRole("checkbox", { name: /^indeed$/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /^low$/i }));

    expect(screen.queryByText("Senior Engineer")).not.toBeInTheDocument();
    expect(screen.queryByText("Junior Dev")).not.toBeInTheDocument();
    expect(screen.getByText("Staff Engineer")).toBeInTheDocument();
  });

  it("shows a partial-failure banner when source_failures is present", async () => {
    vi.mocked(getRun).mockResolvedValue({
      ...FIXTURE_RUN,
      source_failures: { indeed: "timeout" },
    });
    vi.mocked(getRunResults).mockResolvedValue(FIXTURE_RESULTS);

    renderResults();

    await waitFor(() =>
      expect(screen.getByText(/some job sources failed/i)).toBeInTheDocument(),
    );
  });

  it("shows an empty state when no results pass the active filters", async () => {
    vi.mocked(getRun).mockResolvedValue(FIXTURE_RUN);
    vi.mocked(getRunResults).mockResolvedValue(FIXTURE_RESULTS);

    renderResults();
    await waitFor(() => expect(screen.getByText("Senior Engineer")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/min.*score/i), { target: { value: "99" } });

    expect(screen.getByText(/no results match/i)).toBeInTheDocument();
  });
});
