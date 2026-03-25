FROM python:3.12-slim

# System deps for Playwright / Chromium
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium for Playwright
RUN playwright install chromium --with-deps

# Copy app
COPY . .

# Create reports dir
RUN mkdir -p reports

# Environment defaults
ENV PORT=8080
ENV SECRET_KEY=change-me-in-production
ENV MAX_JOBS=3
ENV JOB_TTL_HOURS=24

EXPOSE 8080

# Run with gunicorn (2 sync workers; Playwright runs in threads)
CMD gunicorn -w 2 --threads 4 -b 0.0.0.0:${PORT} \
    --timeout 300 \
    --keep-alive 5 \
    "app:app"
