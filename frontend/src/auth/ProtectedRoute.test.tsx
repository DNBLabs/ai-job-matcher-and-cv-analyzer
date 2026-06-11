import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
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

  it("shows a loading state while the session is resolving", () => {
    vi.mocked(client.getCurrentUser).mockReturnValue(new Promise(() => {}));

    renderAt("/dashboard");

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    expect(screen.queryByText("Secret dashboard")).not.toBeInTheDocument();
  });
});
