import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  createRun,
  deleteCv,
  getRun,
  getRunQuota,
  getRunResults,
  listCvs,
  listRuns,
  pingHealth,
  suggestTitles,
  uploadCv,
} from "./client";

const API_BASE = "http://localhost:8000";

function fakeResponse(status: number, body?: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

describe("api client (Task 21 surface)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  describe("listCvs", () => {
    it("GETs the CV list with credentials", async () => {
      const cvs = [{ id: "cv-1", name: "General", uploaded_at: "2026-06-01T00:00:00Z" }];
      vi.mocked(fetch).mockResolvedValue(fakeResponse(200, cvs));

      await expect(listCvs()).resolves.toEqual(cvs);
      expect(fetch).toHaveBeenCalledWith(
        `${API_BASE}/cvs`,
        expect.objectContaining({ credentials: "include" }),
      );
    });

    it("throws ApiError on failure", async () => {
      vi.mocked(fetch).mockResolvedValue(fakeResponse(500));
      await expect(listCvs()).rejects.toBeInstanceOf(ApiError);
    });
  });

  describe("uploadCv", () => {
    it("POSTs multipart form data without a JSON content-type", async () => {
      const cv = { id: "cv-9", name: "React", uploaded_at: "2026-06-02T00:00:00Z" };
      vi.mocked(fetch).mockResolvedValue(fakeResponse(201, cv));
      const file = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "cv.pdf", {
        type: "application/pdf",
      });

      await expect(uploadCv("React", file)).resolves.toEqual(cv);

      const [, init] = vi.mocked(fetch).mock.calls[0];
      expect(init).toMatchObject({ method: "POST", credentials: "include" });
      expect(init?.body).toBeInstanceOf(FormData);
      // The browser must set the multipart boundary itself.
      const headers = (init?.headers ?? {}) as Record<string, string>;
      expect(headers["Content-Type"]).toBeUndefined();
    });

    it("throws ApiError on a rejected upload (400)", async () => {
      vi.mocked(fetch).mockResolvedValue(fakeResponse(400, { detail: "not a pdf" }));
      const file = new File(["x"], "cv.pdf", { type: "application/pdf" });
      await expect(uploadCv("X", file)).rejects.toMatchObject({ status: 400 });
    });
  });

  describe("deleteCv", () => {
    it("DELETEs the CV by id", async () => {
      vi.mocked(fetch).mockResolvedValue(fakeResponse(204));
      await expect(deleteCv("cv-1")).resolves.toBeUndefined();
      expect(fetch).toHaveBeenCalledWith(
        `${API_BASE}/cvs/cv-1`,
        expect.objectContaining({ method: "DELETE", credentials: "include" }),
      );
    });
  });

  describe("suggestTitles", () => {
    it("POSTs to the suggest-titles endpoint and returns titles", async () => {
      const body = { titles: [{ title: "Frontend Developer", rationale: "React" }] };
      vi.mocked(fetch).mockResolvedValue(fakeResponse(200, body));

      await expect(suggestTitles("cv-1")).resolves.toEqual(body);
      expect(fetch).toHaveBeenCalledWith(
        `${API_BASE}/cvs/cv-1/suggest-titles`,
        expect.objectContaining({ method: "POST", credentials: "include" }),
      );
    });
  });

  describe("runs", () => {
    it("listRuns GETs /runs", async () => {
      vi.mocked(fetch).mockResolvedValue(fakeResponse(200, []));
      await expect(listRuns()).resolves.toEqual([]);
      expect(fetch).toHaveBeenCalledWith(
        `${API_BASE}/runs`,
        expect.objectContaining({ credentials: "include" }),
      );
    });

    it("getRun GETs /runs/{id}", async () => {
      const run = { id: "r-1", status: "queued" };
      vi.mocked(fetch).mockResolvedValue(fakeResponse(200, run));
      await expect(getRun("r-1")).resolves.toEqual(run);
      expect(fetch).toHaveBeenCalledWith(
        `${API_BASE}/runs/r-1`,
        expect.objectContaining({ credentials: "include" }),
      );
    });

    it("createRun POSTs cv_id and job_search", async () => {
      const run = { id: "r-2", status: "queued" };
      vi.mocked(fetch).mockResolvedValue(fakeResponse(201, run));
      const jobSearch = { role: "Engineer", location: "London", remote: false };

      await expect(createRun("cv-1", jobSearch)).resolves.toEqual(run);
      expect(fetch).toHaveBeenCalledWith(
        `${API_BASE}/runs`,
        expect.objectContaining({
          method: "POST",
          credentials: "include",
          body: JSON.stringify({ cv_id: "cv-1", job_search: jobSearch }),
        }),
      );
    });

    it("createRun throws ApiError carrying the status on quota (429)", async () => {
      vi.mocked(fetch).mockResolvedValue(fakeResponse(429, { detail: "quota" }));
      await expect(
        createRun("cv-1", { role: "X", location: "London", remote: false }),
      ).rejects.toMatchObject({ status: 429 });
    });

    it("getRunResults GETs /runs/{id}/results", async () => {
      vi.mocked(fetch).mockResolvedValue(fakeResponse(200, []));
      await expect(getRunResults("r-1")).resolves.toEqual([]);
      expect(fetch).toHaveBeenCalledWith(
        `${API_BASE}/runs/r-1/results`,
        expect.objectContaining({ credentials: "include" }),
      );
    });

    it("getRunQuota GETs /runs/quota", async () => {
      const quota = { remaining: 2, concurrent_blocked: false };
      vi.mocked(fetch).mockResolvedValue(fakeResponse(200, quota));
      await expect(getRunQuota()).resolves.toEqual(quota);
      expect(fetch).toHaveBeenCalledWith(
        `${API_BASE}/runs/quota`,
        expect.objectContaining({ credentials: "include" }),
      );
    });
  });

  describe("pingHealth", () => {
    it("resolves true when the API responds 200", async () => {
      vi.mocked(fetch).mockResolvedValue(fakeResponse(200, { status: "ok" }));
      await expect(pingHealth()).resolves.toBe(true);
    });

    it("resolves false when fetch rejects (API cold/asleep)", async () => {
      vi.mocked(fetch).mockRejectedValue(new Error("network"));
      await expect(pingHealth()).resolves.toBe(false);
    });
  });
});
