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
import { Alert, AlertDescription } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";

/**
 * Authenticated landing page: CV library, run history, daily quota, and the
 * entry point to the new-run wizard. Shows a warming banner while a
 * scaled-to-zero API wakes.
 */
export function Dashboard() {
  const { user } = useAuth();
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
    <main className="mx-auto max-w-3xl px-4 text-foreground">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
      </header>
      <p className="text-muted-foreground">Signed in as {user?.email}</p>

      {warmup === "warming" && (
        <Alert
          role="status"
          className="mb-4 border-sky-200 bg-sky-50 text-sky-900 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-100"
        >
          <AlertDescription>
            Waking the service up — this can take up to a minute on the first
            request. Hang tight.
          </AlertDescription>
        </Alert>
      )}

      <QuotaBanner quota={quota} />

      <section className="mt-8">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xl font-semibold text-foreground">Your CVs</h2>
          {startBlocked ? (
            <Button type="button" disabled>
              Start a new run
            </Button>
          ) : (
            <Button asChild>
              <Link to="/runs/new">Start a new run</Link>
            </Button>
          )}
        </div>
        {loaded && cvs.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No CVs yet — upload your first CV to start a run.
          </p>
        ) : (
          <ul className="mt-2 flex list-none flex-col gap-2 p-0">
            {cvs.map((cv) => (
              <li key={cv.id}>
                <Card className="flex min-w-0 flex-wrap items-center gap-3 p-3 sm:flex-nowrap">
                  <span className="min-w-0 flex-1 truncate font-medium">
                    {cv.name}
                  </span>
                  <span className="shrink-0 text-sm text-muted-foreground">
                    {new Date(cv.uploaded_at).toLocaleDateString()}
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void handleDelete(cv.id)}
                  >
                    Delete
                  </Button>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-8">
        <h2 className="text-xl font-semibold text-foreground">Run history</h2>
        {loaded && <RunHistory runs={runs} cvNames={cvNames} />}
      </section>
    </main>
  );
}
