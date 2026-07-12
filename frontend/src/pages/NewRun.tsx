import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listCvs, type Cv, type Run } from "../api/client";
import { CvUploadForm } from "../components/CvUploadForm";
import { JobSearchForm } from "../components/JobSearchForm";
import { TitleSuggestions } from "../components/TitleSuggestions";
import { Button } from "../components/ui/button";

type Step =
  | { name: "cv" }
  | { name: "titles"; cv: Cv }
  | { name: "search"; cv: Cv; role: string };

/**
 * New Analysis Run wizard: pick or upload a CV, review AI-suggested titles,
 * define the Job Search, and start the run. On success it navigates to the run
 * detail page, where status polling takes over.
 */
export function NewRun() {
  const navigate = useNavigate();
  const [cvs, setCvs] = useState<Cv[]>([]);
  const [step, setStep] = useState<Step>({ name: "cv" });

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const existing = await listCvs();
        if (active) {
          setCvs(existing);
        }
      } catch {
        // Non-fatal: the user can still upload a fresh CV.
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  function handleStarted(run: Run) {
    navigate(`/runs/${run.id}`);
  }

  return (
    <main className="mx-auto max-w-3xl px-4 text-foreground">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Start a new analysis run</h1>
        <Button variant="link" asChild>
          <Link to="/dashboard">Cancel</Link>
        </Button>
      </header>

      {step.name === "cv" && (
        <section>
          {cvs.length > 0 && (
            <div className="mt-6 space-y-3">
              <h3 className="text-lg font-semibold text-foreground">Use an existing CV</h3>
              <ul className="flex list-none flex-col gap-2 p-0">
                {cvs.map((cv) => (
                  <li key={cv.id} className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate">{cv.name}</span>
                    <Button
                      type="button"
                      onClick={() => setStep({ name: "titles", cv })}
                    >
                      Use {cv.name}
                    </Button>
                  </li>
                ))}
              </ul>
              <p className="text-center text-sm text-muted-foreground">or upload a new one</p>
            </div>
          )}
          <CvUploadForm
            onUploaded={(cv) => {
              setCvs((current) => [cv, ...current]);
              setStep({ name: "titles", cv });
            }}
          />
        </section>
      )}

      {step.name === "titles" && (
        <section>
          <p className="text-sm text-muted-foreground">
            Using CV: <strong className="text-foreground">{step.cv.name}</strong>
          </p>
          <TitleSuggestions
            cvId={step.cv.id}
            onUseTitle={(role) => setStep({ name: "search", cv: step.cv, role })}
          />
        </section>
      )}

      {step.name === "search" && (
        <section>
          <p className="text-sm text-muted-foreground">
            Using CV: <strong className="text-foreground">{step.cv.name}</strong>
          </p>
          <JobSearchForm cvId={step.cv.id} initialRole={step.role} onStarted={handleStarted} />
        </section>
      )}
    </main>
  );
}
