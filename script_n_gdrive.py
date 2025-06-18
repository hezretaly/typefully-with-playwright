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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Suppress file_cache warning
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

# Load environment variables
load_dotenv()

def get_drive_service():
    """Create Google Drive service with service account credentials from .env."""
    try:
        credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
        if not credentials_path:
            logger.error("GOOGLE_CREDENTIALS_PATH not set in .env file.")
            raise ValueError("Missing GOOGLE_CREDENTIALS_PATH")
        if not os.path.exists(credentials_path):
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
            logger.error(f"Invalid folder URL: {folder_url}. Expected format: https://drive.google.com/drive/folders/<folder_id>")
            return False

        query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        if not files:
            logger.error(f"File '{filename}' not found in folder ID '{folder_id}'.")
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
            logger.error(f"File '{filename}' not found in folder ID '{folder_id}'.")
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

def perform_login(auth_file_path: str):
    """
    Handles the first-time login and saves the full, reusable auth state.
    """
    X_USERNAME = os.getenv("X_USERNAME")
    X_PASSWORD = os.getenv("X_PASSWORD")
    if not X_USERNAME or not X_PASSWORD:
        sys.exit("Error: Could not find X_USERNAME or X_PASSWORD in your .env file.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto("https://typefully.com/", wait_until="domcontentloaded")
        login_button = page.locator('button:has-text("Log in with X")').first
        login_button.wait_for(state="visible", timeout=15000)
        
        with page.expect_popup() as popup_info:
            login_button.click()

        popup_page = popup_info.value
        popup_page.wait_for_load_state()

        popup_page.locator("#allow").click(timeout=15000)
        popup_page.get_by_label("Phone, email, or username").fill(X_USERNAME)
        popup_page.get_by_role("button", name="Next").click()
        try:
            popup_page.get_by_test_id("ocfEnterTextTextInput").fill(X_USERNAME, timeout=5000)
            popup_page.get_by_role("button", name="Next").click()
        except TimeoutError:
            pass

        popup_page.locator('input[name="password"]').fill(X_PASSWORD)
        popup_page.get_by_test_id("LoginForm_Login_Button").click()
        popup_page.get_by_role("button", name="Authorize app").click(timeout=15000)
        
        popup_page.wait_for_event("close", timeout=60000)
        page.wait_for_timeout(3000)
        page.context.storage_state(path=auth_file_path)
        browser.close()

def automate_typefully(posts, folder_url: str):
    """Automate Typefully posting with images downloaded from Google Drive."""
    # Initialize Google Drive service
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
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(storage_state='auth.json')
        page = context.new_page()
        page.goto('https://typefully.com')
        page.wait_for_timeout(10000)

        # Create downloads directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        downloads_dir = os.path.join(script_dir, 'downloads')
        os.makedirs(downloads_dir, exist_ok=True)

        # Start a new draft
        page.get_by_role("button", name="New draft").click()
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
                    page.screenshot(path=f"error_download_{tweet_number}.png")
                    sys.exit(1)

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

                    # Clean up downloaded image
                    os.remove(image_path)
                    logger.info(f"Deleted temporary file: {image_path}")

                except Exception as e:
                    logger.error(f"Error during image upload for {tweet_number}: {str(e)}")
                    page.screenshot(path=f"error_media_{tweet_number}.png")
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
    AUTH_FILE = "auth.json"
    folder_url = os.getenv("GOOGLE_DRIVE_FOLDER_URL")
    posts = [
        "First post text, which is nice [image.jpg]",
        "Second post text, without the media",
        "Third and last post text [image.jpg]"
    ]
    try:
        if not folder_url:
            logger.error("GOOGLE_DRIVE_FOLDER_URL not set in .env file.")
            sys.exit(1)
        if os.path.isfile(AUTH_FILE):
            automate_typefully(posts, folder_url)
        else:
            perform_login(AUTH_FILE)
    except Exception as e:
        logger.error(f"An error occurred during the process: {str(e)}")
    finally:
        logger.info("Script finished.")