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

describe("Admin page", () => {
  afterEach(() => {
    vi.restoreAllMocks();
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
});
