import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  getCurrentUser,
  googleLoginUrl,
  logout,
  requestMagicLink,
} from "./client";

const API_BASE = "http://localhost:8000";

function fakeResponse(status: number, body?: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

describe("api client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  describe("getCurrentUser", () => {
    it("returns the account identity on 200", async () => {
      const user = { id: "u-1", email: "alex@example.com", is_admin: false };
      vi.mocked(fetch).mockResolvedValue(fakeResponse(200, user));

      await expect(getCurrentUser()).resolves.toEqual(user);
    });

    it("sends cookies with the request", async () => {
      vi.mocked(fetch).mockResolvedValue(fakeResponse(200, { id: "u", email: "e", is_admin: false }));

      await getCurrentUser();

      expect(fetch).toHaveBeenCalledWith(
        `${API_BASE}/auth/me`,
        expect.objectContaining({ credentials: "include" }),
      );
    });

    it("returns null when unauthenticated (401)", async () => {
      vi.mocked(fetch).mockResolvedValue(fakeResponse(401, { detail: "Authentication required" }));

      await expect(getCurrentUser()).resolves.toBeNull();
    });

    it("throws ApiError on server failure", async () => {
      vi.mocked(fetch).mockResolvedValue(fakeResponse(500));

      await expect(getCurrentUser()).rejects.toBeInstanceOf(ApiError);
    });
  });

  describe("requestMagicLink", () => {
    it("POSTs the email and resolves on success", async () => {
      vi.mocked(fetch).mockResolvedValue(fakeResponse(200, { detail: "sent" }));

      await expect(requestMagicLink("alex@example.com")).resolves.toBeUndefined();

      expect(fetch).toHaveBeenCalledWith(
        `${API_BASE}/auth/magic-link`,
        expect.objectContaining({
          method: "POST",
          credentials: "include",
          body: JSON.stringify({ email: "alex@example.com" }),
        }),
      );
    });

    it("throws ApiError with the status when rate limited (429)", async () => {
      vi.mocked(fetch).mockResolvedValue(fakeResponse(429, { detail: "Too many requests" }));

      await expect(requestMagicLink("alex@example.com")).rejects.toMatchObject({
        status: 429,
      });
    });
  });

  describe("logout", () => {
    it("POSTs to the logout endpoint with credentials", async () => {
      vi.mocked(fetch).mockResolvedValue(fakeResponse(200, { detail: "Signed out" }));

      await logout();

      expect(fetch).toHaveBeenCalledWith(
        `${API_BASE}/auth/logout`,
        expect.objectContaining({ method: "POST", credentials: "include" }),
      );
    });
  });

  describe("googleLoginUrl", () => {
    it("points at the backend OAuth entrypoint", () => {
      expect(googleLoginUrl()).toBe(`${API_BASE}/auth/google/login`);
    });
  });
});
