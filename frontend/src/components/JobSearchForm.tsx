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
import { QuotaBanner } from "./QuotaBanner";
import { Alert, AlertDescription } from "./ui/alert";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";

type SubmitState =
  | { kind: "idle" }
  | { kind: "starting" }
  | { kind: "error"; message: string };

const ANY_FILTER_VALUE = "any";

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
    <form className="mt-4 flex flex-col gap-3" onSubmit={handleSubmit}>
      <h3 className="text-lg font-semibold">Search for jobs</h3>

      <QuotaBanner quota={quota} />

      <label htmlFor="role" className="text-sm font-medium">
        Role or keywords
      </label>
      <Input
        id="role"
        name="role"
        type="text"
        required
        className="text-foreground"
        value={role}
        onChange={(event) => setRole(event.target.value)}
      />

      <label htmlFor="location" className="text-sm font-medium">
        Location
      </label>
      <Select value={location} onValueChange={setLocation} disabled={remote}>
        <SelectTrigger id="location">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {UK_CITIES.map((city) => (
            <SelectItem key={city} value={city}>
              {city}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <label htmlFor="remote" className="flex items-center gap-2 text-sm font-medium">
        <input
          id="remote"
          name="remote"
          type="checkbox"
          checked={remote}
          onChange={(event) => setRemote(event.target.checked)}
        />
        Remote only
      </label>

      <label htmlFor="experience-level" className="text-sm font-medium">
        Experience level (optional)
      </label>
      <Select
        value={experienceLevel || ANY_FILTER_VALUE}
        onValueChange={(value) =>
          setExperienceLevel(value === ANY_FILTER_VALUE ? "" : value)
        }
      >
        <SelectTrigger id="experience-level">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY_FILTER_VALUE}>Any</SelectItem>
          {EXPERIENCE_LEVELS.map((level) => (
            <SelectItem key={level.value} value={level.value}>
              {level.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <label htmlFor="employment-type" className="text-sm font-medium">
        Employment type (optional)
      </label>
      <Select
        value={employmentType || ANY_FILTER_VALUE}
        onValueChange={(value) =>
          setEmploymentType(value === ANY_FILTER_VALUE ? "" : value)
        }
      >
        <SelectTrigger id="employment-type">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY_FILTER_VALUE}>Any</SelectItem>
          {EMPLOYMENT_TYPES.map((type) => (
            <SelectItem key={type.value} value={type.value}>
              {type.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Button type="submit" disabled={!canStart}>
        {state.kind === "starting" ? "Starting…" : "Start analysis run"}
      </Button>

      {state.kind === "error" && (
        <Alert variant="destructive">
          <AlertDescription>{state.message}</AlertDescription>
        </Alert>
      )}
    </form>
  );
}
