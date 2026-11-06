import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, getJson, postJson } from "@/lib/api";
import { mockFetch } from "./testUtils";

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("returns parsed JSON on success", async () => {
    mockFetch({ "/ok": () => ({ body: { a: 1 } }) });
    expect(await getJson("/ok")).toEqual({ a: 1 });
  });

  it("turns FastAPI validation arrays into a readable message", async () => {
    mockFetch({ "/bad": () => ({ status: 422, body: { detail: [{ loc: ["body", "tenure_months"], msg: "Input should be >= 3" }] } }) });
    await expect(postJson("/bad", {})).rejects.toMatchObject({ kind: "http", status: 422, message: "tenure_months: Input should be >= 3" });
  });

  it("uses string detail for other HTTP errors", async () => {
    mockFetch({ "/down": () => ({ status: 503, body: { detail: "Model artifact not found." } }) });
    await expect(getJson("/down")).rejects.toMatchObject({ status: 503, message: "Model artifact not found." });
  });

  it("reports an unreachable backend clearly", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const err = (await getJson("/x").catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.kind).toBe("network");
    expect(err.message).toMatch(/Cannot reach the API/);
  });
});
