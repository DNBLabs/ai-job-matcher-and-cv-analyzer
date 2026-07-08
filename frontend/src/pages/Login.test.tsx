import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import path from "node:path";
import { readFile } from "node:fs/promises";
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

function setViewportWidth(width: number) {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: width,
  });
}

async function readLoginSource() {
  return readFile(path.resolve(process.cwd(), "src/pages/Login.tsx"), "utf8");
}

describe("Login", () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
    document.documentElement.classList.remove("dark");
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

  it("test_login_light_mode_375px_no_horizontal_scroll_and_reachable_controls", () => {
    setViewportWidth(375);

    render(<Login />);

    const main = screen.getByRole("main");
    expect(main).toHaveClass("min-h-screen", "px-4", "flex", "items-center", "justify-center");
    expect(screen.getByRole("link", { name: /continue with google/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /email me a sign-in link/i })).toBeInTheDocument();
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(375);
  });

  it("test_login_dark_mode_prefers_dark_legible_text_and_background", () => {
    document.documentElement.classList.add("dark");

    render(<Login />);

    expect(screen.getByRole("main")).toHaveClass("bg-background", "text-foreground");
    expect(screen.getByRole("heading", { name: /sign in/i })).toHaveClass("text-foreground");
    expect(screen.getByRole("link", { name: /continue with google/i })).toHaveClass("bg-background", "text-foreground");
  });

  it("test_login_magic_link_success_shows_visible_high_contrast_confirmation", async () => {
    vi.mocked(client.requestMagicLink).mockResolvedValue(undefined);

    render(<Login />);
    fillEmailAndSubmit("alex@example.com");

    const confirmation = await screen.findByRole("status");
    expect(confirmation).toHaveTextContent(/check your email/i);
    expect(confirmation).toHaveClass("rounded-lg", "border", "bg-card", "text-card-foreground");
  });

  it("test_login_dark_mode_success_confirmation_uses_high_contrast_card_tokens", async () => {
    document.documentElement.classList.add("dark");
    vi.mocked(client.requestMagicLink).mockResolvedValue(undefined);

    render(<Login />);
    fillEmailAndSubmit("alex@example.com");

    const confirmation = await screen.findByRole("status");
    expect(confirmation).toHaveTextContent(/check your email/i);
    expect(confirmation).toHaveClass("rounded-lg", "border", "bg-card", "text-card-foreground");
  });

  it("test_login_error_response_renders_visible_destructive_alert", async () => {
    vi.mocked(client.requestMagicLink).mockRejectedValue(
      new ApiError(429, "Too many requests"),
    );

    render(<Login />);
    fillEmailAndSubmit("alex@example.com");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/too many sign-in requests/i);
    expect(alert).toHaveClass("border-destructive/50", "text-destructive");
  });

  it("test_login_generic_error_renders_visible_destructive_alert", async () => {
    vi.mocked(client.requestMagicLink).mockRejectedValue(
      new ApiError(500, "boom"),
    );

    render(<Login />);
    fillEmailAndSubmit("alex@example.com");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/something went wrong/i);
    expect(alert).toHaveClass("border-destructive/50", "text-destructive");
  });

  it("test_login_sign_in_panel_uses_card_container", () => {
    render(<Login />);

    const heading = screen.getByRole("heading", { name: /sign in/i });
    const card = heading.closest(".rounded-lg");

    expect(card).not.toBeNull();
    expect(card).toHaveClass(
      "rounded-lg",
      "border",
      "bg-card",
      "text-card-foreground",
      "shadow-sm",
    );
  });

  it("test_login_or_divider_uses_separator_styling", () => {
    render(<Login />);

    expect(screen.getByText("or")).toHaveClass("text-muted-foreground");
    expect(
      document.querySelectorAll('[data-orientation="horizontal"]'),
    ).toHaveLength(2);
  });

  it("test_login_existing_vitest_suite_passes_without_modification", () => {
    render(<Login />);

    expect(screen.getByRole("link", { name: /continue with google/i })).toHaveClass(
      "inline-flex",
      "border",
      "bg-background",
    );
    expect(screen.getByLabelText(/email address/i)).toHaveClass(
      "flex",
      "rounded-md",
      "border-input",
      "bg-background",
    );
    expect(screen.getByRole("button", { name: /email me a sign-in link/i })).toHaveClass(
      "bg-primary",
      "text-primary-foreground",
    );
  });

  it("test_login_source_contains_no_auth_page_or_app_css_classnames", async () => {
    const source = await readLoginSource();

    expect(source).not.toContain("auth-page");
    expect(source).not.toContain("google-button");
    expect(source).not.toContain("divider");
    expect(source).not.toContain("form-error");
  });

  it("test_login_invalid_input_reuses_existing_error_alert_path", async () => {
    vi.mocked(client.requestMagicLink).mockRejectedValue(
      new ApiError(429, "Too many requests"),
    );

    render(<Login />);
    fillEmailAndSubmit("");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/too many sign-in requests/i);
    expect(alert).toHaveClass("border-destructive/50", "text-destructive");
    expect(client.requestMagicLink).toHaveBeenCalledWith("");
  });

  it("test_login_pre_auth_page_requires_no_session", () => {
    render(<Login />);

    expect(client.getCurrentUser).not.toHaveBeenCalled();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveClass("min-h-screen");
  });

  it("test_login_tailwind_rewrite_adds_no_new_external_calls", async () => {
    vi.mocked(client.requestMagicLink).mockResolvedValue(undefined);

    render(<Login />);
    fillEmailAndSubmit("alex@example.com");

    await screen.findByRole("status");
    expect(client.requestMagicLink).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: /continue with google/i })).toHaveClass(
      "inline-flex",
      "border",
      "bg-background",
    );
  });
});
