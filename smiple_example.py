from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=50)

    page = browser.new_page()
    page.goto('http://typefully.com')
    page.wait_for_selector('button:has-text("Log in with")')
    page.click('button:has-text("Log in with")')

    browser.close()
