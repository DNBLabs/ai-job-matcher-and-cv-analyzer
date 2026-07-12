import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AdminUser } from "../api/client";
import { Admin } from "./Admin";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, searchAdminUsers: vi.fn(), setUserUnlimited: vi.fn() };
});

import { searchAdminUsers, setUserUnlimited } from "../api/client";

const USER: AdminUser = {
  id: "u-1",
  email: "alice@example.com",
  is_admin: false,
  is_unlimited: false,
  created_at: "2026-06-01T00:00:00Z",
};

function renderAdmin() {
  return render(
    <MemoryRouter>
      <Admin />
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

function getAdminContentMain(): HTMLElement {
  const heading = screen.getByRole("heading", { name: /^admin$/i, level: 1 });
  const main = heading.closest("main");
  expect(main).not.toBeNull();
  return main as HTMLElement;
}

describe("Admin page", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.documentElement.classList.remove("dark");
    setViewportWidth(1024);
  });

  it("searches users by email and lists matches", async () => {
    vi.mocked(searchAdminUsers).mockResolvedValue([USER]);
    renderAdmin();

    fireEvent.change(screen.getByLabelText(/search users by email/i), {
      target: { value: "alice" },
    });
    fireEvent.click(screen.getByRole("button", { name: /search/i }));

    expect(await screen.findByText("alice@example.com")).toBeInTheDocument();
    expect(searchAdminUsers).toHaveBeenCalledWith("alice");
  });

  it("shows an empty state when no users match", async () => {
    vi.mocked(searchAdminUsers).mockResolvedValue([]);
    renderAdmin();

    fireEvent.click(screen.getByRole("button", { name: /search/i }));

    expect(await screen.findByText(/no users match/i)).toBeInTheDocument();
  });

  it("toggles unlimited and reflects the updated state", async () => {
    vi.mocked(searchAdminUsers).mockResolvedValue([USER]);
    vi.mocked(setUserUnlimited).mockResolvedValue({ ...USER, is_unlimited: true });
    renderAdmin();

    fireEvent.click(screen.getByRole("button", { name: /search/i }));
    await screen.findByText("alice@example.com");

    fireEvent.click(screen.getByRole("button", { name: /make unlimited/i }));

    await waitFor(() =>
      expect(setUserUnlimited).toHaveBeenCalledWith("u-1", true),
    );
    expect(
      await screen.findByRole("button", { name: /remove unlimited/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Unlimited")).toBeInTheDocument();
  });

  it("surfaces an error when the search fails", async () => {
    vi.mocked(searchAdminUsers).mockRejectedValue(new Error("boom"));
    renderAdmin();

    fireEvent.click(screen.getByRole("button", { name: /search/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not search/i);
  });

  it("test_admin_searchFormAndTable_notLegacyClasses_useShadcnInput", async () => {
    vi.mocked(searchAdminUsers).mockResolvedValue([USER]);
    renderAdmin();

    const searchForm = screen.getByLabelText(/search users by email/i).closest("form");
    expect(searchForm).not.toBeNull();
    expect(searchForm).not.toHaveClass("admin-search");
    expect(searchForm).toHaveClass("flex", "flex-wrap");

    const searchInput = screen.getByLabelText(/search users by email/i);
    expect(searchInput).toHaveClass(
      "border-input",
      "bg-background",
      "text-foreground",
    );

    fireEvent.click(screen.getByRole("button", { name: /search/i }));
    await screen.findByText("alice@example.com");

    const userList = screen.getByRole("list");
    expect(userList).not.toHaveClass("admin-user-list");

    const userRow = screen.getByText("alice@example.com").closest("li");
    expect(userRow).not.toBeNull();
    expect(userRow).not.toHaveClass("admin-user-row");

    const header = screen.getByRole("heading", { name: /^admin$/i }).closest("header");
    expect(header).not.toBeNull();
    expect(header).not.toHaveClass("admin-header");
  });

  it("test_admin_emptyState_notLegacyClasses_legibleMutedForeground", async () => {
    vi.mocked(searchAdminUsers).mockResolvedValue([]);
    renderAdmin();

    fireEvent.click(screen.getByRole("button", { name: /search/i }));

    const emptyMessage = await screen.findByText(/no users match/i);
    expect(emptyMessage).toBeVisible();
    expect(emptyMessage).not.toHaveClass("empty-state");
    expect(emptyMessage).toHaveClass("text-muted-foreground");
  });

  it("test_admin_searchError_usesAlertNotLegacyAdminError", async () => {
    vi.mocked(searchAdminUsers).mockRejectedValue(new Error("boom"));
    renderAdmin();

    fireEvent.click(screen.getByRole("button", { name: /search/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/could not search/i);
    expect(alert).not.toHaveClass("admin-error");
    expect(alert.tagName).toBe("DIV");
    expect(alert).toHaveClass("rounded-lg", "border");
  });

  it("test_admin_viewport375_lightAndDark_noHorizontalScrollReachableLegibleColours", async () => {
    setViewportWidth(375);
    vi.mocked(searchAdminUsers).mockResolvedValue([
      {
        id: "u-1",
        email: "alice@example.com",
        is_admin: false,
        is_unlimited: false,
        created_at: "2026-06-01T00:00:00Z",
      },
    ]);

    renderAdmin();

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /^admin$/i })).toBeInTheDocument(),
    );

    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(375);

    const adminMain = getAdminContentMain();
    expect(adminMain).not.toHaveClass("admin-page");
    expect(adminMain).toHaveClass(
      "mx-auto",
      "max-w-3xl",
      "px-4",
      "text-foreground",
    );

    const searchInput = screen.getByLabelText(/search users by email/i);
    expect(searchInput).toBeVisible();
    expect(screen.getByRole("button", { name: /search/i })).toBeVisible();
    expect(screen.getByRole("link", { name: /back to dashboard/i })).toBeVisible();

    expect(screen.getByRole("heading", { name: /^admin$/i })).toHaveClass(
      "text-foreground",
    );
    expect(searchInput).toHaveClass("rounded-md", "border-input");

    fireEvent.change(searchInput, { target: { value: "alice" } });
    fireEvent.click(screen.getByRole("button", { name: /search/i }));

    await waitFor(() =>
      expect(screen.getByText("alice@example.com")).toBeInTheDocument(),
    );

    expect(screen.getByRole("button", { name: /make unlimited/i })).toBeVisible();

    document.documentElement.classList.add("dark");

    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(375);

    expect(adminMain).toHaveClass("text-foreground");
    expect(screen.getByRole("heading", { name: /^admin$/i })).toHaveClass(
      "text-foreground",
    );
    expect(searchInput).toHaveClass("rounded-md", "border-input");
  });
});
