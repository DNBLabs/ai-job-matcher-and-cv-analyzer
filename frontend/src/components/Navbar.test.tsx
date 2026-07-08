import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import * as client from "../api/client";

vi.mock("../api/client");

function mockSignedInUser(
  user: { email: string; is_admin: boolean } = {
    email: "alex@example.com",
    is_admin: false,
  },
) {
  vi.mocked(client.getCurrentUser).mockResolvedValue({
    id: "u-1",
    email: user.email,
    is_admin: user.is_admin,
  });
  vi.mocked(client.logout).mockResolvedValue(undefined);
  vi.mocked(client.pingHealth).mockResolvedValue(true);
}

function mockDashboardData() {
  vi.mocked(client.listCvs).mockResolvedValue([]);
  vi.mocked(client.listRuns).mockResolvedValue([]);
  vi.mocked(client.getRunQuota).mockResolvedValue({
    remaining: 3,
    concurrent_blocked: false,
  });
}

function getAppNavbar() {
  const brandLink = screen.getByRole("link", { name: /get me a job/i });
  const nav = brandLink.closest("nav");
  expect(nav).not.toBeNull();
  return nav as HTMLElement;
}

function renderAppAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("Navbar", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      configurable: true,
      value: 1024,
    });
  });

  it("test_navbar_authenticatedDashboard_rendersTopNavWithBrandDashboardAndNewRunLinks", async () => {
    mockSignedInUser();
    mockDashboardData();

    renderAppAt("/dashboard");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /dashboard/i })).toBeInTheDocument(),
    );

    const nav = getAppNavbar();
    expect(nav).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /get me a job/i }),
    ).toHaveAttribute("href", "/dashboard");
    expect(within(nav).getByRole("link", { name: /^dashboard$/i })).toHaveAttribute(
      "href",
      "/dashboard",
    );
    expect(within(nav).getByRole("link", { name: /new run/i })).toHaveAttribute(
      "href",
      "/runs/new",
    );
  });

  it("test_navbar_authenticatedNewRun_rendersSharedNavbarShell", async () => {
    mockSignedInUser();
    vi.mocked(client.listCvs).mockResolvedValue([]);
    vi.mocked(client.logout).mockResolvedValue(undefined);
    vi.mocked(client.pingHealth).mockResolvedValue(true);

    renderAppAt("/runs/new");

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /start a new analysis run/i }),
      ).toBeInTheDocument(),
    );

    const nav = getAppNavbar();
    expect(nav).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /^dashboard$/i })).toHaveAttribute(
      "href",
      "/dashboard",
    );
    expect(within(nav).getByRole("link", { name: /new run/i })).toHaveAttribute(
      "href",
      "/runs/new",
    );
  });

  it("test_navbar_nonAdmin_hidesAdminLink", async () => {
    mockSignedInUser({ email: "alex@example.com", is_admin: false });
    mockDashboardData();

    renderAppAt("/dashboard");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /dashboard/i })).toBeInTheDocument(),
    );

    const nav = getAppNavbar();
    expect(
      within(nav).queryByRole("link", { name: /^admin$/i }),
    ).not.toBeInTheDocument();
  });

  it("test_navbar_admin_rendersAdminLinkToAdminRoute", async () => {
    mockSignedInUser({ email: "operator@example.com", is_admin: true });
    mockDashboardData();

    renderAppAt("/dashboard");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /dashboard/i })).toBeInTheDocument(),
    );

    const nav = getAppNavbar();
    expect(within(nav).getByRole("link", { name: /^admin$/i })).toHaveAttribute(
      "href",
      "/admin",
    );
  });

  it("test_navbar_authenticatedUser_openDropdown_showsEmailAndSignOut", async () => {
    mockSignedInUser({ email: "alex@example.com", is_admin: false });
    mockDashboardData();

    renderAppAt("/dashboard");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /dashboard/i })).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: /alex@example.com/i }));

    await waitFor(() => {
      expect(screen.getByRole("menuitem", { name: /sign out/i })).toBeInTheDocument();
    });
    expect(screen.getAllByText("alex@example.com").length).toBeGreaterThanOrEqual(1);
  });

  it("test_navbar_authenticatedUser_keyboardOpensDropdown_preservesMenuAria", async () => {
    mockSignedInUser({ email: "alex@example.com", is_admin: false });
    mockDashboardData();

    renderAppAt("/dashboard");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /dashboard/i })).toBeInTheDocument(),
    );

    const trigger = screen.getByRole("button", { name: /alex@example.com/i });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    fireEvent.keyDown(trigger, { key: "Enter" });

    await waitFor(() => {
      expect(screen.getByRole("menuitem", { name: /sign out/i })).toBeInTheDocument();
    });
    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });

  it("test_navbar_authenticatedUser_clickSignOut_callsSignOutAndRedirectsToLogin", async () => {
    mockSignedInUser();
    mockDashboardData();

    renderAppAt("/dashboard");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /dashboard/i })).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: /alex@example.com/i }));
    await waitFor(() =>
      expect(screen.getByRole("menuitem", { name: /sign out/i })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: /sign out/i }));

    await waitFor(() => {
      expect(client.logout).toHaveBeenCalledTimes(1);
      expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole("heading", { name: /dashboard/i })).not.toBeInTheDocument();
  });

  it("test_navbar_viewport375_collapsesNavWithoutHorizontalScrollAndKeepsItemsAccessible", async () => {
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      configurable: true,
      value: 375,
    });
    Object.defineProperty(document.documentElement, "clientWidth", {
      writable: true,
      configurable: true,
      value: 375,
    });

    mockSignedInUser();
    mockDashboardData();

    renderAppAt("/dashboard");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /dashboard/i })).toBeInTheDocument(),
    );

    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(375);

    fireEvent.click(screen.getByRole("button", { name: /alex@example.com/i }));

    await waitFor(() => {
      expect(screen.getByRole("menuitem", { name: /^dashboard$/i })).toBeInTheDocument();
      expect(screen.getByRole("menuitem", { name: /new run/i })).toBeInTheDocument();
      expect(screen.getByRole("menuitem", { name: /sign out/i })).toBeInTheDocument();
    });
  });

  it("test_navbar_invalidInput_notApplicable_noUserFacingInputFields", async () => {
    mockSignedInUser();
    mockDashboardData();

    renderAppAt("/dashboard");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /dashboard/i })).toBeInTheDocument(),
    );

    const nav = getAppNavbar();
    expect(nav.querySelector("input")).not.toBeInTheDocument();
    expect(nav.querySelector("textarea")).not.toBeInTheDocument();
    expect(nav.querySelector("select")).not.toBeInTheDocument();
  });

  it("test_navbar_downstream_notApplicable_noExternalServiceCalls", async () => {
    mockSignedInUser({ email: "operator@example.com", is_admin: true });

    vi.mocked(client.listCvs).mockClear();
    vi.mocked(client.listRuns).mockClear();
    vi.mocked(client.getRunQuota).mockClear();
    vi.mocked(client.logout).mockClear();

    renderAppAt("/admin");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /^admin$/i })).toBeInTheDocument(),
    );

    getAppNavbar();

    expect(vi.mocked(client.listCvs)).not.toHaveBeenCalled();
    expect(vi.mocked(client.listRuns)).not.toHaveBeenCalled();
    expect(vi.mocked(client.getRunQuota)).not.toHaveBeenCalled();
    expect(vi.mocked(client.logout)).not.toHaveBeenCalled();
  });
});
