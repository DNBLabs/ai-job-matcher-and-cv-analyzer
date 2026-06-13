import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { Run } from "../api/client";
import { RunHistory } from "./RunHistory";

function renderHistory(runs: Run[], cvNames: Map<string, string>) {
  return render(
    <MemoryRouter>
      <RunHistory runs={runs} cvNames={cvNames} />
    </MemoryRouter>,
  );
}

const completeRun: Run = {
  id: "r-1",
  cv_id: "cv-1",
  status: "complete",
  job_search: { role: "Backend Engineer", location: "London", remote: false },
  created_at: "2026-06-10T00:00:00Z",
};

describe("RunHistory", () => {
  it("lists a run with its CV name, search summary, status, and date", () => {
    renderHistory([completeRun], new Map([["cv-1", "React CV"]]));

    const item = screen.getByRole("listitem");
    expect(within(item).getByText("React CV")).toBeInTheDocument();
    expect(within(item).getByText(/Backend Engineer/)).toBeInTheDocument();
    expect(within(item).getByText(/London/)).toBeInTheDocument();
    expect(within(item).getByText(/Complete/)).toBeInTheDocument();
    expect(within(item).getByRole("link")).toHaveAttribute("href", "/runs/r-1");
  });

  it("summarises a remote search as Remote", () => {
    const remoteRun: Run = {
      ...completeRun,
      id: "r-2",
      job_search: { role: "Designer", location: "Remote", remote: true },
    };
    renderHistory([remoteRun], new Map([["cv-1", "React CV"]]));

    expect(screen.getByText(/Remote/)).toBeInTheDocument();
  });

  it("falls back gracefully when the CV has since been deleted", () => {
    renderHistory([completeRun], new Map());

    expect(screen.getByText(/deleted CV/i)).toBeInTheDocument();
  });

  it("shows an empty state when there are no runs", () => {
    renderHistory([], new Map());

    expect(screen.getByText(/no runs yet/i)).toBeInTheDocument();
  });
});
