FROM python:3.11-slim

# Install Playwright dependencies
RUN apt-get update && apt-get install -y \
    libnss3 libxss1 libasound2 libatk-bridge2.0-0 libgtk-3-0 libgbm-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY ../requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY docker_run.py .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]