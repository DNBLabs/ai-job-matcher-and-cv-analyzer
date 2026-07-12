import { useState } from "react";
import { Link } from "react-router-dom";
import {
  searchAdminUsers,
  setUserUnlimited,
  type AdminUser,
} from "../api/client";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";

/**
 * Operator console: search User Accounts by email and toggle the unlimited
 * quota flag. Reachable only via {@link AdminRoute}; the backend additionally
 * returns 404 for non-admins.
 */
export function Admin() {
  const [query, setQuery] = useState("");
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  async function handleSearch(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const matches = await searchAdminUsers(query);
      setUsers(matches);
      setSearched(true);
    } catch {
      setError("Could not search users. Try again.");
    }
  }

  async function handleToggle(user: AdminUser) {
    setError(null);
    setPendingId(user.id);
    try {
      const updated = await setUserUnlimited(user.id, !user.is_unlimited);
      setUsers((current) =>
        current.map((u) => (u.id === updated.id ? updated : u)),
      );
    } catch {
      setError("Could not update the user. Try again.");
    } finally {
      setPendingId(null);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-4 text-foreground">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Admin</h1>
        <Button variant="link" asChild>
          <Link to="/dashboard">Back to dashboard</Link>
        </Button>
      </header>

      <form
        className="mt-6 flex flex-wrap items-end gap-3"
        onSubmit={handleSearch}
      >
        <div className="min-w-0 flex-1 space-y-2">
          <label htmlFor="admin-email-search" className="text-sm font-medium text-foreground">
            Search users by email
          </label>
          <Input
            id="admin-email-search"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="email fragment"
          />
        </div>
        <Button type="submit">Search</Button>
      </form>

      {error && (
        <Alert variant="destructive" className="mt-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {searched && users.length === 0 && (
        <p className="mt-4 text-muted-foreground">No users match that email.</p>
      )}

      {users.length > 0 && (
        <ul className="mt-6 flex list-none flex-col gap-3 p-0">
          {users.map((user) => (
            <li
              key={user.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border p-3"
            >
              <span className="min-w-0 truncate text-foreground">{user.email}</span>
              <span className="text-sm text-muted-foreground">
                {user.is_unlimited ? "Unlimited" : "Standard"}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={pendingId === user.id}
                onClick={() => void handleToggle(user)}
              >
                {user.is_unlimited ? "Remove unlimited" : "Make unlimited"}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
