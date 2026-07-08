import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import * as client from "./api/client";

vi.mock("./api/client");

function renderAppAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("App routing", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("redirects an unauthenticated visitor from /dashboard to sign-in", async () => {
    vi.mocked(client.getCurrentUser).mockResolvedValue(null);

    renderAppAt("/dashboard");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument(),
    );
  });

  it("renders the dashboard for an authenticated user", async () => {
    vi.mocked(client.getCurrentUser).mockResolvedValue({
      id: "u-1",
      email: "alex@example.com",
      is_admin: false,
    });
    vi.mocked(client.pingHealth).mockResolvedValue(true);
    vi.mocked(client.listCvs).mockResolvedValue([]);
    vi.mocked(client.listRuns).mockResolvedValue([]);
    // Dashboard also loads run quota; without this the auto-mock resolves
    // undefined and `quota.concurrent_blocked` throws mid-render (flaky in CI).
    vi.mocked(client.getRunQuota).mockResolvedValue({ remaining: 3, concurrent_blocked: false });

    renderAppAt("/dashboard");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /dashboard/i })).toBeInTheDocument(),
    );
    expect(screen.getByText(/signed in as alex@example.com/i)).toBeInTheDocument();
  });

  it("routes the index path to the dashboard (login when anonymous)", async () => {
    vi.mocked(client.getCurrentUser).mockResolvedValue(null);

    renderAppAt("/");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument(),
    );
  });

  it("test_app_loginRoute_hidesNavbar", async () => {
    vi.mocked(client.getCurrentUser).mockResolvedValue(null);

    renderAppAt("/login");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument(),
    );
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /get me a job/i }),
    ).not.toBeInTheDocument();

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

    const { unmount } = renderAppAt("/dashboard");
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /dashboard/i })).toBeInTheDocument(),
    );
    expect(screen.getByRole("link", { name: /get me a job/i })).toBeInTheDocument();
    unmount();
  });
});