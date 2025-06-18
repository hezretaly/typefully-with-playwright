import os
import io
import sys
import logging
from playwright.sync_api import sync_playwright, TimeoutError
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.service_account import Credentials
from urllib.parse import urlparse
from dotenv import load_dotenv
from retrying import retry

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Suppress file_cache warning
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

# Load environment variables
load_dotenv()

# Custom exception for login failures
class LoginError(Exception):
    pass

def get_drive_service():
    """Create Google Drive service with service account credentials."""
    try:
        credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
        if not credentials_path or not os.path.exists(credentials_path):
            logger.error(f"Credentials file not found: {credentials_path}")
            raise FileNotFoundError(f"Credentials file not found: {credentials_path}")

        scopes = ['https://www.googleapis.com/auth/drive']
        credentials = Credentials.from_service_account_file(credentials_path, scopes=scopes)
        return build('drive', 'v3', credentials=credentials, cache_discovery=False)
    except Exception as e:
        logger.error(f"Failed to authenticate with service account: {str(e)}")
        raise

def check_gdrive_file_exists(folder_url: str, filename: str, drive_service) -> bool:
    """Check if a file exists in the specified Google Drive folder."""
    try:
        parsed = urlparse(folder_url)
        folder_id = parsed.path.strip('/').split('/')[-1]
        if not folder_id or folder_id == 'folders':
            logger.error(f"Invalid folder URL: {folder_url}")
            return False

        query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        if not files:
            logger.error(f"File '{filename}' not found in folder ID '{folder_id}'")
            return False
        return True
    except Exception as e:
        logger.error(f"Error checking file '{filename}' in Google Drive: {str(e)}")
        return False

def download_gdrive_file(folder_url: str, filename: str, output_path: str, drive_service) -> bool:
    """Download a file from Google Drive to the specified local path."""
    try:
        parsed = urlparse(folder_url)
        folder_id = parsed.path.strip('/').split('/')[-1]
        if not folder_id or folder_id == 'folders':
            logger.error(f"Invalid folder URL: {folder_url}")
            return False

        query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        if not files:
            logger.error(f"File '{filename}' not found in folder ID '{folder_id}'")
            return False

        file_id = files[0]['id']
        request = drive_service.files().get_media(fileId=file_id)
        with io.FileIO(output_path, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                logger.info(f"Download progress for '{filename}': {int(status.progress() * 100)}%")
        logger.info(f"File downloaded to: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Error downloading file '{filename}': {str(e)}")
        return False

@retry(stop_max_attempt_number=3, wait_fixed=2000)
def click_with_retry(locator, timeout):
    """Retry clicking a locator."""
    locator.click(timeout=timeout)

def perform_login(auth_file_path: str):
    """Handles the first-time login and saves the auth state."""
    X_USERNAME = os.getenv("X_USERNAME")
    X_PASSWORD = os.getenv("X_PASSWORD")
    if not X_USERNAME or not X_PASSWORD:
        logger.error("Missing X_USERNAME or X_PASSWORD in environment variables")
        raise LoginError("Login failed: X_USERNAME or X_PASSWORD not set in environment variables")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            page.goto("https://typefully.com/", wait_until="domcontentloaded")
            login_button = page.locator('button:has-text("Log in with X")').first
            try:
                login_button.wait_for(state="visible", timeout=15000)
            except TimeoutError:
                logger.error("Timeout waiting for login button to be visible")
                raise LoginError("Login failed: Timeout waiting for 'Log in with X' button")

            with page.expect_popup() as popup_info:
                try:
                    click_with_retry(login_button, timeout=15000)
                except Exception as e:
                    logger.error(f"Failed to click login button: {str(e)}")
                    raise LoginError(f"Login failed: Could not click 'Log in with X' button: {str(e)}")

            popup_page = popup_info.value
            popup_page.wait_for_load_state()

            try:
                click_with_retry(popup_page.locator("#allow"), timeout=15000)
            except Exception as e:
                logger.error(f"Failed to click 'Allow' button: {str(e)}")
                raise LoginError(f"Login failed: Could not click 'Allow' button: {str(e)}")

            popup_page.get_by_label("Phone, email, or username").fill(X_USERNAME)
            try:
                click_with_retry(popup_page.get_by_role("button", name="Next"), timeout=15000)
            except Exception as e:
                logger.error(f"Failed to click 'Next' button after username: {str(e)}")
                raise LoginError(f"Login failed: Could not click 'Next' after username: {str(e)}")

            try:
                popup_page.get_by_test_id("ocfEnterTextTextInput").fill(X_USERNAME, timeout=5000)
                click_with_retry(popup_page.get_by_role("button", name="Next"), timeout=15000)
            except TimeoutError:
                logger.info("No additional username verification required")
                pass

            popup_page.locator('input[name="password"]').fill(X_PASSWORD)
            try:
                click_with_retry(popup_page.get_by_test_id("LoginForm_Login_Button"), timeout=15000)
            except Exception as e:
                logger.error(f"Failed to click login button after password: {str(e)}")
                raise LoginError(f"Login failed: Could not click login button after password: {str(e)}")

            try:
                click_with_retry(popup_page.get_by_role("button", name="Authorize app"), timeout=15000)
            except Exception as e:
                logger.error(f"Failed to click 'Authorize app' button: {str(e)}")
                raise LoginError(f"Login failed: Could not click 'Authorize app' button: {str(e)}")

            try:
                popup_page.wait_for_event("close", timeout=60000)
            except TimeoutError:
                logger.error("Timeout waiting for popup to close")
                raise LoginError("Login failed: Popup did not close within timeout")

            page.wait_for_timeout(3000)
            try:
                page.context.storage_state(path=auth_file_path)
                logger.info(f"Saved auth state to {auth_file_path}")
            except Exception as e:
                logger.error(f"Failed to save auth state to {auth_file_path}: {str(e)}")
                raise LoginError(f"Login failed: Could not save auth state to {auth_file_path}: {str(e)}")

            browser.close()
    except Exception as e:
        logger.error(f"Unexpected error during login: {str(e)}")
        raise LoginError(f"Login failed due to unexpected error: {str(e)}")

def automate_typefully(posts, folder_url: str):
    """Automate Typefully posting with images downloaded from Google Drive."""
    try:
        drive_service = get_drive_service()
    except Exception as e:
        logger.error(f"Failed to initialize Google Drive service: {str(e)}")
        sys.exit(1)

    # Check if all image files exist in Google Drive
    for post_content in posts:
        split_result = post_content.split('[')
        if len(split_result) > 1:
            image_tag = split_result[1].replace(']', '').strip()
            if not check_gdrive_file_exists(folder_url, image_tag, drive_service):
                logger.error(f"Aborting: Image '{image_tag}' not found in Google Drive.")
                sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=os.getenv("AUTH_FILE_PATH", "/app/data/auth.json"))
        page = context.new_page()
        page.goto('https://typefully.com', timeout=0)
        page.wait_for_timeout(10000)

        # Create downloads directory
        downloads_dir = os.getenv("DOWNLOADS_DIR", "/app/data/downloads")
        os.makedirs(downloads_dir, exist_ok=True)

        # Start a new draft
        click_with_retry(page.get_by_role("button", name="New draft"), timeout=15000)
        page.wait_for_selector('div[data-atom-index="0"]', timeout=15000)
        page.wait_for_timeout(10000)

        # Loop through each post
        for i, post_content in enumerate(posts):
            tweet_number = f"#{i + 1}"
            tweet_container = page.locator(f'div[data-atom-index="{i}"]')

            # --- UPLOAD IMAGE FROM GOOGLE DRIVE ---
            split_result = post_content.split('[')
            if len(split_result) > 1:
                image_tag = split_result[1].replace(']', '').strip()
                image_path = os.path.join(downloads_dir, image_tag)
                
                # Download image from Google Drive
                if not download_gdrive_file(folder_url, image_tag, image_path, drive_service):
                    logger.error(f"Failed to download image '{image_tag}' for {tweet_number}. Aborting.")
                    page.screenshot(path=f"{downloads_dir}/error_download_{tweet_number}.png")
                    sys.exit(1)

                try:
                    with page.expect_file_chooser(timeout=30000) as fc_info:
                        tweet_container.hover()
                        media_button_icon = tweet_container.locator('button:has(svg > rect[x="3"])')
                        media_button_icon.wait_for(state="visible", timeout=5000)
                        click_with_retry(media_button_icon, timeout=5000)
                        page.wait_for_timeout(1000)
                        upload_menu_item = page.get_by_role("menuitem", name="Upload images or video")
                        click_with_retry(upload_menu_item, timeout=15000)
                    
                    file_chooser = fc_info.value
                    file_chooser.set_files(image_path)
                    
                    uploaded_image_preview = tweet_container.locator('img').nth(1)
                    uploaded_image_preview.wait_for(state="visible", timeout=20000)

                    # Clean up downloaded image
                    os.remove(image_path)
                    logger.info(f"Deleted temporary file: {image_path}")

                except Exception as e:
                    logger.error(f"Error during image upload for {tweet_number}: {str(e)}")
                    page.screenshot(path=f"{downloads_dir}/error_media_{tweet_number}.png")
                    raise

            # --- TEXT INPUT ---
            text_to_type = split_result[0].strip() if len(split_result) > 1 else post_content
            try:
                text_area_container = tweet_container.locator('div[data-node-view-content]').first
                text_area_container.click()
                page.wait_for_timeout(500)
                page.keyboard.type(text_to_type, delay=50)
            except Exception as e:
                logger.error(f"Error typing text for {tweet_number}: {str(e)}")
                page.screenshot(path=f"{downloads_dir}/error_typing_{tweet_number}.png")
                raise

            # --- ADD A NEW TWEET ---
            if i < len(posts) - 1:
                add_tweet_button = tweet_container.locator('button:has(svg > path[d="M4 5H20"])')
                click_with_retry(add_tweet_button, timeout=15000)
                page.locator(f'div[data-atom-index="{i + 1}"]').wait_for(state="visible", timeout=10000)
                page.wait_for_timeout(1000)

        # --- Publishing ---
        click_with_retry(page.get_by_role("button", name="Publish", exact=True), timeout=15000)
        page.wait_for_timeout(5000)
        click_with_retry(page.get_by_role("button", name="Publish now"), timeout=15000)
        page.wait_for_timeout(10000)

        context.close()
        browser.close()

if __name__ == "__main__":
    AUTH_FILE = os.getenv("AUTH_FILE_PATH", "/app/data/auth.json")
    folder_url = os.getenv("GOOGLE_DRIVE_FOLDER_URL")
    posts = [
        "First post text [image.jpg]",
        "Second post text, without the media",
        "Third post text [image.jpg]"
    ]
    try:
        if not folder_url:
            logger.error("GOOGLE_DRIVE_FOLDER_URL not set in .env file.")
            raise LoginError("Failed to initialize: GOOGLE_DRIVE_FOLDER_URL not set in environment variables")
        if os.path.isfile(AUTH_FILE):
            logger.info("Found auth.json, proceeding with Typefully automation.")
            automate_typefully(posts, folder_url)
        else:
            logger.info("No auth.json found, performing login.")
            perform_login(AUTH_FILE)
            if os.path.isfile(AUTH_FILE):
                logger.info("Login successful, auth.json created. Proceeding with Typefully automation.")
                automate_typefully(posts, folder_url)
            else:
                logger.error("Failed to create auth.json after login attempt.")
                raise LoginError("Login failed: auth.json was not created after login attempt")
    except LoginError as e:
        logger.error(f"Login error: {str(e)}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"An error occurred during the process: {str(e)}")
        sys.exit(1)
    finally:
        logger.info("Script finished.")