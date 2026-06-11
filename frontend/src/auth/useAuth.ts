import { useContext } from "react";
import { AuthContext, type AuthContextValue } from "./auth-context";

/**
 * Access the authentication state and actions.
 *
 * @throws when called outside an {@link AuthProvider}.
 */
export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return value;
}
