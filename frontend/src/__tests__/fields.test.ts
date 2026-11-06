import { describe, expect, it } from "vitest";
import { LOAN_FIELDS, validateFields } from "@/lib/fields";

const GOOD = { monthly_income: "50000", loan_amount: "300000", tenure_months: "36", annual_interest_rate: "12", existing_emi: "0", age: "32", employment_years: "5", num_existing_loans: "0", credit_history_months: "48" };

describe("validateFields", () => {
  it("accepts valid input and converts to numbers", () => {
    const r = validateFields(LOAN_FIELDS, GOOD);
    expect(r.ok).toBe(true);
    expect(r.payload.monthly_income).toBe(50000);
  });
  it("flags missing, non-numeric, non-integer and out-of-range values", () => {
    const r = validateFields(LOAN_FIELDS, { ...GOOD, monthly_income: "", loan_amount: "abc", tenure_months: "2.5", age: "12" });
    expect(Object.keys(r.errors).sort()).toEqual(["age", "loan_amount", "monthly_income", "tenure_months"]);
  });
  it("sends null (not zero) when credit history is marked unknown", () => {
    const r = validateFields(LOAN_FIELDS, { ...GOOD, credit_history_months: "" }, { credit_history_months: true });
    expect(r.ok).toBe(true);
    expect(r.payload.credit_history_months).toBeNull();
  });
  it("requires a value or the unknown box for optional fields", () => {
    expect(validateFields(LOAN_FIELDS, { ...GOOD, credit_history_months: "" }).errors.credit_history_months).toBeDefined();
  });
});
