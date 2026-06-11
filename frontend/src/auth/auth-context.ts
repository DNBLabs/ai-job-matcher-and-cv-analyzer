import { createContext } from "react";
import type { CurrentUser } from "../api/client";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

export interface AuthContextValue {
  /** The signed-in account, or `null` while loading or when anonymous. */
  user: CurrentUser | null;
  /** Lifecycle of the session probe. */
  status: AuthStatus;
  /** Re-run the session probe (e.g. after returning from OAuth). */
  refresh: () => Promise<void>;
  /** Clear the server session and reset to anonymous. */
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
