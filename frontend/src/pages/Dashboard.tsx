import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { deleteCv, listCvs, listRuns, type Cv, type Run } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { useApiWarmup } from "../hooks/useApiWarmup";

const STATUS_LABELS: Record<Run["status"], string> = {
  queued: "Queued",
  scraping: "Scraping",
  scoring: "Scoring",
  complete: "Complete",
  failed: "Failed",
  cancelled: "Cancelled",
};

/**
 * Authenticated landing page: CV library, run history, and the entry point to
 * the new-run wizard. Shows a warming banner while a scaled-to-zero API wakes.
 */
export function Dashboard() {
  const { user, signOut } = useAuth();
  const { status: warmup } = useApiWarmup();
  const [cvs, setCvs] = useState<Cv[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const [cvList, runList] = await Promise.all([listCvs(), listRuns()]);
      setCvs(cvList);
      setRuns(runList);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleDelete(cvId: string) {
    await deleteCv(cvId);
    setCvs((current) => current.filter((cv) => cv.id !== cvId));
  }

  return (
    <main className="dashboard">
      <header className="dashboard-header">
        <h1>Dashboard</h1>
        <button type="button" onClick={() => void signOut()}>
          Sign out
        </button>
      </header>
      <p>Signed in as {user?.email}</p>

      {warmup === "warming" && (
        <p role="status" className="warming-banner">
          Waking the service up — this can take up to a minute on the first
          request. Hang tight.
        </p>
      )}

      <section className="cv-section">
        <div className="section-header">
          <h2>Your CVs</h2>
          <Link className="primary-action" to="/runs/new">
            Start a new run
          </Link>
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
        {loaded && runs.length === 0 ? (
          <p className="empty-state">No runs yet.</p>
        ) : (
          <ul className="run-list">
            {runs.map((run) => (
              <li key={run.id}>
                <Link to={`/runs/${run.id}`}>
                  {run.job_search.role} —{" "}
                  {run.job_search.remote ? "Remote" : run.job_search.location}
                </Link>
                <span className={`run-status status-${run.status}`}>
                  {STATUS_LABELS[run.status]}
                </span>
                <span className="run-date">
                  {new Date(run.created_at).toLocaleDateString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
