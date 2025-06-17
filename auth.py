import os
import sys
from playwright.sync_api import sync_playwright, Page, TimeoutError
from dotenv import load_dotenv

# --- Login Function (Saves auth after a fixed wait) ---
def perform_login(page: Page, username: str, password: str, auth_file_path: str):
    """
    Handles the first-time login and saves the auth state after a fixed wait,
    as instructed, to avoid getting stuck.
    """
    print("\n--- Auth file not found. Starting first-time login process... ---")
    page.goto("https://typefully.com/", wait_until="domcontentloaded")

    login_button = page.locator('button:has-text("Log in with X")').first
    login_button.wait_for(state="visible", timeout=15000)
    
    with page.expect_popup() as popup_info:
        login_button.click()

    popup_page = popup_info.value
    popup_page.wait_for_load_state()
    print("...Popup opened. Authenticating...")

    # Full, correct login flow within the popup
    popup_page.locator("#allow").click(timeout=15000)
    popup_page.get_by_label("Phone, email, or username").fill(username)
    popup_page.get_by_role("button", name="Next").click()
    try:
        popup_page.get_by_test_id("ocfEnterTextTextInput").fill(username, timeout=5000)
        popup_page.get_by_role("button", name="Next").click()
    except TimeoutError:
        pass
    popup_page.locator('input[name="password"]').fill(password)
    popup_page.get_by_test_id("LoginForm_Login_Button").click()
    popup_page.get_by_role("button", name="Authorize app").click(timeout=15000)
    
    print("...Authorization submitted. Waiting for popup to close...")
    popup_page.wait_for_event("close", timeout=60000)
    print("...Popup closed.")
    
    # Instead of waiting for a flaky selector, we wait for a fixed period.
    print("Authorization complete. Waiting for a fixed 3 seconds for the main page to process the login...")
    page.wait_for_timeout(3000)
    
    # Save the session state immediately and move on.
    print(f"Saving reusable authentication state to '{auth_file_path}' NOW.")
    page.context.storage_state(path=auth_file_path)


# --- Main Execution Block ---
if __name__ == "__main__":
    load_dotenv()
    AUTH_FILE = "auth.json"
    
    X_USERNAME = os.getenv("X_USERNAME")
    X_PASSWORD = os.getenv("X_PASSWORD")
    if not X_USERNAME or not X_PASSWORD:
        sys.exit("Error: Could not find X_USERNAME or X_PASSWORD in your .env file.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = None
        
        try:
            # The logic to correctly create the browser context is sound.
            context = browser.new_context()
            page = context.new_page()
            perform_login(page, X_USERNAME, X_PASSWORD, AUTH_FILE)

        except Exception as e:
            print(f"\nAn error occurred during the process: {e}")
            if 'page' in locals() and page:
                 page.screenshot(path="error.png")

        finally:
            if context:
                context.close()
            print("\nScript finished.")