import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApplicantDashboard } from "@/components/ApplicantDashboard";
import { ApplicationWorkflow } from "@/components/ApplicationWorkflow";
import { setCsrfToken } from "@/lib/api";
import { lastCall, mockFetch, PREDICTION } from "./testUtils";

const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav, usePathname: () => "/", useParams: () => ({}) }));

beforeEach(() => { nav.push.mockClear(); nav.replace.mockClear(); setCsrfToken("csrf-1"); });
afterEach(() => { vi.unstubAllGlobals(); setCsrfToken(null); });

const INPUTS = { monthly_income: 60000, loan_amount: 400000, tenure_months: 36, annual_interest_rate: 12, existing_emi: 6000, age: 32, employment_years: 5, num_existing_loans: 1, credit_history_months: 48 };
const POLICY = { policy_version: "demo-policy-1.0", passes: true, rules: [{ rule: "simulated default probability at or below limit", threshold: 0.2, value: 0.05, passed: true }] };
const UPLOAD = { filename: "statement.csv", size_bytes: 1000, rows_total: 10, rows_valid: 9, rows_with_errors: 1, duplicates_excluded: 0, date_format: "%Y-%m-%d", issues: [{ row: 4, field: "amount", problem: "missing, non-numeric or zero amount", severity: "error" }], uploaded_at: "2026-11-06T10:00:00Z" };
const TXS = {
  credit_categories: ["income_salary", "income_other", "credit_uncategorized"], debit_categories: ["rent", "debit_uncategorized"],
  transactions: [
    { id: 11, key: "T1", row: 1, date: "2026-02-01", description: "UPI-SOMEONE", amount: 2000, direction: "credit", category: "credit_uncategorized", category_source: "default", confidence: "low" },
    { id: 12, key: "T2", row: 2, date: "2026-02-05", description: "RENT PAYMENT", amount: 9000, direction: "debit", category: "rent", category_source: "rule", confidence: "medium" },
    { id: 13, key: "T3", row: 3, date: "2026-02-01", description: "SALARY ACME", amount: 60000, direction: "credit", category: "income_salary", category_source: "supplied", confidence: "high" },
  ],
};
const ASSESSMENT = (preview: boolean) => ({ id: 1, is_preview: preview, created_at: "2026-11-06T10:05:00Z", model_version: "sim-test-v1", feature_schema_version: "1.0.0", policy_version: "demo-policy-1.0", policy_result: POLICY, result: PREDICTION });
const app = (over: object = {}) => ({
  id: "abc", status: "draft", created_at: "2026-11-06T09:00:00Z", updated_at: "2026-11-06T09:00:00Z", submitted_at: null, loan_amount: 400000, tenure_months: 36,
  probability: null, decision: null, loan_inputs: INPUTS, upload: null, editable: true, assessment: null, info_requests: [], final_decision: null, timeline: [{ ts: "2026-11-06T09:00:00Z", action: "application.created", details: {} }], ...over,
});

/** A tiny fake server: `state.app` is what GET returns; handlers may change it. */
function server(state: { app: ReturnType<typeof app>; txs?: typeof TXS | null }, extra: Record<string, () => { status?: number; body?: unknown }> = {}) {
  return mockFetch({
    ...extra,
    "GET /api/v1/applications/abc/transactions": () => ({ body: state.txs ?? TXS }),
    "GET /api/v1/applications/abc/cashflow": () => ({ status: 404, body: { detail: "none" } }),
    "GET /api/v1/applications/abc": () => ({ body: state.app }),
  });
}

describe("ApplicantDashboard", () => {
  it("lists applications with status, probability and decision", async () => {
    mockFetch({ "/api/v1/applications": () => ({ body: { applications: [
      { ...app({ status: "manual_review", probability: 0.0512 }), id: "a1" }, { ...app({ status: "final_demo_decision", decision: "demo_approved" }), id: "a2" }] } }) });
    render(<ApplicantDashboard />);
    expect(screen.getByText("Loading your applications…")).toBeInTheDocument();
    expect(await screen.findByText("In human review")).toBeInTheDocument();
    expect(screen.getByText("5.1%")).toBeInTheDocument();
    expect(screen.getByText("approved")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Open application/ })[0]).toHaveAttribute("href", "/applications/a1");
  });
  it("has an empty state and an error state", async () => {
    mockFetch({ "/api/v1/applications": () => ({ body: { applications: [] } }) });
    const { unmount } = render(<ApplicantDashboard />);
    expect(await screen.findByText(/No applications yet/)).toBeInTheDocument();
    unmount();
    mockFetch({ "/api/v1/applications": () => ({ status: 401, body: { detail: "Session expired. Please log in again." } }) });
    render(<ApplicantDashboard />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Session expired");
  });
});

describe("ApplicationWorkflow — new application", () => {
  it("validates before creating and then redirects to the new draft", async () => {
    const f = mockFetch({ "POST /api/v1/applications": () => ({ status: 201, body: app({ id: "NEW1" }) }) });
    const user = userEvent.setup();
    render(<ApplicationWorkflow />);
    await user.click(screen.getByRole("button", { name: "Create draft" }));
    expect(await screen.findByText(/Please fix the highlighted fields/)).toBeInTheDocument();
    expect(f).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /moderate burden/ }));
    await user.click(screen.getByRole("button", { name: "Create draft" }));
    await vi.waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/applications/NEW1"));
    expect(lastCall(f, "POST", "/api/v1/applications").body).toMatchObject({ monthly_income: 50000, credit_history_months: 48 });
  });
});

describe("ApplicationWorkflow — editing a draft", () => {
  it("loads the draft, saves changes and warns that previews are discarded", async () => {
    const state = { app: app() };
    const f = server(state, { "PATCH /api/v1/applications/abc": () => { state.app = app({ loan_inputs: { ...INPUTS, loan_amount: 250000 } }); return { body: state.app }; } });
    const user = userEvent.setup();
    render(<ApplicationWorkflow id="abc" />);
    expect(screen.getByText("Loading application…")).toBeInTheDocument();
    const amount = await screen.findByLabelText("Requested loan amount");
    expect(amount).toHaveValue("400000");
    await user.clear(amount);
    await user.type(amount, "250000");
    await user.click(screen.getByRole("button", { name: "Save details" }));
    expect(await screen.findByText(/earlier preview was discarded/)).toBeInTheDocument();
    expect(lastCall(f, "PATCH", "/api/v1/applications/abc").body.loan_amount).toBe(250000);
    expect(new Headers(lastCall(f, "PATCH", "/api/v1/applications/abc").init.headers).get("X-CSRF-Token")).toBe("csrf-1");
  });

  it("sends null for an unknown credit history", async () => {
    const state = { app: app({ loan_inputs: { ...INPUTS, credit_history_months: null } }) };
    const f = server(state, { "PATCH /api/v1/applications/abc": () => ({ body: state.app }) });
    const user = userEvent.setup();
    render(<ApplicationWorkflow id="abc" />);
    await screen.findByLabelText("Requested loan amount");
    expect(screen.getByRole("checkbox", { name: /Unknown/ })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Save details" }));
    await screen.findByText(/Details saved/);
    expect(lastCall(f, "PATCH", "/api/v1/applications/abc").body.credit_history_months).toBeNull();
  });

  it("rejects non-CSV uploads without calling the API, and uploads valid files", async () => {
    const state = { app: app() };
    const f = server(state, { "POST /uploads": () => { state.app = app({ upload: UPLOAD }); return { status: 201, body: { upload: UPLOAD, category_issues: [], transactions: TXS.transactions, truncated: false } }; } });
    const user = userEvent.setup({ applyAccept: false });
    render(<ApplicationWorkflow id="abc" />);
    const input = await screen.findByLabelText(/Transaction CSV/);
    await user.upload(input, new File(["x"], "statement.xlsx"));
    expect(await screen.findByText("Only .csv files are accepted.")).toBeInTheDocument();
    expect(f.mock.calls.filter(([, i]) => (i as RequestInit | undefined)?.method === "POST")).toHaveLength(0);
    await user.upload(input, new File(["date,description,amount\n"], "statement.csv", { type: "text/csv" }));
    expect(await screen.findByText(/9 of 10 rows were usable/)).toBeInTheDocument();
    expect(screen.getByText(/data row 4 · amount/)).toBeInTheDocument();
    expect(screen.getByText("UPI-SOMEONE")).toBeInTheDocument();
    expect(screen.getByText("RENT PAYMENT")).toBeInTheDocument();             // medium confidence: still worth a look
    expect(screen.queryByText("SALARY ACME")).not.toBeInTheDocument();        // high confidence (supplied): hidden by default
  });

  it("lets the applicant correct a guessed category", async () => {
    const state = { app: app({ upload: UPLOAD }) };
    const f = server(state, { "PATCH /transactions/11": () => ({ body: {} }) });
    const user = userEvent.setup();
    render(<ApplicationWorkflow id="abc" />);
    await user.selectOptions(await screen.findByLabelText("Category for row 1"), "income_other");
    expect(lastCall(f, "PATCH", "/transactions/11").body).toEqual({ category: "income_other" });
  });

  it("runs a preview assessment and shows the result with its explanation", async () => {
    const state = { app: app() };
    server(state, { "POST /assessments/preview": () => { state.app = app({ assessment: ASSESSMENT(true) }); return { status: 201, body: {} }; } });
    const user = userEvent.setup();
    render(<ApplicationWorkflow id="abc" />);
    expect(await screen.findByText("No assessment yet.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run a preview assessment" }));
    expect(await screen.findByText("12.3%")).toBeInTheDocument();
    expect(screen.getByText(/Preview only: it is not sent to the reviewer/)).toBeInTheDocument();
    expect(screen.getByText("Why the model gave this result")).toBeInTheDocument();
  });
});

describe("ApplicationWorkflow — submission", () => {
  it("needs an explicit confirmation, then locks the application", async () => {
    const state = { app: app() };
    const f = server(state, { "POST /submit": () => { state.app = app({ status: "manual_review", editable: false, assessment: ASSESSMENT(false) }); return { body: state.app }; } });
    const user = userEvent.setup();
    render(<ApplicationWorkflow id="abc" />);
    const submit = await screen.findByRole("button", { name: "Submit for review" });
    expect(submit).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /I understand this is a demonstration/ }));
    expect(submit).toBeEnabled();
    await user.click(submit);
    expect(await screen.findByText("In human review")).toBeInTheDocument();
    expect(screen.getByText("This application is locked")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Submit for review/ })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Requested loan amount")).toBeDisabled();
    expect(screen.getByText(/Official assessment recorded at submission/)).toBeInTheDocument();
    expect(lastCall(f, "POST", "/submit").init.method).toBe("POST");
  });

  it("shows validation problems and keeps the draft editable", async () => {
    const state = { app: app() };
    server(state, { "POST /submit": () => ({ status: 422, body: { detail: { message: "The application did not pass validation.", problems: ["Loan details are invalid: loan_amount must be positive"] } } }) });
    const user = userEvent.setup();
    render(<ApplicationWorkflow id="abc" />);
    await user.click(await screen.findByRole("checkbox", { name: /I understand/ }));
    await user.click(screen.getByRole("button", { name: "Submit for review" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("loan_amount must be positive");
    expect(screen.getByLabelText("Requested loan amount")).toBeEnabled();
  });

  it("shows a 503 when no model is active", async () => {
    server({ app: app() }, { "POST /submit": () => ({ status: 503, body: { detail: "No active 'simulation' model version. An administrator must register and activate one." } }) });
    const user = userEvent.setup();
    render(<ApplicationWorkflow id="abc" />);
    await user.click(await screen.findByRole("checkbox", { name: /I understand/ }));
    await user.click(screen.getByRole("button", { name: "Submit for review" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("administrator must register");
  });
});

describe("ApplicationWorkflow — reviewer questions and decisions", () => {
  const asked = (answered: boolean) => app({ status: "info_requested", info_requests: [{ id: 5, message: "Please confirm your employment length.", created_at: "2026-11-06T11:00:00Z", response: answered ? "Five years." : null, responded_at: answered ? "2026-11-06T12:00:00Z" : null }], assessment: ASSESSMENT(false) });

  it("must answer the question before resubmitting", async () => {
    const state = { app: asked(false) };
    const f = server(state, { "POST /respond": () => { state.app = asked(true); return { body: state.app }; } });
    const user = userEvent.setup();
    render(<ApplicationWorkflow id="abc" />);
    expect(await screen.findByText("Please confirm your employment length.")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /I understand/ }));
    expect(screen.getByRole("button", { name: "Resubmit for review" })).toBeDisabled();
    await user.type(screen.getByLabelText("Your answer"), "Five years.");
    await user.click(screen.getByRole("button", { name: "Send answer" }));
    await vi.waitFor(() => expect(screen.getByRole("button", { name: "Resubmit for review" })).toBeEnabled());
    expect(lastCall(f, "POST", "/respond").body).toEqual({ message: "Five years." });
  });

  it("shows the final demonstration decision without reviewer-internal fields", async () => {
    server({ app: app({ status: "final_demo_decision", editable: false, assessment: ASSESSMENT(false), final_decision: { id: 1, decision: "demo_declined", reason: "Debt burden too high.", created_at: "2026-11-06T13:00:00Z" } }) });
    render(<ApplicationWorkflow id="abc" />);
    const card = (await screen.findByText(/Demonstration decision: declined/)).closest("section")!;
    expect(within(card).getByText(/Debt burden too high/)).toBeInTheDocument();
    expect(within(card).getByText(/not a real lending decision/)).toBeInTheDocument();
    expect(screen.queryByText(/override/i)).not.toBeInTheDocument();
  });
});

describe("ApplicationWorkflow — deletion and errors", () => {
  it("needs a second confirmation before deleting, then returns to the dashboard", async () => {
    const f = server({ app: app() }, { "DELETE /api/v1/applications/abc": () => ({ body: { deleted: true } }) });
    const user = userEvent.setup();
    render(<ApplicationWorkflow id="abc" />);
    await user.click(await screen.findByRole("button", { name: "Delete…" }));
    expect(f.mock.calls.some(([, i]) => (i as RequestInit | undefined)?.method === "DELETE")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Yes, delete permanently" }));
    await vi.waitFor(() => expect(nav.push).toHaveBeenCalledWith("/dashboard"));
  });

  it("cannot delete while the application is in review", async () => {
    server({ app: app({ status: "manual_review", editable: false }) });
    render(<ApplicationWorkflow id="abc" />);
    await screen.findByText("In human review");
    expect(screen.queryByRole("button", { name: "Delete…" })).not.toBeInTheDocument();
  });

  it("explains a missing or foreign application", async () => {
    mockFetch({ "GET /api/v1/applications/abc": () => ({ status: 404, body: { detail: "Application not found." } }) });
    render(<ApplicationWorkflow id="abc" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Application not found.");
  });
});
