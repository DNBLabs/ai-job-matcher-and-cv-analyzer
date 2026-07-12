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

  it("test_cvUploadForm_usesShadcnInputButtonNotLegacyClasses", () => {
    render(<CvUploadForm onUploaded={vi.fn()} />);

    const form = screen.getByLabelText(/cv name/i).closest("form");
    expect(form).not.toBeNull();
    expect(form).not.toHaveClass("cv-upload-form");

    expect(screen.getByLabelText(/cv name/i)).toHaveClass(
      "border-input",
      "bg-background",
      "text-foreground",
    );
    expect(screen.getByLabelText(/pdf file/i)).toHaveClass(
      "border-input",
      "bg-background",
    );

    const uploadButton = screen.getByRole("button", { name: /upload cv/i });
    expect(uploadButton).toHaveClass("inline-flex");
    expect(uploadButton).not.toHaveClass("primary-action");
  });

  it("test_cvUploadForm_errorState_usesAlertNotFormError", async () => {
    vi.mocked(uploadCv).mockRejectedValue(new ApiError(400, "bad pdf"));

    render(<CvUploadForm onUploaded={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/cv name/i), { target: { value: "X" } });
    selectFile();
    fireEvent.click(screen.getByRole("button", { name: /upload/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).not.toHaveClass("form-error");
    expect(alert).toHaveClass("rounded-lg", "border");
    expect(alert.className).toMatch(/destructive/i);
  });
});
