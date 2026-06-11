import { useAuth } from "../auth/useAuth";

/**
 * Authenticated landing page.
 *
 * This is the minimal protected shell for Task 20; the CV wizard, job-search
 * form, and run history are built out in Task 21.
 */
export function Dashboard() {
  const { user, signOut } = useAuth();

  return (
    <main className="dashboard">
      <header className="dashboard-header">
        <h1>Dashboard</h1>
        <button type="button" onClick={() => void signOut()}>
          Sign out
        </button>
      </header>
      <p>Signed in as {user?.email}</p>
      <p className="status-note">
        CV upload, job search, and run history arrive in Task 21.
      </p>
    </main>
  );
}
