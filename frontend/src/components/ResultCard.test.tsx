import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { JobMatchResult } from "../api/client";
import { ResultCard } from "./ResultCard";

function makeResult(overrides: Partial<JobMatchResult> = {}): JobMatchResult {
  return {
    id: "r-1",
    source: "adzuna",
    external_id: "a1",
    title: "Senior Engineer",
    company: "Acme Corp",
    url: "https://example.com/job",
    match_score: 75,
    interview_likelihood: "medium",
    breakdown: {
      match_score: 75,
      interview_likelihood: "medium",
      matched_skills: ["Python"],
      skill_gaps: ["Kubernetes"],
      red_flags: [],
      talking_points: ["5 years experience"],
    },
    created_at: "2026-06-13T10:00:00Z",
    ...overrides,
  };
}

describe("ResultCard", () => {
  it("renders job title, company, and match score", () => {
    render(<ResultCard result={makeResult()} />);
    expect(screen.getByText("Senior Engineer")).toBeInTheDocument();
    expect(screen.getByText("Acme Corp")).toBeInTheDocument();
    expect(screen.getByText(/75/)).toBeInTheDocument();
  });

  it("labels interview likelihood as an AI estimate", () => {
    render(<ResultCard result={makeResult()} />);
    expect(screen.getByText(/AI estimate/i)).toBeInTheDocument();
  });

  it("shows 'Skills fit, seniority gap' badge when score ≥70 and likelihood is low", () => {
    render(<ResultCard result={makeResult({ match_score: 72, interview_likelihood: "low" })} />);
    expect(screen.getByText("Skills fit, seniority gap")).toBeInTheDocument();
  });

  it("shows 'Competitive profile, weak keyword fit' badge when score <50 and likelihood is high", () => {
    render(<ResultCard result={makeResult({ match_score: 45, interview_likelihood: "high" })} />);
    expect(screen.getByText("Competitive profile, weak keyword fit")).toBeInTheDocument();
  });

  it("shows no divergence badge for a non-divergent result", () => {
    render(<ResultCard result={makeResult({ match_score: 75, interview_likelihood: "medium" })} />);
    expect(screen.queryByText("Skills fit, seniority gap")).not.toBeInTheDocument();
    expect(screen.queryByText("Competitive profile, weak keyword fit")).not.toBeInTheDocument();
  });

  it("renders apply link opening in a new tab with noopener noreferrer", () => {
    render(<ResultCard result={makeResult()} />);
    const link = screen.getByRole("link", { name: /apply/i });
    expect(link).toHaveAttribute("href", "https://example.com/job");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders matched skills and skill gaps from the breakdown", () => {
    render(<ResultCard result={makeResult()} />);
    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByText("Kubernetes")).toBeInTheDocument();
  });
});
