import { useState } from "react";
import { Link } from "react-router-dom";
import {
  searchAdminUsers,
  setUserUnlimited,
  type AdminUser,
} from "../api/client";

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
    <main className="admin-page">
      <header className="admin-header">
        <h1>Admin</h1>
        <Link to="/dashboard">Back to dashboard</Link>
      </header>

      <form className="admin-search" onSubmit={handleSearch}>
        <label htmlFor="admin-email-search">Search users by email</label>
        <input
          id="admin-email-search"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="email fragment"
        />
        <button type="submit">Search</button>
      </form>

      {error && (
        <p role="alert" className="admin-error">
          {error}
        </p>
      )}

      {searched && users.length === 0 && (
        <p className="empty-state">No users match that email.</p>
      )}

      {users.length > 0 && (
        <ul className="admin-user-list">
          {users.map((user) => (
            <li key={user.id} className="admin-user-row">
              <span className="admin-user-email">{user.email}</span>
              <span className="admin-user-status">
                {user.is_unlimited ? "Unlimited" : "Standard"}
              </span>
              <button
                type="button"
                disabled={pendingId === user.id}
                onClick={() => void handleToggle(user)}
              >
                {user.is_unlimited ? "Remove unlimited" : "Make unlimited"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
