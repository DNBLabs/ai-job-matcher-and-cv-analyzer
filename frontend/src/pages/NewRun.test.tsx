import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    getCurrentUser: vi.fn(),
    logout: vi.fn(),
    pingHealth: vi.fn(),
    listCvs: vi.fn(),
    getRunQuota: vi.fn(),
    suggestTitles: vi.fn(),
  };
});

vi.mock("../hooks/useApiWarmup", () => ({
  useApiWarmup: vi.fn(() => ({ status: "ready" as const })),
}));

import { getCurrentUser, getRunQuota, listCvs, pingHealth, suggestTitles } from "../api/client";

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

function getNewRunContentMain(): HTMLElement {
  const heading = screen.getByRole("heading", {
    name: /start a new analysis run/i,
    level: 1,
  });
  const main = heading.closest("main");
  expect(main).not.toBeNull();
  return main as HTMLElement;
}

function mockNewRunContent() {
  vi.mocked(listCvs).mockResolvedValue([
    { id: "cv-1", name: "React CV", uploaded_at: "2026-06-01T00:00:00Z" },
  ]);
}

describe("NewRun", () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
    document.documentElement.classList.remove("dark");
    setViewportWidth(1024);
  });

  it("test_newRun_viewport375_lightAndDark_noHorizontalScrollReachableLegibleColours", async () => {
    setViewportWidth(375);
    signedIn();
    mockNewRunContent();

    renderAppAt("/runs/new");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /start a new analysis run/i }),
      ).toBeInTheDocument(),
    );

    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(375);

    const newRunMain = getNewRunContentMain();
    expect(newRunMain).not.toHaveClass("new-run");
    expect(newRunMain).toHaveClass(
      "mx-auto",
      "max-w-3xl",
      "px-4",
      "text-foreground",
    );

    expect(screen.getByRole("link", { name: /cancel/i })).toBeVisible();
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /use react cv/i }),
      ).toBeVisible(),
    );
    expect(screen.getByLabelText(/cv name/i)).toBeVisible();
    expect(screen.getByRole("button", { name: /upload cv/i })).toBeVisible();

    expect(screen.getByLabelText(/cv name/i)).toHaveClass(
      "border-input",
      "bg-background",
      "text-foreground",
    );
    expect(screen.getByText(/or upload a new one/i)).toHaveClass(
      "text-muted-foreground",
    );

    document.documentElement.classList.add("dark");

    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(375);

    expect(newRunMain).toHaveClass("text-foreground");
    expect(screen.getByRole("heading", { name: /use an existing cv/i })).toHaveClass(
      "text-foreground",
    );
    expect(screen.getByText(/or upload a new one/i)).toHaveClass(
      "text-muted-foreground",
    );
    expect(screen.getByLabelText(/cv name/i)).toHaveClass("text-foreground");
  });

  it("test_newRun_noCvs_viewport375_uploadFormReachableLegibleColours", async () => {
    setViewportWidth(375);
    signedIn();
    vi.mocked(listCvs).mockResolvedValue([]);

    renderAppAt("/runs/new");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /start a new analysis run/i }),
      ).toBeInTheDocument(),
    );

    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(375);
    expect(
      screen.queryByRole("heading", { name: /use an existing cv/i }),
    ).not.toBeInTheDocument();

    const uploadForm = screen.getByLabelText(/cv name/i).closest("form");
    expect(uploadForm).not.toBeNull();
    expect(uploadForm).not.toHaveClass("cv-upload-form");

    expect(screen.getByLabelText(/cv name/i)).toBeVisible();
    expect(screen.getByLabelText(/pdf file/i)).toBeVisible();
    expect(screen.getByRole("button", { name: /upload cv/i })).toBeVisible();
    expect(screen.getByLabelText(/cv name/i)).toHaveClass(
      "border-input",
      "bg-background",
      "text-foreground",
    );

    document.documentElement.classList.add("dark");

    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(375);
    expect(screen.getByLabelText(/cv name/i)).toHaveClass("text-foreground");
  });

  it("test_newRun_withCvs_existingListNotLegacyClasses", async () => {
    signedIn();
    mockNewRunContent();

    renderAppAt("/runs/new");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /use an existing cv/i })).toBeInTheDocument(),
    );

    const existingSection = screen
      .getByRole("heading", { name: /use an existing cv/i })
      .closest("div");
    expect(existingSection).not.toBeNull();
    expect(existingSection).not.toHaveClass("existing-cvs");

    expect(screen.getByText(/or upload a new one/i)).not.toHaveClass("divider");
    expect(screen.getByText(/or upload a new one/i)).toHaveClass("text-muted-foreground");

    const useButton = screen.getByRole("button", { name: /use react cv/i });
    expect(useButton).toHaveClass("inline-flex");
    expect(useButton).not.toHaveClass("primary-action");
  });

  it("test_newRun_titlesStep_viewport375_suggestionsReachableNotLegacyClasses", async () => {
    setViewportWidth(375);
    signedIn();
    mockNewRunContent();
    vi.mocked(suggestTitles).mockResolvedValue({
      titles: [{ title: "Frontend Developer", rationale: "React experience" }],
    });

    renderAppAt("/runs/new");

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /use react cv/i })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /use react cv/i }));

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /suggested job titles/i }),
      ).toBeInTheDocument(),
    );

    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(375);

    const wizardCv = screen.getByText(/using cv:/i).closest("p");
    expect(wizardCv).not.toBeNull();
    expect(wizardCv).not.toHaveClass("wizard-cv");
    expect(wizardCv).toHaveClass("text-muted-foreground");

    const suggestionsSection = screen
      .getByRole("heading", { name: /suggested job titles/i })
      .closest("section");
    expect(suggestionsSection).not.toBeNull();
    expect(suggestionsSection).not.toHaveClass("title-suggestions");

    expect(screen.getByText("Frontend Developer")).toBeVisible();
    expect(
      screen.getByRole("button", { name: /use frontend developer/i }),
    ).toBeVisible();
    expect(screen.getByLabelText(/or enter your own role/i)).toBeVisible();
  });

  it("test_newRun_searchStep_viewport375_jobFormReachableNotLegacyClasses", async () => {
    setViewportWidth(375);
    signedIn();
    mockNewRunContent();
    vi.mocked(suggestTitles).mockResolvedValue({
      titles: [{ title: "Frontend Developer", rationale: "React experience" }],
    });
    vi.mocked(getRunQuota).mockResolvedValue({
      remaining: 2,
      concurrent_blocked: false,
    });

    renderAppAt("/runs/new");

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /use react cv/i })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /use react cv/i }));

    await waitFor(() =>
      expect(screen.getByText("Frontend Developer")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /use frontend developer/i }));

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /search for jobs/i })).toBeInTheDocument(),
    );

    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(375);

    const searchForm = screen.getByRole("heading", { name: /search for jobs/i }).closest("form");
    expect(searchForm).not.toBeNull();
    expect(searchForm).not.toHaveClass("job-search-form");

    expect(screen.getByLabelText(/role or keywords/i)).toBeVisible();
    expect(screen.getByLabelText(/location/i)).toBeVisible();
    expect(screen.getByRole("button", { name: /start analysis run/i })).toBeVisible();

    expect(screen.getByLabelText(/role or keywords/i)).toHaveClass(
      "border-input",
      "bg-background",
      "text-foreground",
    );
  });
});
