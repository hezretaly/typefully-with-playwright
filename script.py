import os
import sys
from playwright.sync_api import sync_playwright, TimeoutError
from dotenv import load_dotenv

def perform_login(auth_file_path: str):
    """
    Handles the first-time login and saves the full, reusable auth state.
    """
    # 1. Load credentials from environment variables
    X_USERNAME = os.getenv("X_USERNAME")
    X_PASSWORD = os.getenv("X_PASSWORD")
    if not X_USERNAME or not X_PASSWORD:
        sys.exit("Error: Could not find X_USERNAME or X_PASSWORD in your .env file.")

    with sync_playwright() as p:
        # 2. Launch browser and create a new context
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 3. Navigate to Typefully homepage and wait for DOM to load
        page.goto("https://typefully.com/", wait_until="domcontentloaded")

        # 4. Find and click the 'Log in with X' button to trigger the login popup
        login_button = page.locator('button:has-text("Log in with X")').first
        login_button.wait_for(state="visible", timeout=15000)
        
        with page.expect_popup() as popup_info:
            login_button.click()

        # 5. Switch to the popup window for X/Twitter authentication
        popup_page = popup_info.value
        popup_page.wait_for_load_state()

        # 6. Click 'Allow' if prompted, then enter username
        popup_page.locator("#allow").click(timeout=15000)
        popup_page.get_by_label("Phone, email, or username").fill(X_USERNAME)
        popup_page.get_by_role("button", name="Next").click()
        try:
            # 7. Handle possible extra username confirmation step
            popup_page.get_by_test_id("ocfEnterTextTextInput").fill(X_USERNAME, timeout=5000)
            popup_page.get_by_role("button", name="Next").click()
        except TimeoutError:
            pass  # If the step is skipped, continue

        # 8. Enter password and submit
        popup_page.locator('input[name="password"]').fill(X_PASSWORD)
        popup_page.get_by_test_id("LoginForm_Login_Button").click()

        # 9. Authorize the app (if prompted)
        popup_page.get_by_role("button", name="Authorize app").click(timeout=15000)
        
        # 10. Wait for the popup to close, signaling completion of login
        popup_page.wait_for_event("close", timeout=60000)
        
        # 11 Authorization complete. Waiting 3 seconds for the main page to process login...
        page.wait_for_timeout(3000)
        
        # 12. Save the authenticated browser context for future sessions
        page.context.storage_state(path=auth_file_path)
    

def automate_typefully(posts):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(storage_state='auth.json')
        page = context.new_page()
        page.goto('https://typefully.com', timeout=0)

        page.wait_for_timeout(10000)

        # 1. Start a new draft and wait for it to settle
        page.get_by_role("button", name="New draft").click()
        page.wait_for_selector('div[data-atom-index="0"]', timeout=15000)
        page.wait_for_timeout(10000)

        # 2. Loop through each post
        for i, post_content in enumerate(posts):
            tweet_number = f"#{i + 1}"
            tweet_container = page.locator(f'div[data-atom-index="{i}"]')

            # --- UPLOAD IMAGE FIRST ---
            split_result = post_content.split('[')
            if len(split_result) > 1:
                image_tag = split_result[1].replace(']', '').strip()
                image_path = os.path.join(os.getcwd(), image_tag)
                try:
                    with page.expect_file_chooser(timeout=30000) as fc_info:
                        tweet_container.hover()
                        media_button_icon = tweet_container.locator('button:has(svg > rect[x="3"])')
                        media_button_icon.wait_for(state="visible", timeout=5000)
                        media_button_icon.click()
                        page.wait_for_timeout(1000)
                        upload_menu_item = page.get_by_role("menuitem", name="Upload images or video")
                        upload_menu_item.click(force=True)
                    
                    file_chooser = fc_info.value
                    file_chooser.set_files(image_path)
                    
                    uploaded_image_preview = tweet_container.locator('img').nth(1)
                    uploaded_image_preview.wait_for(state="visible", timeout=20000)

                except Exception as e:
                    print(f"Error during image upload for {tweet_number}: {e}")
                    page.screenshot(path=f"error_media_{tweet_number}.png")
                    raise
            
            # --- TEXT INPUT ---
            if len(split_result) > 1:
                text_to_type = post_content.split('[')[0].strip()
            else:
                text_to_type = post_content
            try:
                # 1. Click the general text area to establish focus.
                text_area_container = tweet_container.locator('div[data-node-view-content]').first
                text_area_container.click()
                
                # 2. Add a pause to ensure the cursor is blinking and ready.
                page.wait_for_timeout(500)

                # 3. Use the main page keyboard to type into the focused element.
                page.keyboard.type(text_to_type, delay=50)

            except Exception as e:
                print(f"Error typing text for {tweet_number}: {e}")
                page.screenshot(path=f"error_typing_{tweet_number}.png")
                raise

            # --- ADD A NEW TWEET ---
            if i < len(posts) - 1:
                add_tweet_button = tweet_container.locator('button:has(svg > path[d="M4 5H20"])')
                add_tweet_button.click()
                page.locator(f'div[data-atom-index="{i + 1}"]').wait_for(state="visible", timeout=10000)
                page.wait_for_timeout(1000)

        # --- Publishing ---
        
        page.get_by_role("button", name="Publish", exact=True).click()
        page.wait_for_timeout(5000)
        page.get_by_role("button", name="Publish now").click()
        
        page.wait_for_timeout(10000)

        context.close()
        browser.close()

# --- Main Execution Block ---
if __name__ == "__main__":
    load_dotenv()
    AUTH_FILE = "auth.json"
    posts = [
        "First post text [image.jpg]",
        "Second post text, without the media",
        "Third post text [image.jpg]"
    ]
    try:
        if os.path.isfile(AUTH_FILE):
            automate_typefully(posts)
        else:
            perform_login(AUTH_FILE)
    except Exception as e:
        print(f"\nAn error occurred during the process: {e}")
    finally:
        print("\nScript finished.")