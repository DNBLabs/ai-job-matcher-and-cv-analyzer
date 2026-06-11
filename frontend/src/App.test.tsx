import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import * as client from "../src/api/client";

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

    renderAppAt("/dashboard");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /dashboard/i })).toBeInTheDocument(),
    );
    expect(screen.getByText(/alex@example.com/)).toBeInTheDocument();
  });

  it("routes the index path to the dashboard (login when anonymous)", async () => {
    vi.mocked(client.getCurrentUser).mockResolvedValue(null);

    renderAppAt("/");

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument(),
    );
  });
});
