import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AdminRoute } from "./AdminRoute";
import { AuthProvider } from "./AuthProvider";
import * as client from "../api/client";

vi.mock("../api/client");

function renderAt(initialPath: string) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/login" element={<div>Login page</div>} />
          <Route path="/dashboard" element={<div>Dashboard page</div>} />
          <Route
            path="/admin"
            element={
              <AdminRoute>
                <div>Operator console</div>
              </AdminRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe("AdminRoute", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the console for an admin", async () => {
    vi.mocked(client.getCurrentUser).mockResolvedValue({
      id: "u-1",
      email: "operator@example.com",
      is_admin: true,
    });

    renderAt("/admin");

    await waitFor(() =>
      expect(screen.getByText("Operator console")).toBeInTheDocument(),
    );
  });

  it("redirects an authenticated non-admin to the dashboard", async () => {
    vi.mocked(client.getCurrentUser).mockResolvedValue({
      id: "u-2",
      email: "seeker@example.com",
      is_admin: false,
    });

    renderAt("/admin");

    await waitFor(() =>
      expect(screen.getByText("Dashboard page")).toBeInTheDocument(),
    );
    expect(screen.queryByText("Operator console")).not.toBeInTheDocument();
  });

  it("redirects an anonymous user to login", async () => {
    vi.mocked(client.getCurrentUser).mockResolvedValue(null);

    renderAt("/admin");

    await waitFor(() =>
      expect(screen.getByText("Login page")).toBeInTheDocument(),
    );
  });
});
