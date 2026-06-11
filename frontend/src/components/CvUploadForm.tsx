import { useState, type FormEvent } from "react";
import { ApiError, uploadCv, type Cv } from "../api/client";

type State =
  | { kind: "idle" }
  | { kind: "uploading" }
  | { kind: "error"; message: string };

const SIZE_LIMIT_MESSAGE = "That file is larger than the 5 MB limit.";
const GENERIC_ERROR_MESSAGE = "We couldn't upload that CV. Please try again.";

/**
 * Upload a named CV PDF.
 *
 * Validation (PDF type, 5 MB cap, magic bytes) is enforced server-side; this
 * form surfaces the resulting error and, on success, hands the created CV back
 * to the wizard via {@link CvUploadFormProps.onUploaded}.
 */
export interface CvUploadFormProps {
  onUploaded: (cv: Cv) => void;
}

export function CvUploadForm({ onUploaded }: CvUploadFormProps) {
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<State>({ kind: "idle" });

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || name.trim() === "") {
      return;
    }
    setState({ kind: "uploading" });
    try {
      const cv = await uploadCv(name.trim(), file);
      setState({ kind: "idle" });
      onUploaded(cv);
    } catch (error) {
      const message =
        error instanceof ApiError && error.status === 413
          ? SIZE_LIMIT_MESSAGE
          : error instanceof ApiError && error.status === 400
            ? "That file was rejected — please upload a valid PDF CV."
            : GENERIC_ERROR_MESSAGE;
      setState({ kind: "error", message });
    }
  }

  return (
    <form className="cv-upload-form" onSubmit={handleSubmit} noValidate>
      <label htmlFor="cv-name">CV name</label>
      <input
        id="cv-name"
        name="cv-name"
        type="text"
        required
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="e.g. React-focused"
      />

      <label htmlFor="cv-file">PDF file</label>
      <input
        id="cv-file"
        name="cv-file"
        type="file"
        accept="application/pdf"
        required
        onChange={(event) => setFile(event.target.files?.[0] ?? null)}
      />

      <button type="submit" disabled={state.kind === "uploading" || !file || name.trim() === ""}>
        {state.kind === "uploading" ? "Uploading…" : "Upload CV"}
      </button>

      {state.kind === "error" && (
        <p role="alert" className="form-error">
          {state.message}
        </p>
      )}
    </form>
  );
}
