import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  deleteCv,
  getRunQuota,
  listCvs,
  listRuns,
  type Cv,
  type Run,
  type RunQuota,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useApiWarmup } from "../hooks/useApiWarmup";
import { QuotaBanner } from "../components/QuotaBanner";
import { RunHistory } from "../components/RunHistory";

/**
 * Authenticated landing page: CV library, run history, daily quota, and the
 * entry point to the new-run wizard. Shows a warming banner while a
 * scaled-to-zero API wakes.
 */
export function Dashboard() {
  const { user, signOut } = useAuth();
  const { status: warmup } = useApiWarmup();
  const [cvs, setCvs] = useState<Cv[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [quota, setQuota] = useState<RunQuota | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const [cvList, runList] = await Promise.all([listCvs(), listRuns()]);
      setCvs(cvList);
      setRuns(runList);
      try {
        setQuota(await getRunQuota());
      } catch {
        // A missing quota readout is non-fatal; the server still enforces it.
      }
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const cvNames = useMemo(
    () => new Map(cvs.map((cv) => [cv.id, cv.name])),
    [cvs],
  );

  // Unlimited accounts have `remaining === null` and are never cap-blocked here.
  const startBlocked =
    quota !== null && (quota.concurrent_blocked || quota.remaining === 0);

  async function handleDelete(cvId: string) {
    await deleteCv(cvId);
    setCvs((current) => current.filter((cv) => cv.id !== cvId));
  }

  return (
    <main className="dashboard">
      <header className="dashboard-header">
        <h1>Dashboard</h1>
        <nav className="dashboard-nav">
          {user?.is_admin && <Link to="/admin">Admin</Link>}
          <button type="button" onClick={() => void signOut()}>
            Sign out
          </button>
        </nav>
      </header>
      <p>Signed in as {user?.email}</p>

      {warmup === "warming" && (
        <p role="status" className="warming-banner">
          Waking the service up — this can take up to a minute on the first
          request. Hang tight.
        </p>
      )}

      <QuotaBanner quota={quota} />

      <section className="cv-section">
        <div className="section-header">
          <h2>Your CVs</h2>
          {startBlocked ? (
            <button type="button" className="primary-action" disabled>
              Start a new run
            </button>
          ) : (
            <Link className="primary-action" to="/runs/new">
              Start a new run
            </Link>
          )}
        </div>
        {loaded && cvs.length === 0 ? (
          <p className="empty-state">No CVs yet — upload your first CV to start a run.</p>
        ) : (
          <ul className="cv-list">
            {cvs.map((cv) => (
              <li key={cv.id}>
                <span className="cv-name">{cv.name}</span>
                <span className="cv-date">
                  {new Date(cv.uploaded_at).toLocaleDateString()}
                </span>
                <button type="button" onClick={() => void handleDelete(cv.id)}>
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="run-section">
        <h2>Run history</h2>
        {loaded && <RunHistory runs={runs} cvNames={cvNames} />}
      </section>
    </main>
  );
}
