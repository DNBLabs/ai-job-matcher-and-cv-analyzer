import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  createRun,
  getRunQuota,
  type JobSearchCriteria,
  type Run,
  type RunQuota,
} from "../api/client";
import {
  EMPLOYMENT_TYPES,
  EXPERIENCE_LEVELS,
  REMOTE_LOCATION,
  UK_CITIES,
} from "../domain/jobSearch";

type SubmitState =
  | { kind: "idle" }
  | { kind: "starting" }
  | { kind: "error"; message: string };

/**
 * Job Search form: collects role, location/remote, and optional filters, shows
 * remaining quota, and starts an Analysis Run.
 *
 * Quota and concurrency are also enforced server-side; the UI display is a
 * convenience and a concurrent-run block disables the start button up front.
 */
export interface JobSearchFormProps {
  cvId: string;
  initialRole: string;
  onStarted: (run: Run) => void;
}

function quotaMessage(quota: RunQuota): string {
  if (quota.remaining === null) {
    return "Unlimited runs on your account.";
  }
  const noun = quota.remaining === 1 ? "run" : "runs";
  return `${quota.remaining} ${noun} left today.`;
}

export function JobSearchForm({ cvId, initialRole, onStarted }: JobSearchFormProps) {
  const [role, setRole] = useState(initialRole);
  const [location, setLocation] = useState<string>(UK_CITIES[0]);
  const [remote, setRemote] = useState(false);
  const [experienceLevel, setExperienceLevel] = useState("");
  const [employmentType, setEmploymentType] = useState("");
  const [quota, setQuota] = useState<RunQuota | null>(null);
  const [state, setState] = useState<SubmitState>({ kind: "idle" });

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const next = await getRunQuota();
        if (active) {
          setQuota(next);
        }
      } catch {
        // A missing quota readout is non-fatal; the server still enforces it.
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const concurrentBlocked = quota?.concurrent_blocked ?? false;
  const quotaExhausted = quota?.remaining === 0;
  const canStart =
    state.kind !== "starting" && !concurrentBlocked && !quotaExhausted && role.trim() !== "";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canStart) {
      return;
    }
    const criteria: JobSearchCriteria = {
      role: role.trim(),
      location: remote ? REMOTE_LOCATION : location,
      remote,
    };
    if (experienceLevel !== "" || employmentType !== "") {
      criteria.filters = {
        experience_level: experienceLevel || null,
        employment_type: employmentType || null,
      };
    }

    setState({ kind: "starting" });
    try {
      const run = await createRun(cvId, criteria);
      onStarted(run);
    } catch (error) {
      const message =
        error instanceof ApiError && error.status === 429
          ? "You've hit your run limit or already have a run in progress."
          : error instanceof ApiError && error.status === 400
            ? "Please check the role and location and try again."
            : "We couldn't start that run. Please try again.";
      setState({ kind: "error", message });
    }
  }

  return (
    <form className="job-search-form" onSubmit={handleSubmit}>
      <h3>Search for jobs</h3>

      {quota && <p className="quota-note">{quotaMessage(quota)}</p>}
      {concurrentBlocked && (
        <p className="quota-note">A run is already running — wait for it to finish.</p>
      )}

      <label htmlFor="role">Role or keywords</label>
      <input
        id="role"
        name="role"
        type="text"
        required
        value={role}
        onChange={(event) => setRole(event.target.value)}
      />

      <label htmlFor="location">Location</label>
      <select
        id="location"
        name="location"
        value={location}
        disabled={remote}
        onChange={(event) => setLocation(event.target.value)}
      >
        {UK_CITIES.map((city) => (
          <option key={city} value={city}>
            {city}
          </option>
        ))}
      </select>

      <label htmlFor="remote">
        <input
          id="remote"
          name="remote"
          type="checkbox"
          checked={remote}
          onChange={(event) => setRemote(event.target.checked)}
        />
        Remote only
      </label>

      <label htmlFor="experience-level">Experience level (optional)</label>
      <select
        id="experience-level"
        name="experience-level"
        value={experienceLevel}
        onChange={(event) => setExperienceLevel(event.target.value)}
      >
        <option value="">Any</option>
        {EXPERIENCE_LEVELS.map((level) => (
          <option key={level.value} value={level.value}>
            {level.label}
          </option>
        ))}
      </select>

      <label htmlFor="employment-type">Employment type (optional)</label>
      <select
        id="employment-type"
        name="employment-type"
        value={employmentType}
        onChange={(event) => setEmploymentType(event.target.value)}
      >
        <option value="">Any</option>
        {EMPLOYMENT_TYPES.map((type) => (
          <option key={type.value} value={type.value}>
            {type.label}
          </option>
        ))}
      </select>

      <button type="submit" disabled={!canStart}>
        {state.kind === "starting" ? "Starting…" : "Start analysis run"}
      </button>

      {state.kind === "error" && (
        <p role="alert" className="form-error">
          {state.message}
        </p>
      )}
    </form>
  );
}
