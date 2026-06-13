import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "./useAuth";

/**
 * Gate a route behind admin privileges.
 *
 * While the session probe runs a loading state is shown; anonymous users go to
 * `/login` and authenticated non-admins are redirected to the dashboard so the
 * operator console is never revealed to them.
 */
export function AdminRoute({ children }: { children: ReactNode }) {
  const { status, user } = useAuth();

  if (status === "loading") {
    return <p role="status">Loading…</p>;
  }

  if (status === "anonymous") {
    return <Navigate to="/login" replace />;
  }

  if (!user?.is_admin) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}
