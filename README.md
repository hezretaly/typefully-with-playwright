# Typefully Automation Script

A Python script to automate posting to Typefully using Playwright for browser automation. Supports login with X credentials and posting drafts with optional images.

## Prerequisites
- Python 3.13
- Install dependencies: `pip install playwright python-dotenv`
- Run `playwright install` to install browsers
- Create a `.env` file with `X_USERNAME` and `X_PASSWORD`

## Setup
1. Clone the repository
2. Install requirements: `pip install -r requirements.txt`
3. Configure `.env` with your X credentials

## Usage
Run the script:
```bash
python script.py
```
The script:
1. Checks for an existing `auth.json` file
2. If absent, performs login and saves authentication state
3. If present, uses saved state to post drafts

## Features
- **Login Automation**: Logs into Typefully via X, saving auth state to `auth.json`
- **Post Automation**: Creates drafts, supports text and image uploads, and publishes posts
- **Error Handling**: Captures screenshots on errors for debugging.

## Post Format
Define posts in the `posts` list:
```py
posts = [
    "Post text [image.jpg]",  # Text with optional image
    "Post text without media",
]
```
- Images must be in the script
- Use `[image_name]` to include an image

## Notes
- Runs in non-headless mode for visibility
- Ensure valid X credentials and image paths
- Screenshots are saved on errors as `error_*.png`
- images should be in same directory as the `script.py`

## License
MIT License