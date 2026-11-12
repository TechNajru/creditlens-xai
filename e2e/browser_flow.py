"""Optional browser end-to-end test: register -> application -> upload -> preview -> submit -> reviewer decision -> outcome -> admin audit.

Setup (one time):   pip install playwright   then   playwright install chromium
Run backend + frontend first (see README), then from the repo root:
    python e2e/browser_flow.py <reviewer-password> <admin-password>
The two passwords are the ones printed by `python -m app.admin init`. Use a FRESH database: the script registers najrudeen.demo@example.com.
Not run on Windows by the author; verified on Linux with Chromium."""
import re, sys, json
from playwright.sync_api import sync_playwright, expect

REV_PW, ADM_PW = sys.argv[1], sys.argv[2]
import os
CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sample_data", "SYNTHETIC_salaried_stable.csv")
APPLICANT, APW = "najrudeen.demo@example.com", "a-long-demo-password-1"
BASE = os.environ.get("CREDITLENS_WEB", "http://localhost:3000")

def login(pg, email, pw):
    pg.goto(f"{BASE}/login"); pg.get_by_label("Email").fill(email); pg.get_by_label("Password").fill(pw)
    pg.get_by_role("button", name="Log in").click()

def logout(pg):
    pg.get_by_role("button", name="Log out").click(); pg.wait_for_url(f"{BASE}/")

with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1150, "height": 900}); pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    # logged out: protected page asks to log in
    pg.goto(f"{BASE}/dashboard"); expect(pg.get_by_text("Please log in")).to_be_visible(timeout=15000)
    print("1 logged-out dashboard ->", "login prompt shown")

    # register through the UI (consent notice)
    pg.goto(f"{BASE}/register"); expect(pg.get_by_text(re.compile("educational prototype")).first).to_be_visible(timeout=15000)
    pg.get_by_label("Email").fill(APPLICANT); pg.get_by_label("Password").fill(APW); pg.get_by_role("checkbox").check()
    os.makedirs("e2e/screenshots", exist_ok=True); pg.screenshot(path="e2e/screenshots/1_register.png")
    pg.get_by_role("button", name="Create account").click(); pg.wait_for_url(f"{BASE}/dashboard", timeout=15000)
    expect(pg.get_by_text(re.compile("No applications yet"))).to_be_visible()
    print("2 registered, dashboard empty state")

    # cookie + storage security as seen by the browser
    ck = next(c for c in ctx.cookies() if c["name"] == "creditlens_session")
    print("3 cookie httpOnly:", ck["httpOnly"], "| sameSite:", ck["sameSite"], "| JS can read it:", "creditlens_session" in pg.evaluate("document.cookie"),
          "| localStorage keys:", pg.evaluate("Object.keys(localStorage)"), "| sessionStorage keys:", pg.evaluate("Object.keys(sessionStorage)"))

    # create draft, upload CSV, correct a category, preview, submit
    pg.get_by_role("link", name="New application").click(); pg.get_by_role("button", name=re.compile("moderate burden")).click()
    pg.get_by_role("button", name="Create draft").click(); pg.wait_for_url(re.compile(r".*/applications/[0-9a-f-]{36}$"), timeout=15000)
    app_url = pg.url
    pg.get_by_label(re.compile("Transaction CSV")).set_input_files(CSV)
    expect(pg.get_by_text(re.compile(r"\d+ of \d+ rows were usable"))).to_be_visible(timeout=15000)
    sel = pg.locator("select[aria-label^='Category for row']").first
    sel.select_option(index=1); pg.wait_for_timeout(1200)
    print("4 uploaded:", pg.get_by_text(re.compile(r"rows usable")).first.inner_text()[:90])
    pg.get_by_role("button", name="Run a preview assessment").click()
    expect(pg.get_by_text("Why the model gave this result")).to_be_visible(timeout=20000)
    print("5 preview probability:", pg.locator("section[aria-labelledby=result-heading] p.text-4xl").inner_text(), "| reasons:", pg.locator("ul.list-disc li").all_inner_texts()[:2])
    os.makedirs("e2e/screenshots", exist_ok=True); pg.screenshot(path="e2e/screenshots/2_application.png", full_page=True)
    pg.get_by_role("checkbox", name=re.compile("I understand")).check(); pg.get_by_role("button", name="Submit for review").click()
    expect(pg.get_by_text("This application is locked")).to_be_visible(timeout=20000)
    print("6 submitted; status badge:", pg.get_by_text("In human review").first.inner_text(), "| form locked:", pg.get_by_label("Requested loan amount").is_disabled())
    logout(pg)

    # reviewer
    login(pg, "reviewer@demo.local", REV_PW); pg.wait_for_url(f"{BASE}/review", timeout=15000)
    expect(pg.get_by_role("link", name=re.compile("^Review U"))).to_be_visible(timeout=15000)
    print("7 reviewer queue row:", pg.locator("tbody tr").first.inner_text().replace("\n", " | ")[:140])
    pg.get_by_role("link", name=re.compile("^Review U")).click(); expect(pg.get_by_text(re.compile("^Applicant U"))).to_be_visible(timeout=15000)
    rec = pg.locator("dt:has-text('Policy recommendation') + dd").inner_text().strip()
    print("8 reviewer sees recommendation:", rec, "| email visible to reviewer:", APPLICANT in pg.content())
    pg.locator("details", has_text="Technical details").locator("summary").click(); pg.wait_for_timeout(700)
    os.makedirs("e2e/screenshots", exist_ok=True); pg.screenshot(path="e2e/screenshots/3_review.png", full_page=True)
    pg.locator("#rv-decision").select_option("demo_approved" if rec == "approved" else "demo_declined")
    pg.locator("#rv-reason").fill("Follows the demonstration policy recommendation.")
    pg.get_by_role("button", name="Record decision").click(); expect(pg.get_by_text(re.compile("No action available"))).to_be_visible(timeout=15000)
    print("9 decision recorded")
    pg.goto(f"{BASE}/admin"); expect(pg.get_by_text("Not permitted")).to_be_visible(timeout=15000)
    print("10 reviewer opening /admin ->", "Not permitted")
    logout(pg)

    # applicant sees the outcome
    login(pg, APPLICANT, APW); pg.wait_for_url(f"{BASE}/dashboard", timeout=15000)
    expect(pg.get_by_text("Demo decision recorded")).to_be_visible(timeout=15000)
    pg.get_by_role("link", name=re.compile("Open application")).click(); expect(pg.get_by_text(re.compile("Demonstration decision:"))).to_be_visible(timeout=15000)
    print("11 applicant outcome:", pg.get_by_text(re.compile("Demonstration decision:")).first.inner_text(), "| override info visible:", "override" in pg.content().lower())
    os.makedirs("e2e/screenshots", exist_ok=True); pg.screenshot(path="e2e/screenshots/4_outcome.png", full_page=True)
    logout(pg)

    # admin
    login(pg, "admin@demo.local", ADM_PW); pg.wait_for_url(f"{BASE}/admin", timeout=15000)
    pg.get_by_role("tab", name="Audit").click(); pg.get_by_role("button", name="Verify audit chain").click()
    expect(pg.get_by_text("Audit chain intact")).to_be_visible(timeout=15000)
    print("12 admin audit:", pg.get_by_text(re.compile("events checked")).inner_text())
    pg.get_by_role("tab", name="Models").click(); expect(pg.get_by_text("ACTIVE").first).to_be_visible(timeout=15000)
    pg.get_by_role("tab", name="Monitoring").click(); expect(pg.get_by_text(re.compile("cannot be measured without repayment outcomes"))).to_be_visible(timeout=15000)
    os.makedirs("e2e/screenshots", exist_ok=True); pg.screenshot(path="e2e/screenshots/5_admin.png", full_page=True)
    pg.goto(app_url); expect(pg.get_by_role("alert")).to_be_visible(timeout=15000)
    print("13 admin opening an application ->", pg.get_by_role("alert").first.inner_text().replace("\n", " ")[:80])
    print("browser console/page errors:", errors[:5])
    b.close()
