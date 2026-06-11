import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { getCurrentUser, logout, type CurrentUser } from "../api/client";
import { AuthContext, type AuthStatus } from "./auth-context";

/**
 * Provides authentication state to the SPA.
 *
 * On mount it probes the session via `GET /auth/me` and exposes the resulting
 * user plus `refresh`/`signOut` actions through {@link useAuth}.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  const applySession = useCallback((current: CurrentUser | null) => {
    setUser(current);
    setStatus(current ? "authenticated" : "anonymous");
  }, []);

  const refresh = useCallback(async () => {
    try {
      applySession(await getCurrentUser());
    } catch {
      applySession(null);
    }
  }, [applySession]);

  const signOut = useCallback(async () => {
    await logout();
    applySession(null);
  }, [applySession]);

  // Probe the session once on mount. State is updated only after the awaited
  // network call resolves, never synchronously within the effect body.
  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const current = await getCurrentUser();
        if (active) {
          applySession(current);
        }
      } catch {
        if (active) {
          applySession(null);
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [applySession]);

  const value = useMemo(
    () => ({ user, status, refresh, signOut }),
    [user, status, refresh, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
