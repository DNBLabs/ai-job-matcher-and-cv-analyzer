import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "./useAuth";

/**
 * Gate a route behind authentication.
 *
 * While the session probe is in flight a loading state is shown; anonymous
 * users are redirected to `/login`, replacing history so Back does not loop.
 */
export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { status } = useAuth();

  if (status === "loading") {
    return <p role="status">Loading…</p>;
  }

  if (status === "anonymous") {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
