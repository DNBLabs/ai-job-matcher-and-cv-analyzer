import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { QuotaBanner } from "./QuotaBanner";

describe("QuotaBanner", () => {
  it("shows the plural remaining-runs message", () => {
    render(<QuotaBanner quota={{ remaining: 2, concurrent_blocked: false }} />);
    expect(screen.getByText(/2 runs left today/i)).toBeInTheDocument();
  });

  it("uses the singular noun for one remaining run", () => {
    render(<QuotaBanner quota={{ remaining: 1, concurrent_blocked: false }} />);
    expect(screen.getByText(/1 run left today/i)).toBeInTheDocument();
  });

  it("hides the daily cap for unlimited accounts", () => {
    render(<QuotaBanner quota={{ remaining: null, concurrent_blocked: false }} />);
    expect(screen.getByText(/unlimited/i)).toBeInTheDocument();
    expect(screen.queryByText(/left today/i)).not.toBeInTheDocument();
  });

  it("warns when a concurrent run blocks a new start", () => {
    render(<QuotaBanner quota={{ remaining: 2, concurrent_blocked: true }} />);
    expect(screen.getByText(/already running/i)).toBeInTheDocument();
  });

  it("renders nothing while the quota is unknown", () => {
    const { container } = render(<QuotaBanner quota={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
