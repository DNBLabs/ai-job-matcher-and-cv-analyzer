import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { AuthProvider } from "./AuthProvider";
import { ProtectedRoute } from "./ProtectedRoute";
import * as client from "../api/client";

vi.mock("../api/client");

function renderAt(initialPath: string) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/login" element={<div>Login page</div>} />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <div>Secret dashboard</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe("ProtectedRoute", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the protected content for an authenticated user", async () => {
    vi.mocked(client.getCurrentUser).mockResolvedValue({
      id: "u-1",
      email: "alex@example.com",
      is_admin: false,
    });

    renderAt("/dashboard");

    await waitFor(() =>
      expect(screen.getByText("Secret dashboard")).toBeInTheDocument(),
    );
  });

  it("redirects an anonymous user to the login page", async () => {
    vi.mocked(client.getCurrentUser).mockResolvedValue(null);

    renderAt("/dashboard");

    await waitFor(() =>
      expect(screen.getByText("Login page")).toBeInTheDocument(),
    );
    expect(screen.queryByText("Secret dashboard")).not.toBeInTheDocument();
  });

  it("test_protectedRoute_anonymousUser_redirectsToLogin_unchangedBehavior", async () => {
    vi.mocked(client.getCurrentUser).mockResolvedValue(null);

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument(),
    );
    expect(screen.queryByRole("heading", { name: /dashboard/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /get me a job/i })).not.toBeInTheDocument();

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
    expect(screen.getByRole("link", { name: /get me a job/i })).toBeInTheDocument();
  });

  it("shows a loading state while the session is resolving", () => {
    vi.mocked(client.getCurrentUser).mockReturnValue(new Promise(() => {}));

    renderAt("/dashboard");

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    expect(screen.queryByText("Secret dashboard")).not.toBeInTheDocument();
  });
});
