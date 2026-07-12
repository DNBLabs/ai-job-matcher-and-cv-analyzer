import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RunStatus } from "../api/client";
import App from "../App";
import { RunDetail } from "./RunDetail";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    getCurrentUser: vi.fn(),
    logout: vi.fn(),
    pingHealth: vi.fn(),
    getRun: vi.fn(),
    getRunResults: vi.fn(),
    listCvs: vi.fn(),
    listRuns: vi.fn(),
    getRunQuota: vi.fn(),
  };
});

vi.mock("../hooks/useApiWarmup", () => ({
  useApiWarmup: vi.fn(() => ({ status: "ready" as const })),
}));

import { getCurrentUser, getRun, getRunResults, pingHealth } from "../api/client";

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

function signedIn() {
  vi.mocked(getCurrentUser).mockResolvedValue({
    id: "u-1",
    email: "alex@example.com",
    is_admin: false,
  });
  vi.mocked(pingHealth).mockResolvedValue(true);
}

function setViewportWidth(width: number) {
  Object.defineProperty(window, "innerWidth", {
    writable: true,
    configurable: true,
    value: width,
  });
  Object.defineProperty(document.documentElement, "clientWidth", {
    writable: true,
    configurable: true,
    value: width,
  });
}

function renderAppAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

function getRunDetailContentMain(): HTMLElement {
  const heading = screen.getByRole("heading", {
    name: /analysis run/i,
    level: 1,
  });
  const main = heading.closest("main");
  expect(main).not.toBeNull();
  return main as HTMLElement;
}

function getStatusBadge(statusLabel: string): HTMLElement {
  const statusLine = screen.getByText(/^Status:/i).closest("div");
  expect(statusLine).not.toBeNull();
  return within(statusLine as HTMLElement).getByText(statusLabel);
}

describe("RunDetail", () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
    document.documentElement.classList.remove("dark");
    setViewportWidth(1024);
  });

  it("shows the current run status from polling", async () => {
    vi.mocked(getRun).mockResolvedValue(runWith("scraping"));

    renderRunDetail();

    await waitFor(() =>
      expect(getStatusBadge("Scraping job boards")).toBeInTheDocument(),
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

  it("test_runDetail_viewport375_lightAndDark_noHorizontalScrollReachableLegibleColours", async () => {
    setViewportWidth(375);
    signedIn();
    vi.mocked(getRun).mockResolvedValue(runWith("scraping"));

    renderAppAt("/runs/r-1");

    await waitFor(() =>
      expect(getStatusBadge("Scraping job boards")).toBeInTheDocument(),
    );

    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(375);

    const runDetailMain = getRunDetailContentMain();
    expect(runDetailMain).not.toHaveClass("run-detail");
    expect(runDetailMain).toHaveClass(
      "mx-auto",
      "max-w-3xl",
      "px-4",
      "text-foreground",
    );

    expect(
      screen.getByRole("link", { name: /back to dashboard/i }),
    ).toBeVisible();
    expect(screen.getByText(/engineer — london/i)).toBeVisible();
    expect(screen.getByText(/queued/i)).toBeVisible();
    expect(getStatusBadge("Scraping job boards")).toBeVisible();

    expect(screen.getByText(/engineer — london/i)).toHaveClass(
      "text-muted-foreground",
    );
    expect(getStatusBadge("Scraping job boards")).toHaveClass(
      "inline-flex",
      "items-center",
    );

    document.documentElement.classList.add("dark");

    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(375);

    expect(runDetailMain).toHaveClass("text-foreground");
    expect(screen.getByRole("heading", { name: /analysis run/i })).toHaveClass(
      "text-foreground",
    );
    expect(screen.getByText(/engineer — london/i)).toHaveClass(
      "text-muted-foreground",
    );
    expect(getStatusBadge("Scraping job boards")).toHaveClass(
      "inline-flex",
      "items-center",
    );
  });

  it("test_runDetail_complete_viewport375_resultsLinkReachableLegibleColours", async () => {
    setViewportWidth(375);
    signedIn();
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

    renderAppAt("/runs/r-1");

    await waitFor(() =>
      expect(screen.getByRole("link", { name: /view results/i })).toBeInTheDocument(),
    );

    await waitFor(() =>
      expect(screen.getByText(/1 result found/i)).toBeInTheDocument(),
    );

    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(375);

    const completeSection = screen.getByRole("link", { name: /view results/i }).closest("section");
    expect(completeSection).not.toBeNull();
    expect(completeSection).not.toHaveClass("run-complete");

    expect(screen.getByRole("link", { name: /view results/i })).toBeVisible();
    expect(screen.getByRole("link", { name: /back to dashboard/i })).toBeVisible();
    expect(screen.getByText(/1 result found/i)).toHaveClass("text-muted-foreground");

    document.documentElement.classList.add("dark");

    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(375);
    expect(screen.getByText(/1 result found/i)).toHaveClass("text-muted-foreground");
  });

  it("test_runDetail_failed_alertUsesDestructiveNotFormError", async () => {
    vi.mocked(getRun).mockResolvedValue({
      ...runWith("failed"),
      failure_message: "Scraping failed — try again later",
    });

    renderRunDetail();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/scraping failed/i);
    expect(alert).not.toHaveClass("form-error");
    expect(alert).toHaveClass("rounded-lg", "border");
    expect(alert.className).toMatch(/destructive/i);
  });
});
