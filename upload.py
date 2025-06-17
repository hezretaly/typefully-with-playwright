from playwright.sync_api import sync_playwright
import os
import json

posts = [
    "First post text [image.jpg]",
    "Second post text [image.jpg]",
    "Third post text [image.jpg]"
]

def automate_typefully(posts):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(storage_state='auth.json')
        page = context.new_page()
        page.goto('https://typefully.com')

        # 1. Start a new draft and wait for it to settle
        page.get_by_role("button", name="New draft").click()
        page.wait_for_selector('div[data-atom-index="0"]', timeout=15000)
        print("New draft editor loaded. Pausing for UI to settle.")
        page.wait_for_timeout(2000)

        # 2. Loop through each post
        for i, post_content in enumerate(posts):
            tweet_number = f"#{i + 1}"
            print(f"--- Starting Tweet {tweet_number} ---")
            
            tweet_container = page.locator(f'div[data-atom-index="{i}"]')

            image_tag = post_content.split('[')[1].replace(']', '').strip()
            image_path = os.path.join(os.getcwd(), image_tag)
            
            try:
                with page.expect_file_chooser(timeout=10000) as fc_info:
                    tweet_container.hover()
                    media_button_icon = tweet_container.locator('button:has(svg > rect[x="3"])')
                    media_button_icon.wait_for(state="visible", timeout=5000)
                    media_button_icon.click()
                    page.wait_for_timeout(500)
                    upload_menu_item = page.get_by_role("menuitem", name="Upload images or video")
                    upload_menu_item.click(force=True)
                
                file_chooser = fc_info.value
                file_chooser.set_files(image_path)
                print(f"File selected for Tweet {tweet_number}. Waiting for upload...")
                
                page.wait_for_timeout(5000)
                
                uploaded_image_preview = tweet_container.locator('img').nth(1)
                uploaded_image_preview.wait_for(state="visible", timeout=15000)
                print(f"Upload confirmed for Tweet {tweet_number}.")

            except Exception as e:
                print(f"Error during image upload for {tweet_number}: {e}")
                page.screenshot(path=f"error_media_{tweet_number}.png")
                raise

            text_to_type = post_content.split('[')[0].strip()
            try:
                # 1. Click the general text area to establish focus.
                text_area_container = tweet_container.locator('div[data-node-view-content]').first
                text_area_container.click()
                
                # 2. Add a pause to ensure the cursor is blinking and ready.
                page.wait_for_timeout(500)

                # 3. Use the main page keyboard to type into the focused element.
                page.keyboard.type(text_to_type, delay=50)

                print(f"Successfully typed text for Tweet {tweet_number}")
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
                print("Successfully added new tweet area.")

        # --- Publishing ---
        print("\n--- All tweets processed. Publishing Thread ---")
        
        page.get_by_role("button", name="Publish", exact=True).click()
        page.wait_for_timeout(1000)
        page.get_by_role("button", name="Publish now").click()
        
        print("Thread published successfully!")
        page.wait_for_timeout(5000)

        context.close()
        browser.close()

if __name__ == "__main__":

    # Below is how the auth keys looks like
    # auth_keys = {
    #     "lastLaunchDate": "date",
    #     "event-tracked:User Journey Callout Shown:latest-update": "true",
    #     "intercom.intercom-state-r0tm2ksd": "{}",
    #     "selectedDraftId": "{}",
    #     "writhread:auth": "{}",
    #     "leftSidebarOpen": "true"
    # }

    # And here's what the auth.json file looks like
    # storage_state = {
    #     "origins": [
    #         {
    #             "origin": "https://typefully.com",
    #             "localStorage": [
    #                 {"name": key, "value": str(value)} for key, value in auth_keys.items()
    #             ]
    #         }
    #     ]
    # }
    # with open('auth.json', 'w') as f:
    #     json.dump(storage_state, f)

    # make sure authentication data is saved to auth.json then
    # Run the automation
    automate_typefully(posts)