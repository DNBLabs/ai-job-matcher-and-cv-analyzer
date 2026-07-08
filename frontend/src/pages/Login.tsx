import { useState, type FormEvent } from "react";
import { ApiError, googleLoginUrl, requestMagicLink } from "../api/client";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Separator } from "../components/ui/separator";

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
    <main className="flex min-h-screen items-center justify-center bg-background px-4 text-foreground">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <h1 className="text-2xl font-semibold leading-none tracking-tight text-foreground">
            Sign in
          </h1>
          <CardDescription>Access your CVs and Analysis Runs.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button variant="outline" className="w-full text-foreground" asChild>
            <a href={googleLoginUrl()}>Continue with Google</a>
          </Button>

          <div className="flex items-center gap-2">
            <Separator orientation="horizontal" className="flex-1" />
            <span className="text-sm text-muted-foreground">or</span>
            <Separator orientation="horizontal" className="flex-1" />
          </div>

          {state.kind === "sent" ? (
            <p
              role="status"
              className="rounded-lg border bg-card p-4 text-sm text-card-foreground"
            >
              Check your email — we sent a sign-in link to{" "}
              <strong>{state.email}</strong> if it matches an account.
            </p>
          ) : (
            <form onSubmit={handleSubmit} noValidate className="space-y-4">
              <div className="space-y-2">
                <label htmlFor="email">Email address</label>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  autoComplete="email"
                />
              </div>
              <Button type="submit" disabled={state.kind === "submitting"}>
                Email me a sign-in link
              </Button>
              {state.kind === "error" && (
                <Alert variant="destructive">
                  <AlertDescription>{state.message}</AlertDescription>
                </Alert>
              )}
            </form>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
