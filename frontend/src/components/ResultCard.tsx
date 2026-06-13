import type { JobMatchResult } from "../api/client";

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
  const badge = getDivergenceBadge(result.match_score, result.interview_likelihood);
  const likelihoodLabel =
    LIKELIHOOD_LABELS[result.interview_likelihood] ?? result.interview_likelihood;

  return (
    <article className="result-card">
      <header className="result-card-header">
        <div className="result-card-title-row">
          <h3 className="result-card-title">{result.title}</h3>
          <span className="result-score">{result.match_score}</span>
        </div>
        <p className="result-card-company">{result.company}</p>
        <div className="result-card-meta">
          <span className="result-source">{result.source}</span>
          <span className="result-likelihood">
            {likelihoodLabel}{" "}
            <span className="result-likelihood-note">(AI estimate)</span>
          </span>
          {badge && <span className="divergence-badge">{badge}</span>}
        </div>
      </header>

      {result.breakdown.matched_skills.length > 0 && (
        <section className="result-breakdown">
          <h4>Matched skills</h4>
          <ul>
            {result.breakdown.matched_skills.map((skill) => (
              <li key={skill}>{skill}</li>
            ))}
          </ul>
        </section>
      )}

      {result.breakdown.skill_gaps.length > 0 && (
        <section className="result-breakdown">
          <h4>Skill gaps</h4>
          <ul>
            {result.breakdown.skill_gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </section>
      )}

      {result.breakdown.red_flags.length > 0 && (
        <section className="result-breakdown">
          <h4>Red flags</h4>
          <ul>
            {result.breakdown.red_flags.map((flag) => (
              <li key={flag}>{flag}</li>
            ))}
          </ul>
        </section>
      )}

      {result.breakdown.talking_points.length > 0 && (
        <section className="result-breakdown">
          <h4>Talking points</h4>
          <ul>
            {result.breakdown.talking_points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </section>
      )}

      <footer className="result-card-footer">
        <a
          href={result.url}
          target="_blank"
          rel="noopener noreferrer"
          className="result-apply-link"
        >
          Apply
        </a>
      </footer>
    </article>
  );
}
