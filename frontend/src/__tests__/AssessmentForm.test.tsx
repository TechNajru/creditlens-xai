import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AssessmentForm } from "@/components/AssessmentForm";
import { LOAN_CONFIG } from "@/lib/fields";
import { mockFetch, PREDICTION } from "./testUtils";

afterEach(() => vi.unstubAllGlobals());
const setup = () => { const user = userEvent.setup(); render(<AssessmentForm config={LOAN_CONFIG} />); return user; };
const loadExample = (user: ReturnType<typeof userEvent.setup>) => user.click(screen.getByRole("button", { name: /Example: moderate burden/ }));
const submit = (user: ReturnType<typeof userEvent.setup>) => user.click(screen.getByRole("button", { name: /Run assessment/ }));

describe("AssessmentForm", () => {
  it("starts with an empty state and a prototype notice", () => {
    setup();
    expect(screen.getByText(/No result yet/)).toBeInTheDocument();
    expect(screen.getByText(/SYNTHETIC data/)).toBeInTheDocument();
  });

  it("blocks submission and shows field errors when inputs are invalid", async () => {
    const fetchMock = mockFetch({});
    const user = setup();
    await submit(user);
    expect(await screen.findByText(/Please fix the highlighted fields/)).toBeInTheDocument();
    expect(screen.getAllByText("This field is required.").length).toBeGreaterThan(3);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the result, provenance and explanation on success", async () => {
    const fetchMock = mockFetch({ "/api/v1/assessments/predict": () => ({ body: PREDICTION }) });
    const user = setup();
    await loadExample(user);
    await submit(user);
    expect(await screen.findByText("12.3%")).toBeInTheDocument();
    expect(screen.getByText(/Simulated default probability/)).toBeInTheDocument();
    expect(screen.getByText(/loan-approval probability/)).toBeInTheDocument();
    expect(screen.getByText(PREDICTION.data_provenance)).toBeInTheDocument();
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(init.body as string).monthly_income).toBe(50000);
  });

  it("sends null for unknown credit history", async () => {
    const fetchMock = mockFetch({ "/api/v1/assessments/predict": () => ({ body: PREDICTION }) });
    const user = setup();
    await user.click(screen.getByRole("button", { name: /heavy burden, no history/ }));
    await submit(user);
    await screen.findByText("12.3%");
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(init.body as string).credit_history_months).toBeNull();
  });

  it("shows an API error and no stale result", async () => {
    mockFetch({ "/api/v1/assessments/predict": () => ({ status: 503, body: { detail: "Model artifact not found. Train it first." } }) });
    const user = setup();
    await loadExample(user);
    await submit(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("Model artifact not found");
    expect(screen.queryByText("12.3%")).not.toBeInTheDocument();
  });

  it("explains a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const user = setup();
    await loadExample(user);
    await submit(user);
    expect(await screen.findByText(/Cannot reach the API/)).toBeInTheDocument();
  });

  it("shows a loading state while waiting and disables resubmission", async () => {
    let release: (v: Response) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((res) => { release = res; })));
    const user = setup();
    await loadExample(user);
    await submit(user);
    expect(await screen.findByText(/Running the model and computing the explanation/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Assessing…" })).toBeDisabled();
    release(new Response(JSON.stringify(PREDICTION), { status: 200 }));
    expect(await screen.findByText("12.3%")).toBeInTheDocument();
  });

  it("still shows the prediction when the explanation is unavailable", async () => {
    const body = { ...PREDICTION, explanation: { status: "unavailable", reason: "No background." } };
    mockFetch({ "/api/v1/assessments/predict": () => ({ body }) });
    const user = setup();
    await loadExample(user);
    await submit(user);
    expect(await screen.findByText("12.3%")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Explanation unavailable")).toBeInTheDocument());
  });
});
