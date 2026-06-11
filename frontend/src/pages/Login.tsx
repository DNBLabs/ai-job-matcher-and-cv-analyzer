import { useState, type FormEvent } from "react";
import { ApiError, googleLoginUrl, requestMagicLink } from "../api/client";

type FormState =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "sent"; email: string }
  | { kind: "error"; message: string };

const RATE_LIMIT_MESSAGE =
  "Too many sign-in requests. Please wait a while before trying again.";
const GENERIC_ERROR_MESSAGE =
  "Something went wrong sending your sign-in link. Please try again.";

/**
 * Sign-in page offering Google OAuth and email magic-link entry points.
 *
 * The Google button is a real anchor so the browser performs a full-page
 * redirect to the backend OAuth flow; the magic-link form submits via the API
 * client and confirms with a check-email state.
 */
export function Login() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<FormState>({ kind: "idle" });

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState({ kind: "submitting" });
    try {
      await requestMagicLink(email);
      setState({ kind: "sent", email });
    } catch (error) {
      const message =
        error instanceof ApiError && error.status === 429
          ? RATE_LIMIT_MESSAGE
          : GENERIC_ERROR_MESSAGE;
      setState({ kind: "error", message });
    }
  }

  return (
    <main className="auth-page">
      <h1>Sign in</h1>
      <p>Access your CVs and Analysis Runs.</p>

      <a className="google-button" href={googleLoginUrl()}>
        Continue with Google
      </a>

      <div className="divider">or</div>

      {state.kind === "sent" ? (
        <p role="status">
          Check your email — we sent a sign-in link to{" "}
          <strong>{state.email}</strong> if it matches an account.
        </p>
      ) : (
        <form onSubmit={handleSubmit} noValidate>
          <label htmlFor="email">Email address</label>
          <input
            id="email"
            name="email"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
          />
          <button type="submit" disabled={state.kind === "submitting"}>
            Email me a sign-in link
          </button>
          {state.kind === "error" && (
            <p role="alert" className="form-error">
              {state.message}
            </p>
          )}
        </form>
      )}
    </main>
  );
}
