import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../auth/AuthProvider";
import { Dashboard } from "./Dashboard";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    getCurrentUser: vi.fn(),
    logout: vi.fn(),
    pingHealth: vi.fn(),
    listCvs: vi.fn(),
    listRuns: vi.fn(),
    deleteCv: vi.fn(),
  };
});

import { getCurrentUser, listCvs, listRuns, pingHealth } from "../api/client";

function renderDashboard() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Dashboard />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("Dashboard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists the user's CVs and run history", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue({
      id: "u-1",
      email: "alex@example.com",
      is_admin: false,
    });
    vi.mocked(pingHealth).mockResolvedValue(true);
    vi.mocked(listCvs).mockResolvedValue([
      { id: "cv-1", name: "React CV", uploaded_at: "2026-06-01T00:00:00Z" },
    ]);
    vi.mocked(listRuns).mockResolvedValue([
      {
        id: "r-1",
        cv_id: "cv-1",
        status: "complete",
        job_search: { role: "Engineer", location: "London", remote: false },
        created_at: "2026-06-10T00:00:00Z",
      },
    ]);

    renderDashboard();

    await waitFor(() => expect(screen.getByText("React CV")).toBeInTheDocument());
    expect(screen.getByText(/Engineer/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /start a new run/i })).toBeInTheDocument();
  });

  it("shows an empty state when there are no CVs", async () => {
    vi.mocked(getCurrentUser).mockResolvedValue({
      id: "u-1",
      email: "alex@example.com",
      is_admin: false,
    });
    vi.mocked(pingHealth).mockResolvedValue(true);
    vi.mocked(listCvs).mockResolvedValue([]);
    vi.mocked(listRuns).mockResolvedValue([]);

    renderDashboard();

    await waitFor(() =>
      expect(screen.getByText(/no cvs yet|upload your first/i)).toBeInTheDocument(),
    );
  });
});
