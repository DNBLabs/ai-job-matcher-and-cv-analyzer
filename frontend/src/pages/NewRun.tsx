import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listCvs, type Cv, type Run } from "../api/client";
import { CvUploadForm } from "../components/CvUploadForm";
import { JobSearchForm } from "../components/JobSearchForm";
import { TitleSuggestions } from "../components/TitleSuggestions";

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
    <main className="new-run">
      <header>
        <h1>Start a new analysis run</h1>
        <Link to="/dashboard">Cancel</Link>
      </header>

      {step.name === "cv" && (
        <section>
          {cvs.length > 0 && (
            <div className="existing-cvs">
              <h3>Use an existing CV</h3>
              <ul>
                {cvs.map((cv) => (
                  <li key={cv.id}>
                    <span>{cv.name}</span>
                    <button
                      type="button"
                      onClick={() => setStep({ name: "titles", cv })}
                    >
                      Use {cv.name}
                    </button>
                  </li>
                ))}
              </ul>
              <p className="divider">or upload a new one</p>
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
          <p className="wizard-cv">Using CV: <strong>{step.cv.name}</strong></p>
          <TitleSuggestions
            cvId={step.cv.id}
            onUseTitle={(role) => setStep({ name: "search", cv: step.cv, role })}
          />
        </section>
      )}

      {step.name === "search" && (
        <section>
          <p className="wizard-cv">Using CV: <strong>{step.cv.name}</strong></p>
          <JobSearchForm cvId={step.cv.id} initialRole={step.role} onStarted={handleStarted} />
        </section>
      )}
    </main>
  );
}
