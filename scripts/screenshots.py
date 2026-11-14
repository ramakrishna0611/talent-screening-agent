"""Screenshots of the dashboard with the locally installed Edge (no browser download)."""
from playwright.sync_api import sync_playwright
B = "http://127.0.0.1:8001"
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    page = b.new_page(viewport={"width": 1500, "height": 950}, color_scheme="light")
    errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(B); page.wait_for_selector("#org-form"); page.wait_for_timeout(700); page.screenshot(path="docs/login.png")
    page.fill("#org-form [name=code]", "KSTL01"); page.fill("#org-form [name=password]", "kestrel@2026"); page.click("#org-form button")
    page.wait_for_selector("#user-form:not([hidden])")
    page.fill("#user-form [name=email]", "priya@kestrel.test"); page.fill("#user-form [name=password]", "Welcome@123")
    page.click("#user-form button[type=submit]"); page.wait_for_selector(".cand"); page.wait_for_timeout(500)
    page.click(".cand >> nth=0"); page.wait_for_selector(".sc-head"); page.click("details >> nth=0"); page.wait_for_timeout(400)
    page.screenshot(path="docs/dashboard.png")
    page.click("text=Sameer Khan"); page.wait_for_selector(".flag"); page.wait_for_timeout(300)
    page.screenshot(path="docs/injection.png")
    page.click(".switch"); page.wait_for_timeout(200); page.click(".theme-btn >> nth=1"); page.wait_for_timeout(400)
    page.screenshot(path="docs/blind_dark.png")
    print("errors:", errs); b.close()
