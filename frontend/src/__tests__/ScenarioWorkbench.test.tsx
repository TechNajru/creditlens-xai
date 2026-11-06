import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ScenarioWorkbench } from "@/components/ScenarioWorkbench";
import { mockFetch } from "./testUtils";

afterEach(() => vi.unstubAllGlobals());

const INPUTS = { monthly_income: 40000, loan_amount: 1200000, tenure_months: 36, annual_interest_rate: 14, existing_emi: 15000, age: 27, employment_years: 2, num_existing_loans: 2, credit_history_months: null };
const POLICY = { version: "demo-policy-1.0", max_default_probability: 0.2, max_total_emi_to_income: 0.5, min_loan_amount: 10000, min_tenure_months: 6, max_tenure_months: 84, disclaimer: "Experimental demonstration thresholds." };
const ev = (over: object, prob: number, meets = false) => ({
  inputs: { ...INPUTS, ...over },
  metrics: { new_loan_emi: 41013, total_emi: 56013, total_emi_to_income: 1.4, total_interest: 276000, default_probability_simulated: prob },
  policy: { policy_version: "demo-policy-1.0", passes: meets, rules: [
    { rule: "simulated default probability at or below limit", threshold: 0.2, value: prob, passed: prob <= 0.2 },
    { rule: "total EMI as a share of income at or below limit", threshold: 0.5, value: 1.4, passed: meets }] },
  feasibility_issues: [], meets_policy: meets,
});
const ZERO = { new_loan_emi: 0, total_emi: 0, total_emi_to_income: 0, total_interest: 0, default_probability_simulated: 0 };
const UNCHANGED = ["monthly_income", "age", "employment_years", "num_existing_loans", "credit_history_months"];
const NOTES = ["Model-output changes are associations from a model trained on synthetic data, not proven causal effects.", "Real-world approval is not guaranteed. The policy here is an experimental demonstration."];
const SEARCH = { mutable_inputs: ["loan_amount", "tenure_months"], never_changed: UNCHANGED, ranking: "x", candidates_evaluated: 200, searched_range: { loan_amount: [300000, 1200000], tenure_months: [6, 84] } };

const WHATIF = {
  policy: POLICY, base: ev({}, 0.919), notes: NOTES,
  scenarios: [{ ...ev({ loan_amount: 500000 }, 0.31), name: "Smaller loan", changed_inputs: { loan_amount: { from: 1200000, to: 500000 } }, unchanged_inputs: ["tenure_months", ...UNCHANGED], hypothetical: [], delta_vs_base: { ...ZERO, default_probability_simulated: -0.609, total_interest: -150000 } }],
};
const ALT = (hyp: string[]) => ({
  ...ev({ loan_amount: 400000, tenure_months: 60, existing_emi: hyp.length ? 11250 : 15000 }, 0.18, true),
  changed_inputs: { loan_amount: { from: 1200000, to: 400000 }, tenure_months: { from: 36, to: 60 }, ...(hyp.length ? { existing_emi: { from: 15000, to: 11250 } } : {}) },
  unchanged_inputs: UNCHANGED, hypothetical: hyp, delta_vs_base: { ...ZERO, default_probability_simulated: -0.739, total_interest: 20000 }, change_cost: 0.9,
});

async function setup() {
  const user = userEvent.setup();
  render(<ScenarioWorkbench />);
  await user.click(screen.getByRole("button", { name: /heavy burden, no history/ }));
  return user;
}
const scenario1 = () => within(screen.getByRole("region", { name: "Scenario 1" }));

describe("ScenarioWorkbench — what-if", () => {
  it("offers only the allowed inputs in a scenario", async () => {
    await setup();
    const s = scenario1();
    expect(s.getByLabelText(/Loan amount/)).toBeInTheDocument();
    expect(s.getByLabelText(/Tenure/)).toBeInTheDocument();
    expect(s.getByLabelText(/Interest rate/)).toBeInTheDocument();
    expect(s.getByLabelText(/Existing monthly EMI \(hypothetical/)).toBeInTheDocument();
    for (const forbidden of [/Monthly income/, /Age/, /employment/i, /Number of existing loans/, /Credit history/]) {
      expect(s.queryByLabelText(forbidden)).not.toBeInTheDocument();
    }
  });

  it("compares scenarios, marks changed inputs and states the model-output caveat", async () => {
    const fetchMock = mockFetch({ "/scenarios/what-if": () => ({ body: WHATIF }) });
    const user = await setup();
    await user.type(scenario1().getByLabelText(/Loan amount/), "500000");
    await user.click(screen.getByRole("button", { name: "Compare scenarios" }));
    expect(await screen.findByRole("columnheader", { name: "Smaller loan" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Base" })).toBeInTheDocument();
    expect(screen.getByText("(changed)")).toBeInTheDocument();
    expect(screen.getByText(/−60.9 pts model output/)).toBeInTheDocument();
    expect(screen.getByText(/not proven causal effects/)).toBeInTheDocument();
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.scenarios[0]).toEqual({ name: "Scenario A", changes: { loan_amount: 500000 } });
    expect(body.application.monthly_income).toBe(40000);
    expect(body.application.credit_history_months).toBeNull();
    expect(body.policy).toEqual({ max_default_probability: 0.2, max_total_emi_to_income: 0.5 });
  });

  it("requires a change in every scenario before calling the API", async () => {
    const fetchMock = mockFetch({});
    const user = await setup();
    await user.click(screen.getByRole("button", { name: "Compare scenarios" }));
    expect(await screen.findByText(/at least one changed value/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("validates the base application first", async () => {
    const fetchMock = mockFetch({});
    const user = userEvent.setup();
    render(<ScenarioWorkbench />);
    await user.click(screen.getByRole("button", { name: "Compare scenarios" }));
    expect(await screen.findByText(/Please fix the highlighted fields/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows API errors", async () => {
    mockFetch({ "/scenarios/what-if": () => ({ status: 422, body: { detail: "These inputs cannot be changed in a scenario: ['age']" } }) });
    const user = await setup();
    await user.type(scenario1().getByLabelText(/Loan amount/), "500000");
    await user.click(screen.getByRole("button", { name: "Compare scenarios" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("cannot be changed");
  });
});

describe("ScenarioWorkbench — alternatives", () => {
  const CF = (status: string, extra: object) => ({ status, message: "msg", policy: POLICY, base: ev({}, 0.919), notes: NOTES, alternatives: [], closest_attempt: null, search: SEARCH, ...extra });

  it("lists alternatives with changed and unchanged inputs and trade-offs", async () => {
    const fetchMock = mockFetch({ "/scenarios/counterfactuals": () => ({ body: CF("found", { message: "Found 1 alternative(s) that meet every demonstration rule.", alternatives: [ALT([])] }) }) });
    const user = await setup();
    await user.click(screen.getByRole("button", { name: "Find alternatives" }));
    expect(await screen.findByText("Alternatives found")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Alternative 1" })).toBeInTheDocument();
    expect(screen.getByText(/Loan amount 12,00,000 → 4,00,000/)).toBeInTheDocument();
    expect(screen.getByText("Unchanged:").parentElement).toHaveTextContent("Monthly income");
    expect(screen.getByText(/Real-world approval is not guaranteed/)).toBeInTheDocument();
    expect(screen.queryByText(/Hypothetical: this assumes/)).not.toBeInTheDocument();
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(init.body as string).allow_hypothetical_debt_reduction).toBe(false);
  });

  it("labels debt reduction as hypothetical and sends the opt-in flag", async () => {
    const fetchMock = mockFetch({ "/scenarios/counterfactuals": () => ({ body: CF("found", { alternatives: [ALT(["existing_emi"])] }) }) });
    const user = await setup();
    await user.click(screen.getByRole("checkbox", { name: /hypothetical reductions in existing EMI/ }));
    await user.click(screen.getByRole("button", { name: "Find alternatives" }));
    expect(await screen.findByText(/Hypothetical: this assumes you actually reduce existing debt/)).toBeInTheDocument();
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(init.body as string).allow_hypothetical_debt_reduction).toBe(true);
  });

  it("says plainly when no feasible alternative exists", async () => {
    mockFetch({ "/scenarios/counterfactuals": () => ({ body: CF("no_feasible_alternative", { message: "No alternative within the allowed changes meets every demonstration rule.", closest_attempt: { ...ALT([]), meets_policy: false } }) }) });
    const user = await setup();
    await user.click(screen.getByRole("button", { name: "Find alternatives" }));
    expect(await screen.findByText("No feasible alternative")).toBeInTheDocument();
    expect(screen.getByText(/No alternative within the allowed changes/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Closest attempt \(does not pass\)/ })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Alternative 1" })).not.toBeInTheDocument();
  });

  it("reports when the request already meets the policy", async () => {
    mockFetch({ "/scenarios/counterfactuals": () => ({ body: CF("already_meets_policy", { message: "The requested terms already meet every demonstration rule. No alternative is needed." }) }) });
    const user = await setup();
    await user.click(screen.getByRole("button", { name: "Find alternatives" }));
    expect(await screen.findByText("No change needed")).toBeInTheDocument();
  });
});
