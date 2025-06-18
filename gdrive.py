import os
import io
import logging
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

def download_and_read_gdrive_file(folder_url: str, filename: str) -> bytes | None:
    """Download a file from Google Drive, read its content, and clean up."""
    try:
        drive_service = get_drive_service()

        # Extract folder ID from URL
        parsed = urlparse(folder_url)
        folder_id = parsed.path.strip('/').split('/')[-1]
        if not folder_id or folder_id == 'folders':
            logger.error(f"Invalid folder URL: {folder_url}. Expected format: https://drive.google.com/drive/folders/<folder_id>")
            return None

        # Query for the file
        query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])

        if not files:
            logger.error(f"File '{filename}' not found in folder ID '{folder_id}'.")
            return None

        file_id = files[0]['id']
        script_dir = os.path.dirname(os.path.abspath(__file__))
        downloads_dir = os.path.join(script_dir, 'temp')
        os.makedirs(downloads_dir, exist_ok=True)
        output_path = os.path.join(downloads_dir, filename)

        # Download file
        request = drive_service.files().get_media(fileId=file_id)
        with io.FileIO(output_path, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                logger.info(f"Download progress: {int(status.progress() * 100)}%")

        # Read file content
        logger.info(f"File downloaded to: {output_path}")
        with open(output_path, 'rb') as f:
            content = f.read()
            logger.info(f"File content size: {len(content)} bytes")
            

        # Clean up
        os.remove(output_path)
        logger.info(f"Deleted temporary file: {output_path}")
        return content

    except Exception as e:
        logger.error(f"Error processing file '{filename}': {str(e)}")
        return None

if __name__ == "__main__":
    folder_url = "https://drive.google.com/drive/folders/<folder_id>" 
    filename = "image.jpg"  # Replace with your target filename
    content = download_and_read_gdrive_file(folder_url, filename)
    if content is None:
        logger.error("Failed to retrieve file content.")