import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Login } from "./Login";
import { ApiError } from "../api/client";
import * as client from "../api/client";

// Keep the real ApiError class (so `error.status` survives) and mock only the
// network functions.
vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof client>();
  return {
    ...actual,
    getCurrentUser: vi.fn(),
    requestMagicLink: vi.fn(),
    logout: vi.fn(),
    googleLoginUrl: vi.fn(() => "http://localhost:8000/auth/google/login"),
  };
});

function fillEmailAndSubmit(email: string) {
  fireEvent.change(screen.getByLabelText(/email/i), {
    target: { value: email },
  });
  fireEvent.click(screen.getByRole("button", { name: /sign-in link|send/i }));
}

describe("Login", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("links the Google button to the backend OAuth entrypoint", () => {
    vi.mocked(client.googleLoginUrl).mockReturnValue(
      "http://localhost:8000/auth/google/login",
    );

    render(<Login />);

    const link = screen.getByRole("link", { name: /google/i });
    expect(link).toHaveAttribute(
      "href",
      "http://localhost:8000/auth/google/login",
    );
  });

  it("shows a check-email confirmation after submitting the magic-link form", async () => {
    vi.mocked(client.requestMagicLink).mockResolvedValue(undefined);

    render(<Login />);
    fillEmailAndSubmit("alex@example.com");

    await waitFor(() =>
      expect(screen.getByText(/check your email/i)).toBeInTheDocument(),
    );
    expect(client.requestMagicLink).toHaveBeenCalledWith("alex@example.com");
    expect(screen.getByText(/alex@example.com/)).toBeInTheDocument();
  });

  it("surfaces a rate-limit message on 429", async () => {
    vi.mocked(client.requestMagicLink).mockRejectedValue(
      new ApiError(429, "Too many requests"),
    );

    render(<Login />);
    fillEmailAndSubmit("alex@example.com");

    await waitFor(() =>
      expect(screen.getByText(/too many/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/check your email/i)).not.toBeInTheDocument();
  });

  it("shows a generic error when the request fails", async () => {
    vi.mocked(client.requestMagicLink).mockRejectedValue(
      new ApiError(500, "boom"),
    );

    render(<Login />);
    fillEmailAndSubmit("alex@example.com");

    await waitFor(() =>
      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument(),
    );
  });
});
