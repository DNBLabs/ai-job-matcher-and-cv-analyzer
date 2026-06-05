import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("shows the application title for Job Seekers", () => {
    render(<App />);
    expect(
      screen.getByRole("heading", { name: /AI Job Matcher & CV Analyzer/i }),
    ).toBeDefined();
  });
});
