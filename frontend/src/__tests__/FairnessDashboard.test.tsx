import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ExperimentsPanel } from "@/components/ExperimentsPanel";
import { FairnessDashboard } from "@/components/FairnessDashboard";
import { mockFetch } from "./testUtils";

afterEach(() => vi.unstubAllGlobals());

const rate = (v: number, n: number, ok = true) => ({ value: v, ci95: [Math.max(0, v - 0.02), Math.min(1, v + 0.02)], n, reliable: ok });
const group = (name: string, n: number, reliable: boolean) => ({
  group: name, n, defaulters: Math.round(n * 0.2), non_defaulters: Math.round(n * 0.8), reliable,
  flagged_rate: rate(0.25, n), favourable_rate: rate(0.75, n), observed_default_rate: rate(0.22, n),
  false_positive_rate: rate(0.15, n, reliable), false_negative_rate: rate(0.45, n, reliable),
  mean_predicted_probability: 0.22, calibration_gap: 0.006, calibration_gap_reliable: reliable,
  warnings: reliable ? [] : [`small group (n=${n} < 100): estimates are unreliable`],
});
const SUMMARY = { computed: true, groups_included: ["a", "b"], groups_excluded_small: [], demographic_parity_difference: 0.054, demographic_parity_ratio: 0.8, equalized_odds_difference: 0.043, false_positive_rate_difference: 0.043, false_negative_rate_difference: 0.04 };
const REPORT = {
  model_version: "uci-test", data_provenance: "PUBLIC data", evaluated_on: "untouched test split", n_test: 4500,
  threshold: { value: 0.28, chosen_on: "validation split", criterion: "maximum F1", experimental: true },
  definitions: { positive_prediction: "The model flags the client as high default risk.", favourable_outcome: "Not flagged.", false_positive_rate: "Among clients who did NOT default, the share who were flagged." },
  label_note: "Group labels follow the UCI variable documentation.",
  limits: { min_group_n: 100, min_class_n: 30, intervals: "95% Wilson score intervals" },
  attributes: {
    SEX: { groups: [group("female", 2704, true), group("male", 1796, true)], summary: SUMMARY, warnings: [] },
    EDUCATION: { groups: [group("university", 2081, true), group("others", 20, false)], summary: { ...SUMMARY, groups_excluded_small: ["others"] }, warnings: ["small group"] },
  },
  mitigation: {
    attribute: "SEX", method: "Fairlearn ThresholdOptimizer", fit_on: "validation split", evaluated_on: "test split", deployed: false,
    implications: ["It needs each client's SEX at decision time. Using protected attributes may be unlawful in lending."],
    tradeoffs: [{ metric: "balanced_accuracy", baseline: 0.708, mitigated: 0.697 }, { metric: "equalized_odds_difference (SEX)", baseline: 0.0425, mitigated: 0.0385 }],
    mitigated: { calibration: "Not applicable: mitigated output is a randomized yes/no decision." },
  },
  caveats: ["No single metric proves fairness."],
};

describe("FairnessDashboard", () => {
  it("tells the user how to generate a missing report", async () => {
    mockFetch({ "/fairness/public": () => ({ status: 404, body: { detail: "Report not found" } }) });
    render(<FairnessDashboard />);
    expect(await screen.findByText(/python -m app\.fairness/)).toBeInTheDocument();
  });

  it("shows loading first, then definitions, intervals and the audit-only warning", async () => {
    mockFetch({ "/fairness/public": () => ({ body: REPORT }) });
    render(<FairnessDashboard />);
    expect(screen.getByText("Loading fairness report…")).toBeInTheDocument();
    expect(await screen.findByText(/Sensitive attributes — handle with care/)).toBeInTheDocument();
    expect(screen.getByText(/Age is a model input/)).toBeInTheDocument();
    expect(screen.getByText(/flags the client as high default risk/)).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /female 2,704/ })).toBeInTheDocument();
    expect(screen.getAllByText(/\(23\.0%–27\.0%\)/).length).toBeGreaterThan(0);   // 95% interval displayed
  });

  it("flags small groups as unreliable and lists them as excluded from the summary", async () => {
    mockFetch({ "/fairness/public": () => ({ body: REPORT }) });
    const user = userEvent.setup();
    render(<FairnessDashboard />);
    await user.click(await screen.findByRole("tab", { name: "Education" }));
    expect(screen.getByText(/Unreliable: small group \(n=20 < 100\)/)).toBeInTheDocument();
    expect(screen.getByText(/Excluded from the summary because they are too small: others/)).toBeInTheDocument();
  });

  it("presents the mitigation as an undeployed experiment with its implications", async () => {
    mockFetch({ "/fairness/public": () => ({ body: REPORT }) });
    render(<FairnessDashboard />);
    expect(await screen.findByRole("heading", { name: /not deployed/ })).toBeInTheDocument();
    expect(screen.getByText(/Using protected attributes may be unlawful/)).toBeInTheDocument();
    expect(screen.getByText(/Not applicable: mitigated output/)).toBeInTheDocument();
    const table = screen.getByRole("table", { name: /Baseline versus mitigated/ });
    expect(within(table).getByRole("row", { name: /equalized_odds_difference/ })).toHaveTextContent(/0\.04[23].*0\.03[89]/);
    expect(within(table).getByRole("row", { name: /balanced_accuracy/ })).toHaveTextContent(/70\.8%.*69\.7%/);
  });
});

describe("ExperimentsPanel", () => {
  const EXP = {
    label: "LIMITED-INFORMATION EXPERIMENT. Months are hidden from clients who actually have 6 months of history. This is not a validated thin-file evaluation.",
    data_provenance: "PUBLIC", evaluated_on: "untouched test split", n_test: 4500, recipe: "HGB + sigmoid; no selection among variants", baseline_constant_brier: 0.1722,
    caveats: ["Real thin-file applicants differ in unobserved ways."],
    variants: [
      { months_visible: 6, label: "Full history (6 months)", n_features: 23, roc_auc: 0.782, roc_auc_ci95: [0.766, 0.799], brier: 0.134, log_loss: 0.43, ece: 0.0066, roc_auc_change_vs_full: 0 },
      { months_visible: 0, label: "No payment history (limit + age only)", n_features: 2, roc_auc: 0.593, roc_auc_ci95: [0.575, 0.615], brier: 0.1693, log_loss: 0.5, ece: 0.0292, roc_auc_change_vs_full: -0.189 },
    ],
  };
  it("labels the experiment and shows every variant", async () => {
    mockFetch({ "/experiments": () => ({ body: EXP }) });
    render(<ExperimentsPanel />);
    expect(await screen.findByText(/not a validated thin-file evaluation/)).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /No payment history/ })).toHaveTextContent("0.593 (0.575–0.615)");
    expect(screen.getByRole("row", { name: /No payment history/ })).toHaveTextContent("-0.189");
  });
  it("shows a helpful message when not generated", async () => {
    mockFetch({ "/experiments": () => ({ status: 404, body: { detail: "nope" } }) });
    render(<ExperimentsPanel />);
    expect(await screen.findByText(/python -m app\.experiments/)).toBeInTheDocument();
  });
});
