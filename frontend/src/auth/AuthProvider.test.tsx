import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./AuthProvider";
import { useAuth } from "./useAuth";
import * as client from "../api/client";

vi.mock("../api/client");

function Probe() {
  const { status, user, signOut } = useAuth();
  return (
    <div>
      <span>
        status:{status} email:{user?.email ?? "none"}
      </span>
      <button onClick={() => void signOut()}>sign out</button>
    </div>
  );
}

describe("AuthProvider", () => {
  beforeEach(() => {
    vi.mocked(client.logout).mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("resolves to authenticated with the user identity", async () => {
    vi.mocked(client.getCurrentUser).mockResolvedValue({
      id: "u-1",
      email: "alex@example.com",
      is_admin: false,
    });

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() =>
      expect(screen.getByText(/status:authenticated/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/email:alex@example.com/)).toBeInTheDocument();
  });

  it("resolves to anonymous when there is no session", async () => {
    vi.mocked(client.getCurrentUser).mockResolvedValue(null);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() =>
      expect(screen.getByText(/status:anonymous/)).toBeInTheDocument(),
    );
  });

  it("signs out and returns to anonymous", async () => {
    vi.mocked(client.getCurrentUser).mockResolvedValue({
      id: "u-1",
      email: "alex@example.com",
      is_admin: false,
    });

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() =>
      expect(screen.getByText(/status:authenticated/)).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() =>
      expect(screen.getByText(/status:anonymous/)).toBeInTheDocument(),
    );
    expect(client.logout).toHaveBeenCalledOnce();
  });

  it("throws when useAuth is used outside the provider", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow(/useAuth/);
  });
});
