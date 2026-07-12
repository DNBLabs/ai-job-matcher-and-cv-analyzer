import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TitleSuggestions } from "./TitleSuggestions";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, suggestTitles: vi.fn() };
});

import { suggestTitles } from "../api/client";

describe("TitleSuggestions", () => {
  afterEach(() => vi.restoreAllMocks());

  it("fetches and renders suggested titles for the CV", async () => {
    vi.mocked(suggestTitles).mockResolvedValue({
      titles: [
        { title: "Frontend Developer", rationale: "Strong React experience" },
        { title: "UI Engineer", rationale: "Design systems work" },
      ],
    });

    render(<TitleSuggestions cvId="cv-1" onUseTitle={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByText("Frontend Developer")).toBeInTheDocument(),
    );
    expect(suggestTitles).toHaveBeenCalledWith("cv-1");
    expect(screen.getByText("UI Engineer")).toBeInTheDocument();
  });

  it("hands the chosen title back when a suggestion is used", async () => {
    vi.mocked(suggestTitles).mockResolvedValue({
      titles: [{ title: "Frontend Developer", rationale: "React" }],
    });
    const onUseTitle = vi.fn();

    render(<TitleSuggestions cvId="cv-1" onUseTitle={onUseTitle} />);

    await waitFor(() =>
      expect(screen.getByText("Frontend Developer")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /use “Frontend Developer”|use frontend developer/i }));

    expect(onUseTitle).toHaveBeenCalledWith("Frontend Developer");
  });

  it("still lets the user skip when suggestions fail", async () => {
    vi.mocked(suggestTitles).mockRejectedValue(new Error("boom"));
    const onUseTitle = vi.fn();

    render(<TitleSuggestions cvId="cv-1" onUseTitle={onUseTitle} />);

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });

  it("test_titleSuggestions_loadedState_notLegacySuggestionClasses", async () => {
    vi.mocked(suggestTitles).mockResolvedValue({
      titles: [{ title: "Frontend Developer", rationale: "React experience" }],
    });

    render(<TitleSuggestions cvId="cv-1" onUseTitle={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByText("Frontend Developer")).toBeInTheDocument(),
    );

    const section = screen
      .getByRole("heading", { name: /suggested job titles/i })
      .closest("section");
    expect(section).not.toBeNull();
    expect(section).not.toHaveClass("title-suggestions");

    const list = screen.getByRole("list");
    expect(list).not.toHaveClass("suggestion-list");

    const customForm = screen.getByLabelText(/or enter your own role/i).closest("form");
    expect(customForm).not.toBeNull();
    expect(customForm).not.toHaveClass("custom-role");

    expect(screen.getByLabelText(/or enter your own role/i)).toHaveClass(
      "border-input",
      "bg-background",
      "text-foreground",
    );

    const useButton = screen.getByRole("button", { name: /use frontend developer/i });
    expect(useButton).toHaveClass("inline-flex");
  });

  it("test_titleSuggestions_errorState_usesAlertNotFormError", async () => {
    vi.mocked(suggestTitles).mockRejectedValue(new Error("boom"));

    render(<TitleSuggestions cvId="cv-1" onUseTitle={vi.fn()} />);

    const alert = await screen.findByRole("alert");
    expect(alert).not.toHaveClass("form-error");
    expect(alert).toHaveClass("rounded-lg", "border");
    expect(alert.className).toMatch(/destructive/i);
  });
});
