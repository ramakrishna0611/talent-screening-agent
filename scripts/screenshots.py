"""README screenshots with the locally installed Edge (run while the server is on port 8001)."""
from playwright.sync_api import sync_playwright
B = "http://127.0.0.1:8001"
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    page = b.new_page(viewport={"width": 1500, "height": 950})
    errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(B); page.wait_for_selector("#login-form"); page.wait_for_timeout(600); page.screenshot(path="docs/login.png")
    page.fill("#login-form [name=email]", "priya@kestrel.test"); page.fill("#login-form [name=password]", "Welcome@123")
    page.click("#login-form button[type=submit]"); page.wait_for_selector(".cand"); page.wait_for_timeout(500)
    page.click(".cand >> nth=0"); page.wait_for_selector(".sc-head"); page.click("details >> nth=0"); page.wait_for_timeout(300)
    page.screenshot(path="docs/dashboard.png")
    page.click("text=Sameer Khan"); page.wait_for_selector(".flag"); page.wait_for_timeout(300); page.screenshot(path="docs/injection.png")
    page.click("text=Rohit Sharma"); page.wait_for_selector(".decide"); page.click('.decide [data-d="SHORTLISTED"]')
    page.wait_for_selector("#mail-dialog[open]"); page.wait_for_timeout(300); page.screenshot(path="docs/email_preview.png"); page.click("#mail-cancel")
    page.click("#inbox-btn"); page.wait_for_selector("#inbox-dialog[open]"); page.wait_for_timeout(600); page.screenshot(path="docs/inbox.png")
    page.click("#inbox-close"); page.click(".switch"); page.click(".theme-btn >> nth=1"); page.wait_for_timeout(400)
    page.screenshot(path="docs/blind_dark.png")
    print("errors:", errs); b.close()
