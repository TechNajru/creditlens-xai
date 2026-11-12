import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AdminConsole } from "@/components/AdminConsole";
import { AuthProvider } from "@/components/AuthProvider";
import { ReviewDetail } from "@/components/ReviewDetail";
import { ReviewQueue } from "@/components/ReviewQueue";
import { setCsrfToken } from "@/lib/api";
import { lastCall, mockFetch, PREDICTION } from "./testUtils";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }), usePathname: () => "/", useParams: () => ({}) }));

beforeEach(() => setCsrfToken("csrf-1"));
afterEach(() => { vi.unstubAllGlobals(); setCsrfToken(null); });

const INPUTS = { monthly_income: 40000, loan_amount: 1200000, tenure_months: 36, annual_interest_rate: 14, existing_emi: 15000, age: 27, employment_years: 2, num_existing_loans: 2, credit_history_months: null };
const POLICY = { policy_version: "demo-policy-1.0", passes: false, rules: [
  { rule: "simulated default probability at or below limit", threshold: 0.2, value: 0.92, passed: false },
  { rule: "total EMI as a share of income at or below limit", threshold: 0.5, value: 1.4, passed: false }] };
const DETAIL = (over: object = {}) => ({
  id: "abc", status: "manual_review", created_at: "2026-11-06T09:00:00Z", updated_at: "2026-11-06T09:00:00Z", submitted_at: "2026-11-06T10:00:00Z",
  loan_amount: 1200000, tenure_months: 36, probability: 0.92, decision: null, applicant_ref: "U7", loan_inputs: INPUTS,
  review_reasons: [{ code: "demo_policy_all_cases_reviewed", message: "Demonstration policy: every submission is reviewed by a human." },
    { code: "credit_history_unknown", message: "Credit history length is unknown (not treated as zero)." }],
  input_quality: { credit_history: "unknown", cashflow_provided: false, cashflow_sufficient: null, upload_rows_with_errors: null, upload_duplicates_excluded: null, low_confidence_value_share: null },
  upload: null, transactions: [], cashflow: null,
  assessment: { id: 1, is_preview: false, created_at: "2026-11-06T10:00:00Z", model_version: "sim-test-v1", feature_schema_version: "1.0.0", policy_version: "demo-policy-1.0", policy_result: POLICY, result: PREDICTION },
  preview_assessments: 1, policy_recommendation: "demo_declined", info_requests: [], decisions: [],
  timeline: [{ id: 1, ts: "2026-11-06T10:00:00Z", actor_role: "applicant", action: "application.status_changed", details: { status_to: "manual_review" } }], ...over,
});

describe("ReviewQueue", () => {
  const ROW = { ...DETAIL(), id: "r1", review_reason_codes: ["demo_policy_all_cases_reviewed", "credit_history_unknown"], policy_passes: false };
  it("lists pseudonymous applicants and re-queries when the filter changes", async () => {
    const f = mockFetch({ "/reviews/queue": () => ({ body: { applications: [ROW] } }) });
    const user = userEvent.setup();
    render(<ReviewQueue />);
    expect(screen.getByText("Loading the queue…")).toBeInTheDocument();
    expect(await screen.findByText("U7")).toBeInTheDocument();
    expect(screen.getByText("rules not met")).toBeInTheDocument();
    expect(screen.getByText("credit_history_unknown")).toBeInTheDocument();           // routine reason is not repeated on every row
    expect(screen.getByRole("link", { name: "Review U7" })).toHaveAttribute("href", "/review/r1");
    await user.click(screen.getByRole("tab", { name: "Decided" }));
    await waitFor(() => expect(String(lastCall(f, "GET", "/reviews/queue").url)).toContain("status=final_demo_decision"));
  });
  it("has empty and error states", async () => {
    mockFetch({ "/reviews/queue": () => ({ body: { applications: [] } }) });
    const { unmount } = render(<ReviewQueue />);
    expect(await screen.findByText("Nothing in this list.")).toBeInTheDocument();
    unmount();
    mockFetch({ "/reviews/queue": () => ({ status: 403, body: { detail: "You do not have permission for this action." } }) });
    render(<ReviewQueue />);
    expect(await screen.findByRole("alert")).toHaveTextContent("do not have permission");
  });
});

describe("ReviewDetail", () => {
  const open = async () => {
    const user = userEvent.setup();
    const state = { d: DETAIL() };
    const f = mockFetch({
      "POST /request-info": () => { state.d = DETAIL({ status: "info_requested" }); return { body: state.d }; },
      "POST /decision": () => { state.d = DETAIL({ status: "final_demo_decision" }); return { body: state.d }; },
      "GET /api/v1/reviews/abc": () => ({ body: state.d }),
    });
    render(<ReviewDetail id="abc" />);
    await screen.findByText("Applicant U7");
    return { user, f };
  };

  it("shows reasons, input quality, versions and the policy recommendation, but no email", async () => {
    await open();
    expect(screen.getByText(/every submission is reviewed by a human/)).toBeInTheDocument();
    expect(screen.getByText("Credit history length is unknown (not treated as zero).")).toBeInTheDocument();
    expect(screen.getAllByText("sim-test-v1").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("declined", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText(/✗ total EMI as a share of income/)).toBeInTheDocument();
    expect(screen.getByText("Model output (separate from your decision)")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/@example\.com/);
  });

  it("requires an override reason when the decision differs from the recommendation", async () => {
    const { user, f } = await open();
    expect(screen.queryByLabelText(/Override reason/)).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Decision"), "demo_approved");
    expect(screen.getByLabelText(/Override reason \(required\)/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Reasoning"), "Savings evidence supports approval.");
    await user.click(screen.getByRole("button", { name: "Record decision" }));
    expect(await screen.findByText(/differs from the policy recommendation \(declined\)/)).toBeInTheDocument();
    expect(f.mock.calls.filter(([, i]) => (i as RequestInit | undefined)?.method === "POST")).toHaveLength(0);
    await user.type(screen.getByLabelText(/Override reason/), "Applicant showed offline savings evidence.");
    await user.click(screen.getByRole("button", { name: "Record decision" }));
    expect(await screen.findByText(/No action available/)).toBeInTheDocument();
    expect(lastCall(f, "POST", "/decision").body).toEqual({ decision: "demo_approved", reason: "Savings evidence supports approval.", override_reason: "Applicant showed offline savings evidence." });
    expect(new Headers(lastCall(f, "POST", "/decision").init.headers).get("X-CSRF-Token")).toBe("csrf-1");
  });

  it("needs no override when following the recommendation", async () => {
    const { user, f } = await open();
    await user.selectOptions(screen.getByLabelText("Decision"), "demo_declined");
    expect(screen.queryByLabelText(/Override reason/)).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Reasoning"), "Fails both demonstration rules.");
    await user.click(screen.getByRole("button", { name: "Record decision" }));
    await screen.findByText(/No action available/);
    expect(lastCall(f, "POST", "/decision").body).toEqual({ decision: "demo_declined", reason: "Fails both demonstration rules.", override_reason: null });
  });

  it("validates the decision form before sending", async () => {
    const { user, f } = await open();
    await user.click(screen.getByRole("button", { name: "Record decision" }));
    expect(await screen.findByText("Choose a decision.")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Decision"), "demo_declined");
    await user.type(screen.getByLabelText("Reasoning"), "short");
    await user.click(screen.getByRole("button", { name: "Record decision" }));
    expect(await screen.findByText(/at least 10 characters/)).toBeInTheDocument();
    expect(f.mock.calls.filter(([, i]) => (i as RequestInit | undefined)?.method === "POST")).toHaveLength(0);
  });

  it("requests information with a minimum-length question", async () => {
    const { user, f } = await open();
    await user.type(screen.getByLabelText("Question for the applicant"), "too short");
    await user.click(screen.getByRole("button", { name: "Request information" }));
    expect(await screen.findByText(/Write at least 10 characters/)).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Question for the applicant"));
    await user.type(screen.getByLabelText("Question for the applicant"), "Please confirm your employment length.");
    await user.click(screen.getByRole("button", { name: "Request information" }));
    expect(await screen.findByText(/No action available/)).toBeInTheDocument();
    expect(lastCall(f, "POST", "/request-info").body).toEqual({ message: "Please confirm your employment length." });
  });

  it("shows server rejections (for example a double decision)", async () => {
    mockFetch({ "POST /decision": () => ({ status: 409, body: { detail: "A decision cannot be recorded while the application is 'final_demo_decision'." } }), "GET /api/v1/reviews/abc": () => ({ body: DETAIL() }) });
    const user = userEvent.setup();
    render(<ReviewDetail id="abc" />);
    await screen.findByText("Applicant U7");
    await user.selectOptions(screen.getByLabelText("Decision"), "demo_declined");
    await user.type(screen.getByLabelText("Reasoning"), "Fails both demonstration rules.");
    await user.click(screen.getByRole("button", { name: "Record decision" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("cannot be recorded");
  });

  it("closes the forms once the case is decided", async () => {
    mockFetch({ "GET /api/v1/reviews/abc": () => ({ body: DETAIL({ status: "final_demo_decision", decisions: [{ id: 1, decision: "demo_approved", reason: "Meets demo rules.", created_at: "x", policy_recommendation: "demo_declined", is_override: true, override_reason: "Offline savings." }] }) }) });
    render(<ReviewDetail id="abc" />);
    expect(await screen.findByText(/No action available/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record decision" })).not.toBeInTheDocument();
    expect(screen.getByText(/OVERRIDE of declined: Offline savings\./)).toBeInTheDocument();
  });

  it("reports a missing application", async () => {
    mockFetch({ "GET /api/v1/reviews/abc": () => ({ status: 403, body: { detail: "You cannot review your own application." } }) });
    render(<ReviewDetail id="abc" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("own application");
  });
});

describe("AdminConsole", () => {
  const USERS = { users: [
    { id: 1, email: "admin@demo.local", role: "admin", is_active: true, created_at: "x", applications: 0 },
    { id: 2, email: "alice@example.com", role: "applicant", is_active: true, created_at: "x", applications: 3 }] };
  const MODELS = { models: [
    { id: 1, track: "simulation", version: "sim-a", artifact_sha256: "a".repeat(64), is_active: true, registered_at: "x", activated_at: "x", summary: { trained_at_utc: "2026-11-01T00:00:00+00:00" } },
    { id: 2, track: "simulation", version: "sim-b", artifact_sha256: "b".repeat(64), is_active: false, registered_at: "x", activated_at: null, summary: {} }] };
  const base = { "/auth/me": () => ({ body: { user: { id: 1, email: "admin@demo.local", role: "admin" }, csrf_token: "csrf-1" } }) };
  const setup = (routes: Record<string, () => { status?: number; body?: unknown }>) => {
    const f = mockFetch({ ...base, ...routes });
    const user = userEvent.setup();
    render(<AuthProvider><AdminConsole /></AuthProvider>);
    return { f, user };
  };

  it("lists users, protects the admin's own row and changes another user's role", async () => {
    const { f, user } = setup({ "PATCH /admin/users/2": () => ({ body: {} }), "/admin/users": () => ({ body: USERS }) });
    expect(await screen.findByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByLabelText("Role for admin@demo.local")).toBeDisabled();
    expect(screen.getByLabelText("Active: admin@demo.local")).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Role for alice@example.com"), "reviewer");
    expect(await screen.findByText(/must log in again/)).toBeInTheDocument();
    expect(lastCall(f, "PATCH", "/admin/users/2").body).toEqual({ role: "reviewer" });
  });

  it("creates a user and shows server-side password problems", async () => {
    const { user } = setup({ "POST /admin/users": () => ({ status: 422, body: { detail: "Password must be at least 10 characters." } }), "/admin/users": () => ({ body: USERS }) });
    await screen.findByText("alice@example.com");
    await user.type(screen.getByLabelText("New user email"), "rev@example.com");
    await user.type(screen.getByLabelText(/Password/), "short");
    await user.click(screen.getByRole("button", { name: "Create user" }));
    expect(await screen.findByText(/at least 10 characters/)).toBeInTheDocument();
  });

  it("activates a model version", async () => {
    const { f, user } = setup({ "POST /activate": () => ({ body: {} }), "/admin/models": () => ({ body: MODELS }), "/admin/users": () => ({ body: USERS }) });
    await user.click(await screen.findByRole("tab", { name: "Models" }));
    expect(await screen.findByText("sim-b")).toBeInTheDocument();
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Activate" }));
    expect(await screen.findByText("Activated sim-b.")).toBeInTheDocument();
    expect(lastCall(f, "POST", "/admin/models/2/activate").init.method).toBe("POST");
  });

  it("shows monitoring with its honest limits", async () => {
    const mon = { applications_by_status: { manual_review: 2 }, assessments: { official: 2, preview: 3, official_by_model_version: { "sim-a": 2 } },
      prediction_distribution: { n: 2, mean: 0.4, p10: 0.1, p50: 0.4, p90: 0.7, histogram_10_bins: [1, 0, 0, 0, 0, 0, 0, 1, 0, 0] },
      input_missingness: { submitted_applications: 2, credit_history_unknown_share: 0.5, no_cashflow_file_share: 1 }, review: { decisions: 0, approved_share: null, override_share: null },
      notes: ["Performance degradation cannot be measured without repayment outcomes, which this demonstration does not collect."] };
    const { user } = setup({ "/admin/monitoring": () => ({ body: mon }), "/admin/users": () => ({ body: USERS }) });
    await user.click(await screen.findByRole("tab", { name: "Monitoring" }));
    expect(await screen.findByText(/cannot be measured without repayment outcomes/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Histogram/ })).toBeInTheDocument();
    expect(screen.getByText(/credit history unknown: 50%/)).toBeInTheDocument();
  });

  it("reports an intact and a broken audit chain differently", async () => {
    let ok = true;
    const { user } = setup({ "/admin/audit/verify": () => ({ body: ok ? { ok: true, checked: 12, first_bad_event_id: null } : { ok: false, checked: 3, first_bad_event_id: 4 } }),
      "/admin/audit?": () => ({ body: { events: [] } }), "/admin/users": () => ({ body: USERS }) });
    await user.click(await screen.findByRole("tab", { name: "Audit" }));
    await user.click(await screen.findByRole("button", { name: "Verify audit chain" }));
    expect(await screen.findByText("Audit chain intact")).toBeInTheDocument();
    ok = false;
    await user.click(screen.getByRole("button", { name: "Verify audit chain" }));
    const broken = await screen.findByText("Audit chain BROKEN");
    expect(within(broken.closest("[role=alert]")!).getByText(/Event 4/)).toBeInTheDocument();
  });
});
