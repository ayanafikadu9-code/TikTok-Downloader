# TikTok Download Bot (with 15s "watch ad" flow)

Files provided:
- bot.py            (you already created / provided)
- requirements.txt
- .env.example
- Dockerfile
- docker-compose.yml
- start.sh
- .gitignore

Quick setup (local)
1. Copy environment file:
   cp .env.example .env
   Edit `.env` and set BOT_TOKEN and HOST (HOST should be a public HTTPS URL reachable by users; for testing you can use ngrok).

2. Install Python deps (optional if using Docker):
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt

3. Run:
   ./start.sh
   or
   python bot.py

Using Docker (recommended for stability)
1. Build and start:
   docker compose up --build -d

2. The Flask ad page listens on port 5000 inside the container; map port 5000 to your host (docker-compose.yml already exposes it).

Important notes
- HOST must be a publicly reachable HTTPS URL so users can open the ad page from the Telegram client.
- Keep BOT_TOKEN secret. Do NOT commit .env to git.
- Telegram file size limits apply when sending videos to users. For large downloads consider uploading to S3 and sending users a link.
- This method only ensures the user opened the ad page and waited ~15s; it doesn't cryptographically prove the user watched an ad. Use proper ad providers if you need accurate ad impressions.
- Be careful about copyright and TikTok terms when downloading and redistributing videos.

Optional next steps I can do for you
- Add HMAC-signed short-lived tokens for job URLs (prevents reuse/leak).
- Add a simple /premium Flask page (the bot references a premium_url).
- Convert the ad flow to a Telegram Web App for tighter integration and signed init_data handling.
- Provide a Procfile or Heroku-specific instructions.

If you want one of those, tell me which and I’ll add it next.
