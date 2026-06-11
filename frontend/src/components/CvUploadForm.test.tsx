import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CvUploadForm } from "./CvUploadForm";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, uploadCv: vi.fn() };
});

import { ApiError, uploadCv } from "../api/client";

function selectFile() {
  const file = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "cv.pdf", {
    type: "application/pdf",
  });
  fireEvent.change(screen.getByLabelText(/pdf file/i), { target: { files: [file] } });
  return file;
}

describe("CvUploadForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("uploads the named PDF and reports the created CV", async () => {
    const cv = { id: "cv-1", name: "React CV", uploaded_at: "2026-06-11T00:00:00Z" };
    vi.mocked(uploadCv).mockResolvedValue(cv);
    const onUploaded = vi.fn();

    render(<CvUploadForm onUploaded={onUploaded} />);
    fireEvent.change(screen.getByLabelText(/cv name/i), { target: { value: "React CV" } });
    const file = selectFile();
    fireEvent.click(screen.getByRole("button", { name: /upload/i }));

    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith(cv));
    expect(uploadCv).toHaveBeenCalledWith("React CV", file);
  });

  it("shows a validation error when the upload is rejected", async () => {
    vi.mocked(uploadCv).mockRejectedValue(new ApiError(400, "bad pdf"));
    const onUploaded = vi.fn();

    render(<CvUploadForm onUploaded={onUploaded} />);
    fireEvent.change(screen.getByLabelText(/cv name/i), { target: { value: "X" } });
    selectFile();
    fireEvent.click(screen.getByRole("button", { name: /upload/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(onUploaded).not.toHaveBeenCalled();
  });
});
