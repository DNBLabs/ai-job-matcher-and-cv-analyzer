import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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

function makeFullBreakdownResult(): JobMatchResult {
  return makeResult({
    breakdown: {
      match_score: 75,
      interview_likelihood: "medium",
      matched_skills: ["Python"],
      skill_gaps: ["Kubernetes"],
      red_flags: ["Requires clearance"],
      talking_points: ["5 years experience"],
    },
  });
}

function clickShowBreakdown(): void {
  fireEvent.click(screen.getByRole("button", { name: /show breakdown/i }));
}

function clickHideBreakdown(): void {
  fireEvent.click(screen.getByRole("button", { name: /hide breakdown/i }));
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

  it("test_ResultCard_onInitialMount_showsSummaryFieldsAndOmitsBreakdownFromDom", () => {
    render(<ResultCard result={makeFullBreakdownResult()} />);

    expect(screen.getByText("Senior Engineer")).toBeInTheDocument();
    expect(screen.getByText("Acme Corp")).toBeInTheDocument();
    expect(screen.getByText(/75/)).toBeInTheDocument();
    expect(screen.getByText(/AI estimate/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /apply/i })).toBeInTheDocument();

    expect(screen.queryByText("Python")).not.toBeInTheDocument();
    expect(screen.queryByText("Kubernetes")).not.toBeInTheDocument();
    expect(screen.queryByText("Requires clearance")).not.toBeInTheDocument();
    expect(screen.queryByText("5 years experience")).not.toBeInTheDocument();
  });

  it("test_ResultCard_onShowBreakdownClick_revealsBreakdownSectionsAndUpdatesButtonLabel", () => {
    render(<ResultCard result={makeFullBreakdownResult()} />);

    clickShowBreakdown();

    expect(screen.getByRole("heading", { name: /matched skills/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /skill gaps/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /red flags/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /talking points/i })).toBeInTheDocument();
    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByText("Kubernetes")).toBeInTheDocument();
    expect(screen.getByText("Requires clearance")).toBeInTheDocument();
    expect(screen.getByText("5 years experience")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /hide breakdown/i })).toBeInTheDocument();
  });

  it("test_ResultCard_onHideBreakdownClick_removesBreakdownFromDomAndResetsButtonLabel", () => {
    render(<ResultCard result={makeFullBreakdownResult()} />);

    clickShowBreakdown();
    clickHideBreakdown();

    expect(screen.queryByText("Python")).not.toBeInTheDocument();
    expect(screen.queryByText("Kubernetes")).not.toBeInTheDocument();
    expect(screen.queryByText("Requires clearance")).not.toBeInTheDocument();
    expect(screen.queryByText("5 years experience")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /show breakdown/i })).toBeInTheDocument();

    clickShowBreakdown();

    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /hide breakdown/i })).toBeInTheDocument();
  });

  it("test_ResultCard_whenOneCardExpanded_otherCardRemainsCollapsed", () => {
    render(
      <>
        <ResultCard
          result={makeResult({
            id: "r-1",
            title: "Job A",
            breakdown: {
              match_score: 75,
              interview_likelihood: "medium",
              matched_skills: ["Python"],
              skill_gaps: [],
              red_flags: [],
              talking_points: [],
            },
          })}
        />
        <ResultCard
          result={makeResult({
            id: "r-2",
            title: "Job B",
            breakdown: {
              match_score: 75,
              interview_likelihood: "medium",
              matched_skills: ["Rust"],
              skill_gaps: [],
              red_flags: [],
              talking_points: [],
            },
          })}
        />
      </>,
    );

    const showButtons = screen.getAllByRole("button", { name: /show breakdown/i });
    fireEvent.click(showButtons[0]);

    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.queryByText("Rust")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /hide breakdown/i })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: /show breakdown/i })).toHaveLength(1);
  });

  it("test_ResultCard_whenExpandedWithEmptyMatchedSkills_omitsMatchedSkillsSection", () => {
    render(
      <ResultCard
        result={makeResult({
          breakdown: {
            match_score: 75,
            interview_likelihood: "medium",
            matched_skills: [],
            skill_gaps: ["Kubernetes"],
            red_flags: [],
            talking_points: [],
          },
        })}
      />,
    );

    clickShowBreakdown();

    expect(screen.queryByRole("heading", { name: /matched skills/i })).not.toBeInTheDocument();
    expect(screen.getByText("Kubernetes")).toBeInTheDocument();
  });

  it("test_ResultCard_whenCollapsedWithDivergence_showsDivergenceBadgeInHeader", () => {
    render(<ResultCard result={makeResult({ match_score: 72, interview_likelihood: "low" })} />);

    expect(screen.getByText("Skills fit, seniority gap")).toBeInTheDocument();
    expect(screen.queryByText("Python")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /matched skills/i })).not.toBeInTheDocument();
  });

  it("test_ResultCard_afterExpandToggleClick_rendersMatchedSkillsAndSkillGaps", () => {
    render(<ResultCard result={makeResult()} />);

    clickShowBreakdown();

    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByText("Kubernetes")).toBeInTheDocument();
  });

  it("test_ResultCard_invalidInput_notApplicable", () => {
    const { container } = render(<ResultCard result={makeResult()} />);

    expect(container.querySelector("input")).not.toBeInTheDocument();
    expect(container.querySelector("textarea")).not.toBeInTheDocument();
    expect(container.querySelector("select")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /show breakdown/i })).toBeInTheDocument();
  });

  it("test_ResultCard_auth_notApplicable", () => {
    render(<ResultCard result={makeResult()} />);

    expect(screen.getByText("Senior Engineer")).toBeInTheDocument();
    expect(screen.queryByText(/sign in/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /show breakdown/i })).toBeInTheDocument();
  });

  it("test_ResultCard_downstream_noExternalCallsOnExpand", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    render(<ResultCard result={makeResult()} />);
    clickShowBreakdown();

    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
