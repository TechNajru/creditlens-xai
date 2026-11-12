import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getJson, postJson, setCsrfToken } from "@/lib/api";
import { AuthProvider } from "@/components/AuthProvider";
import { LoginForm } from "@/components/LoginForm";
import { RegisterForm } from "@/components/RegisterForm";
import { RequireAuth } from "@/components/RequireAuth";
import { lastCall, mockFetch } from "./testUtils";

const nav = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav, usePathname: () => "/", useParams: () => ({}) }));

beforeEach(() => { nav.push.mockClear(); nav.replace.mockClear(); });
afterEach(() => { vi.unstubAllGlobals(); setCsrfToken(null); });

const ME = (role = "applicant", id = 1) => ({ user: { id, email: `${role}@example.com`, role }, csrf_token: "csrf-123" });

describe("API client security behaviour", () => {
  it("sends cookies, and the CSRF header only on non-GET requests", async () => {
    const f = mockFetch({ "/x": () => ({ body: {} }) });
    setCsrfToken("tok-1");
    await getJson("/x");
    await postJson("/x", { a: 1 });
    const get = (f.mock.calls[0] as unknown as [string, RequestInit])[1];
    const post = (f.mock.calls[1] as unknown as [string, RequestInit])[1];
    expect(get.credentials).toBe("include");
    expect(new Headers(get.headers).get("X-CSRF-Token")).toBeNull();
    expect(new Headers(post.headers).get("X-CSRF-Token")).toBe("tok-1");
    expect(new Headers(post.headers).get("Content-Type")).toBe("application/json");
    setCsrfToken(null);
    await postJson("/x", {});
    expect(new Headers((f.mock.calls[2] as unknown as [string, RequestInit])[1].headers).get("X-CSRF-Token")).toBeNull();
  });

  it("never puts the token in browser storage", async () => {
    mockFetch({ "/auth/me": () => ({ body: ME() }) });
    render(<AuthProvider><RequireAuth><p>secret page</p></RequireAuth></AuthProvider>);
    await screen.findByText("secret page");
    expect(JSON.stringify(window.localStorage)).not.toContain("csrf-123");
    expect(JSON.stringify(window.sessionStorage)).not.toContain("csrf-123");
  });

  it("turns structured validation problems into one readable message", async () => {
    mockFetch({ "/s": () => ({ status: 422, body: { detail: { message: "The application did not pass validation.", problems: ["Loan details are invalid: x"] } } }) });
    await expect(postJson("/s", {})).rejects.toMatchObject({ message: "The application did not pass validation. Loan details are invalid: x" });
  });
});

describe("RequireAuth", () => {
  it("shows a login prompt when nobody is logged in", async () => {
    mockFetch({ "/auth/me": () => ({ status: 401, body: { detail: "Please log in." } }) });
    render(<AuthProvider><RequireAuth><p>secret page</p></RequireAuth></AuthProvider>);
    expect(screen.getByText("Checking your session…")).toBeInTheDocument();
    expect(await screen.findByText("Please log in")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
    expect(screen.queryByText("secret page")).not.toBeInTheDocument();
  });

  it("blocks a role that is not allowed", async () => {
    mockFetch({ "/auth/me": () => ({ body: ME("applicant") }) });
    render(<AuthProvider><RequireAuth roles={["admin"]}><p>admin only</p></RequireAuth></AuthProvider>);
    expect(await screen.findByText("Not permitted")).toBeInTheDocument();
    expect(screen.queryByText("admin only")).not.toBeInTheDocument();
  });

  it("explains a network failure instead of pretending to be logged out", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    render(<AuthProvider><RequireAuth><p>x</p></RequireAuth></AuthProvider>);
    expect(await screen.findByText(/Cannot reach the API/)).toBeInTheDocument();
  });
});

describe("LoginForm", () => {
  const setup = () => {
    const user = userEvent.setup();
    render(<AuthProvider><LoginForm /></AuthProvider>);
    return user;
  };
  const fill = async (user: ReturnType<typeof userEvent.setup>) => {
    await user.type(screen.getByLabelText("Email"), "a@example.com");
    await user.type(screen.getByLabelText("Password"), "correct-horse-battery-1");
    await user.click(screen.getByRole("button", { name: "Log in" }));
  };

  it("does not call the API with empty fields", async () => {
    const f = mockFetch({ "/auth/me": () => ({ status: 401, body: {} }) });
    const user = setup();
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByText("Enter your email and password.")).toBeInTheDocument();
    expect(f.mock.calls.filter(([u]) => String(u).includes("/auth/login"))).toHaveLength(0);
  });

  it("shows the generic server error", async () => {
    mockFetch({ "/auth/me": () => ({ status: 401, body: {} }), "POST /auth/login": () => ({ status: 401, body: { detail: "Invalid email or password." } }) });
    const user = setup();
    await fill(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
    expect(nav.push).not.toHaveBeenCalled();
  });

  it.each([["applicant", "/dashboard"], ["reviewer", "/review"], ["admin", "/admin"]])("sends a %s to %s after login", async (role, dest) => {
    mockFetch({ "/auth/me": () => ({ status: 401, body: {} }), "POST /auth/login": () => ({ body: ME(role) }) });
    const user = setup();
    await fill(user);
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith(dest));
  });

  it("uses the CSRF token from the login response on the next unsafe request", async () => {
    const f = mockFetch({ "/auth/me": () => ({ status: 401, body: {} }), "POST /auth/login": () => ({ body: ME("applicant") }), "POST /next": () => ({ body: {} }) });
    const user = setup();
    await fill(user);
    await waitFor(() => expect(nav.push).toHaveBeenCalled());
    await postJson("/next", {});
    expect(new Headers(lastCall(f, "POST", "/next").init.headers).get("X-CSRF-Token")).toBe("csrf-123");
  });
});

describe("RegisterForm", () => {
  const NOTICE = { version: "2026-11-v1", text: "CreditLens XAI is an educational prototype." };
  const setup = () => {
    const user = userEvent.setup();
    render(<AuthProvider><RegisterForm /></AuthProvider>);
    return user;
  };

  it("shows the data-use notice and requires acceptance", async () => {
    const f = mockFetch({ "/auth/me": () => ({ status: 401, body: {} }), "/consent/notice": () => ({ body: NOTICE }), "POST /auth/register": () => ({ body: ME() }) });
    const user = setup();
    expect(await screen.findByText(/educational prototype/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText("Password"), "a-long-enough-password");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText(/must read and accept/)).toBeInTheDocument();
    expect(f.mock.calls.filter(([u]) => String(u).includes("/auth/register"))).toHaveLength(0);
  });

  it("rejects a short password before calling the API", async () => {
    mockFetch({ "/auth/me": () => ({ status: 401, body: {} }), "/consent/notice": () => ({ body: NOTICE }) });
    const user = setup();
    await screen.findByText(/educational prototype/);
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText("Password"), "short");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText(/at least 10 characters \(a short phrase/)).toBeInTheDocument();
  });

  it("registers with the accepted notice version and goes to the dashboard", async () => {
    const f = mockFetch({ "/auth/me": () => ({ status: 401, body: {} }), "/consent/notice": () => ({ body: NOTICE }), "POST /auth/register": () => ({ status: 201, body: ME() }) });
    const user = setup();
    await screen.findByText(/educational prototype/);
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText("Password"), "a-long-enough-password");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/dashboard"));
    expect(lastCall(f, "POST", "/auth/register").body).toEqual({ email: "new@example.com", password: "a-long-enough-password", accept_notice_version: "2026-11-v1" });
  });

  it("shows server-side errors such as a duplicate email", async () => {
    mockFetch({ "/auth/me": () => ({ status: 401, body: {} }), "/consent/notice": () => ({ body: NOTICE }), "POST /auth/register": () => ({ status: 409, body: { detail: "An account with this email already exists." } }) });
    const user = setup();
    await screen.findByText(/educational prototype/);
    await user.type(screen.getByLabelText("Email"), "dup@example.com");
    await user.type(screen.getByLabelText("Password"), "a-long-enough-password");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
  });
});
