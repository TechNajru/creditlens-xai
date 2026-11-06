import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ExplanationPanel } from "@/components/ExplanationPanel";
import type { Explanation } from "@/lib/types";
import { PREDICTION } from "./testUtils";

describe("ExplanationPanel", () => {
  it("shows an honest unavailable state and never invents factors", () => {
    render(<ExplanationPanel explanation={{ status: "unavailable", reason: "Retrain to enable explanations." }} />);
    expect(screen.getByText("Explanation unavailable")).toBeInTheDocument();
    expect(screen.getByText(/Retrain to enable explanations/)).toBeInTheDocument();
    expect(screen.queryByText(/Factors raising/)).not.toBeInTheDocument();
  });

  it("renders reason codes, factors and the scale caveat", () => {
    render(<ExplanationPanel explanation={PREDICTION.explanation as Explanation} />);
    expect(screen.getByText(/raised the model's risk score/)).toBeInTheDocument();
    expect(screen.getByText("+0.050")).toBeInTheDocument();
    expect(screen.getByText(/not percentage-point changes/)).toBeInTheDocument();
  });

  it("handles empty factor lists", () => {
    const empty = { ...PREDICTION.explanation, top_risk_increasing: [], top_risk_reducing: [], reason_codes: [] } as Explanation;
    render(<ExplanationPanel explanation={empty} />);
    expect(screen.getByText(/No single input moved/)).toBeInTheDocument();
    expect(screen.getAllByText("None found for this case.")).toHaveLength(2);
  });

  it("hides the technical reviewer section unless full detail is present", () => {
    render(<ExplanationPanel explanation={PREDICTION.explanation as Explanation} />);
    expect(screen.queryByText(/Technical details/)).not.toBeInTheDocument();
  });
});
