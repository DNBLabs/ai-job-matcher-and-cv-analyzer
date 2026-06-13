import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, searchAdminUsers, setUserUnlimited } from "./client";

const API_BASE = "http://localhost:8000";

function fakeResponse(status: number, body?: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

const FIXTURE_USER = {
  id: "u-1",
  email: "alice@example.com",
  is_admin: false,
  is_unlimited: false,
  created_at: "2026-06-01T00:00:00Z",
};

describe("admin api client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  describe("searchAdminUsers", () => {
    it("GETs /admin/users with an encoded email query and credentials", async () => {
      vi.mocked(fetch).mockResolvedValue(fakeResponse(200, [FIXTURE_USER]));

      await expect(searchAdminUsers("ali ce")).resolves.toEqual([FIXTURE_USER]);
      expect(fetch).toHaveBeenCalledWith(
        `${API_BASE}/admin/users?email=ali+ce`,
        expect.objectContaining({ credentials: "include" }),
      );
    });

    it("throws ApiError when the caller is not an admin (404)", async () => {
      vi.mocked(fetch).mockResolvedValue(fakeResponse(404));
      await expect(searchAdminUsers("x")).rejects.toBeInstanceOf(ApiError);
    });
  });

  describe("setUserUnlimited", () => {
    it("PATCHes /admin/users/{id} with the is_unlimited flag", async () => {
      const updated = { ...FIXTURE_USER, is_unlimited: true };
      vi.mocked(fetch).mockResolvedValue(fakeResponse(200, updated));

      await expect(setUserUnlimited("u-1", true)).resolves.toEqual(updated);
      expect(fetch).toHaveBeenCalledWith(
        `${API_BASE}/admin/users/u-1`,
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ is_unlimited: true }),
        }),
      );
    });

    it("throws ApiError on failure", async () => {
      vi.mocked(fetch).mockResolvedValue(fakeResponse(404));
      await expect(setUserUnlimited("u-1", true)).rejects.toBeInstanceOf(ApiError);
    });
  });
});
