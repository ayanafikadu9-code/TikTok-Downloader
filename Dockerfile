# Minimal container for the bot. Builds Python image, installs ffmpeg and Python deps.
FROM python:3.11-slim

# Install ffmpeg (used by yt-dlp for merging/converting)
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency file and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

ENV PYTHONUNBUFFERED=1

# Expose Flask port (used for ad page)
EXPOSE 5000

# Default command; in production you may run inside a process manager
CMD ["python", "bot.py"]
