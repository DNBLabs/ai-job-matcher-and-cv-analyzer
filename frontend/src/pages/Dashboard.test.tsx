import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../auth/AuthProvider";
import { Dashboard } from "./Dashboard";
import * as client from "../api/client";

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
    getRunQuota: vi.fn(),
  };
});

vi.mock("../hooks/useApiWarmup", () => ({
  useApiWarmup: vi.fn(() => ({ status: "ready" as const })),
}));

import {
  getCurrentUser,
  getRunQuota,
  listCvs,
  listRuns,
  pingHealth,
} from "../api/client";
import { useApiWarmup } from "../hooks/useApiWarmup";

function signedIn() {
  vi.mocked(getCurrentUser).mockResolvedValue({
    id: "u-1",
    email: "alex@example.com",
    is_admin: false,
  });
  vi.mocked(pingHealth).mockResolvedValue(true);
}

function renderDashboard() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Dashboard />
      </AuthProvider>
    </MemoryRouter>,
  );
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

function getDashboardContentMain(): HTMLElement {
  const heading = screen.getByRole("heading", { name: /^dashboard$/i, level: 1 });
  const main = heading.closest("main");
  expect(main).not.toBeNull();
  return main as HTMLElement;
}

function mockDashboardContent() {
  vi.mocked(getRunQuota).mockResolvedValue({ remaining: 2, concurrent_blocked: false });
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
}

function renderAppAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("Dashboard", () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
    document.documentElement.classList.remove("dark");
    setViewportWidth(1024);
  });

  it("lists the user's CVs and run history with the CV name", async () => {
    signedIn();
    vi.mocked(getRunQuota).mockResolvedValue({ remaining: 2, concurrent_blocked: false });
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

    // CV name appears both in the CV list and against the run.
    await waitFor(() =>
      expect(screen.getAllByText("React CV").length).toBeGreaterThanOrEqual(2),
    );
    expect(screen.getByText(/Engineer/)).toBeInTheDocument();
    expect(screen.getByText(/2 runs left today/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /start a new run/i })).toBeInTheDocument();
  });

  it("shows an empty state when there are no CVs", async () => {
    signedIn();
    vi.mocked(getRunQuota).mockResolvedValue({ remaining: 3, concurrent_blocked: false });
    vi.mocked(listCvs).mockResolvedValue([]);
    vi.mocked(listRuns).mockResolvedValue([]);

    renderDashboard();

    await waitFor(() =>
      expect(screen.getByText(/no cvs yet|upload your first/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/no runs yet/i)).toBeInTheDocument();
  });

  it("blocks starting a new run when the daily quota is exhausted", async () => {
    signedIn();
    vi.mocked(getRunQuota).mockResolvedValue({ remaining: 0, concurrent_blocked: false });
    vi.mocked(listCvs).mockResolvedValue([
      { id: "cv-1", name: "React CV", uploaded_at: "2026-06-01T00:00:00Z" },
    ]);
    vi.mocked(listRuns).mockResolvedValue([]);

    renderDashboard();

    await waitFor(() =>
      expect(screen.getByText(/0 runs left today/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /start a new run/i })).toBeDisabled();
    expect(screen.queryByRole("link", { name: /start a new run/i })).not.toBeInTheDocument();
  });

  it("test_dashboard_withNavbar_doesNotRenderDuplicateInlineSignOutButton", async () => {
    vi.mocked(client.getCurrentUser).mockResolvedValue({
      id: "u-1",
      email: "alex@example.com",
      is_admin: false,
    });
    vi.mocked(client.pingHealth).mockResolvedValue(true);
    vi.mocked(client.listCvs).mockResolvedValue([]);
    vi.mocked(client.listRuns).mockResolvedValue([]);
    vi.mocked(client.getRunQuota).mockResolvedValue({
      remaining: 3,
      concurrent_blocked: false,
    });

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /dashboard/i })).toBeInTheDocument(),
    );

    const dashboardNav = document.querySelector(".dashboard-nav");
    expect(dashboardNav).not.toBeInTheDocument();
    expect(
      screen.getByRole("navigation"),
    ).not.toHaveClass("dashboard-nav");
  });

  it("test_dashboard_withNavbar_initialRender_hidesInlineSignOutAction", async () => {
    vi.mocked(client.getCurrentUser).mockResolvedValue({
      id: "u-1",
      email: "alex@example.com",
      is_admin: false,
    });
    vi.mocked(client.pingHealth).mockResolvedValue(true);
    vi.mocked(client.listCvs).mockResolvedValue([]);
    vi.mocked(client.listRuns).mockResolvedValue([]);
    vi.mocked(client.getRunQuota).mockResolvedValue({
      remaining: 3,
      concurrent_blocked: false,
    });

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /dashboard/i })).toBeInTheDocument(),
    );

    expect(
      screen.queryByRole("button", { name: /^sign out$/i }),
    ).not.toBeInTheDocument();
  });

  it("hides the daily cap and keeps starting enabled for unlimited accounts", async () => {
    signedIn();
    vi.mocked(getRunQuota).mockResolvedValue({ remaining: null, concurrent_blocked: false });
    vi.mocked(listCvs).mockResolvedValue([
      { id: "cv-1", name: "React CV", uploaded_at: "2026-06-01T00:00:00Z" },
    ]);
    vi.mocked(listRuns).mockResolvedValue([]);

    renderDashboard();

    await waitFor(() => expect(screen.getByText(/unlimited/i)).toBeInTheDocument());
    expect(screen.queryByText(/left today/i)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /start a new run/i })).toBeInTheDocument();
  });

  it("test_dashboard_viewport375_lightAndDark_noHorizontalScrollReachableLegibleColours", async () => {
    setViewportWidth(375);
    signedIn();
    mockDashboardContent();

    renderAppAt("/dashboard");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /^dashboard$/i })).toBeInTheDocument(),
    );

    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(375);

    const dashboardMain = getDashboardContentMain();
    expect(dashboardMain).not.toHaveClass("dashboard");
    expect(dashboardMain).toHaveClass(
      "mx-auto",
      "max-w-3xl",
      "px-4",
      "text-foreground",
    );

    expect(screen.getByRole("link", { name: /start a new run/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /^delete$/i })).toBeVisible();
    expect(screen.getByText(/2 runs left today/i)).toHaveClass("text-muted-foreground");

    document.documentElement.classList.add("dark");

    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(375);

    expect(dashboardMain).toHaveClass("text-foreground");
    expect(screen.getByRole("heading", { name: /your cvs/i })).toHaveClass(
      "text-foreground",
    );
    expect(screen.getByRole("heading", { name: /run history/i })).toHaveClass(
      "text-foreground",
    );
    expect(screen.getByText(/2 runs left today/i)).toHaveClass("text-muted-foreground");
  });

  it("test_dashboard_noCvs_emptyStateVisibleAndAppropriatelyStyled", async () => {
    signedIn();
    vi.mocked(getRunQuota).mockResolvedValue({ remaining: 3, concurrent_blocked: false });
    vi.mocked(listCvs).mockResolvedValue([]);
    vi.mocked(listRuns).mockResolvedValue([]);

    renderDashboard();

    const cvEmpty = await screen.findByText(/no cvs yet/i);
    expect(cvEmpty).toBeVisible();
    expect(cvEmpty).not.toHaveClass("empty-state");
    expect(cvEmpty).toHaveClass("text-muted-foreground");

    const runsEmpty = screen.getByText(/no runs yet/i);
    expect(runsEmpty).toBeVisible();
    expect(runsEmpty).not.toHaveClass("empty-state");
    expect(runsEmpty).toHaveClass("text-muted-foreground");
  });

  it("test_dashboard_warmingBannerActive_statusRoleVisuallyDistinctInfoAlert", async () => {
    signedIn();
    vi.mocked(useApiWarmup).mockReturnValue({ status: "warming" });
    vi.mocked(getRunQuota).mockResolvedValue({ remaining: 3, concurrent_blocked: false });
    vi.mocked(listCvs).mockResolvedValue([]);
    vi.mocked(listRuns).mockResolvedValue([]);

    renderDashboard();

    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent(/waking the service up/i);
    expect(banner).not.toHaveClass("warming-banner");
    expect(banner.tagName).toBe("DIV");
    expect(banner).toHaveClass("rounded-lg", "border");
    expect(banner.className).toMatch(/sky|blue/i);
  });

  it("test_dashboard_withCvs_cvListAndPrimaryActionUseShadcnNotLegacyClasses", async () => {
    signedIn();
    vi.mocked(useApiWarmup).mockReturnValue({ status: "ready" });
    mockDashboardContent();

    renderDashboard();

    const cvSection = await screen.findByRole("heading", { name: /your cvs/i });
    const cvSectionEl = cvSection.closest("section");
    expect(cvSectionEl).not.toBeNull();

    const cvList = within(cvSectionEl as HTMLElement).getByRole("list");
    expect(cvList).not.toHaveClass("cv-list");

    const cvItem = within(cvList).getByRole("listitem");
    const cvCard = cvItem.querySelector("[class*='rounded-lg'][class*='border'][class*='bg-card']");
    expect(cvCard).not.toBeNull();

    const startLink = within(cvSectionEl as HTMLElement).getByRole("link", {
      name: /start a new run/i,
    });
    expect(startLink).not.toHaveClass("primary-action");
    expect(startLink).toHaveClass("inline-flex");

    const deleteBtn = within(cvItem).getByRole("button", { name: /^delete$/i });
    expect(deleteBtn).toHaveClass("inline-flex");
  });
});
