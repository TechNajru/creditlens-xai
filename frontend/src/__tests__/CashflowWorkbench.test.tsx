import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CashflowWorkbench } from "@/components/CashflowWorkbench";
import { mockFetch } from "./testUtils";

afterEach(() => vi.unstubAllGlobals());

const CATEGORIES = { categories: [], credit: ["income_salary", "income_other", "credit_uncategorized"], debit: ["rent", "debit_uncategorized"] };
const PREVIEW = {
  stats: { rows_total: 3, rows_valid: 2, rows_with_errors: 1, duplicates_excluded: 0, issues_total: 1, errors_total: 1 },
  detected_mapping: {}, date_format: "%Y-%m-%d", truncated: false, note: "",
  issues: [{ row: 3, field: "amount", problem: "missing, non-numeric or zero amount", severity: "error" }],
  category_issues: [],
  transactions: [
    { key: "A1", row: 1, date: "2026-01-05", description: "UPI-SOMEONE", amount: 2000, direction: "credit", category: "credit_uncategorized", category_source: "default", confidence: "low" },
    { key: "A2", row: 2, date: "2026-01-06", description: "RENT PAYMENT", amount: 9000, direction: "debit", category: "rent", category_source: "supplied", confidence: "high" },
  ],
};
const csv = (name = "a.csv") => new File(["date,description,amount\n"], name, { type: "text/csv" });

describe("CashflowWorkbench", () => {
  it("starts empty with disabled actions", () => {
    mockFetch({ "/categories": () => ({ body: CATEGORIES }) });
    render(<CashflowWorkbench />);
    expect(screen.getByText("No file selected yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview file" })).toBeDisabled();
  });

  it("rejects non-CSV files before any upload", async () => {
    const fetchMock = mockFetch({ "/categories": () => ({ body: CATEGORIES }) });
    const user = userEvent.setup({ applyAccept: false });
    render(<CashflowWorkbench />);
    await user.upload(screen.getByLabelText(/Transaction CSV/), csv("statement.xlsx"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only .csv files are accepted.");
    expect(screen.getByRole("button", { name: "Preview file" })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledTimes(1); // categories only
  });

  it("previews, lists problems, shows uncertain rows and counts corrections", async () => {
    mockFetch({ "/categories": () => ({ body: CATEGORIES }), "/uploads/preview": () => ({ body: PREVIEW }) });
    const user = userEvent.setup();
    render(<CashflowWorkbench />);
    await user.upload(screen.getByLabelText(/Transaction CSV/), csv());
    await user.click(screen.getByRole("button", { name: "Preview file" }));
    expect(await screen.findByText(/2 of 3 rows are usable/)).toBeInTheDocument();
    expect(screen.getByText(/data row 3 · amount/)).toBeInTheDocument();
    expect(screen.getByText("UPI-SOMEONE")).toBeInTheDocument();
    expect(screen.queryByText("RENT PAYMENT")).not.toBeInTheDocument(); // high-confidence rows hidden by default
    await user.selectOptions(screen.getByLabelText("Category for row 1"), "income_other");
    expect(screen.getByRole("button", { name: /Apply 1 correction and refresh preview/ })).toBeInTheDocument();
  });

  it("shows an API failure", async () => {
    mockFetch({ "/categories": () => ({ body: CATEGORIES }), "/uploads/preview": () => ({ status: 422, body: { detail: "Missing required columns: ['date']" } }) });
    const user = userEvent.setup();
    render(<CashflowWorkbench />);
    await user.upload(screen.getByLabelText(/Transaction CSV/), csv());
    await user.click(screen.getByRole("button", { name: "Preview file" }));
    expect(await screen.findByText(/Missing required columns/)).toBeInTheDocument();
  });
});
