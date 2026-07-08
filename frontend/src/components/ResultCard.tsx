import { useState } from "react";
import type { JobMatchResult } from "../api/client";
import { Button } from "./ui/button";

interface Props {
  result: JobMatchResult;
}

const LIKELIHOOD_LABELS: Record<string, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

function getDivergenceBadge(matchScore: number, likelihood: string): string | null {
  if (matchScore >= 70 && likelihood === "low") return "Skills fit, seniority gap";
  if (matchScore < 50 && likelihood === "high") return "Competitive profile, weak keyword fit";
  return null;
}

export function ResultCard({ result }: Props) {
  const [expanded, setExpanded] = useState(false);
  const badge = getDivergenceBadge(result.match_score, result.interview_likelihood);
  const likelihoodLabel =
    LIKELIHOOD_LABELS[result.interview_likelihood] ?? result.interview_likelihood;

  return (
    <article className="rounded-lg border border-border px-5 py-4">
      <header>
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="m-0 text-[1.05rem] font-semibold">{result.title}</h3>
          <span className="whitespace-nowrap text-[1.4rem] font-bold text-primary">
            {result.match_score}
          </span>
        </div>
        <p className="my-1 text-[0.95rem] text-muted-foreground">{result.company}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs capitalize">
            {result.source}
          </span>
          <span className="text-sm text-muted-foreground">
            {likelihoodLabel}{" "}
            <span className="text-xs text-muted-foreground/80">(AI estimate)</span>
          </span>
          {badge && (
            <span className="rounded-full border border-yellow-400 bg-yellow-50 px-2 py-0.5 text-xs text-yellow-800">
              {badge}
            </span>
          )}
        </div>
      </header>

      <Button
        type="button"
        variant="ghost"
        onClick={() => setExpanded((prev) => !prev)}
      >
        {expanded ? "Hide breakdown" : "Show breakdown"}
      </Button>

      {expanded && (
        <>
          {result.breakdown.matched_skills.length > 0 && (
            <section className="mt-3">
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Matched skills
              </h4>
              <ul className="m-0 list-disc pl-5 text-sm text-muted-foreground">
                {result.breakdown.matched_skills.map((skill) => (
                  <li key={skill} className="mb-0.5">
                    {skill}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {result.breakdown.skill_gaps.length > 0 && (
            <section className="mt-3">
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Skill gaps
              </h4>
              <ul className="m-0 list-disc pl-5 text-sm text-muted-foreground">
                {result.breakdown.skill_gaps.map((gap) => (
                  <li key={gap} className="mb-0.5">
                    {gap}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {result.breakdown.red_flags.length > 0 && (
            <section className="mt-3">
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Red flags
              </h4>
              <ul className="m-0 list-disc pl-5 text-sm text-muted-foreground">
                {result.breakdown.red_flags.map((flag) => (
                  <li key={flag} className="mb-0.5">
                    {flag}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {result.breakdown.talking_points.length > 0 && (
            <section className="mt-3">
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Talking points
              </h4>
              <ul className="m-0 list-disc pl-5 text-sm text-muted-foreground">
                {result.breakdown.talking_points.map((point) => (
                  <li key={point} className="mb-0.5">
                    {point}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      <footer className="mt-4 border-t border-border pt-3">
        <a
          href={result.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground no-underline"
        >
          Apply
        </a>
      </footer>
    </article>
  );
}
