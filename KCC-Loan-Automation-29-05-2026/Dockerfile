FROM python:3.11-slim-bookworm

# ── System packages: Chrome + virtual display + noVNC ────────────────
RUN apt-get update && apt-get install -y \
    wget gnupg2 curl \
    xvfb x11vnc novnc websockify \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# ── Chrome wrapper: injects --no-sandbox without touching Python code ─
RUN mv /usr/bin/google-chrome-stable /usr/bin/google-chrome-real
COPY chrome-wrapper.sh /usr/bin/google-chrome-stable
RUN chmod +x /usr/bin/google-chrome-stable

WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application source ────────────────────────────────────────────────
COPY src/    ./src/
COPY config/ ./config/
COPY start.sh .
RUN chmod +x start.sh

RUN mkdir -p /app/uploads

EXPOSE 5000 6080

CMD ["./start.sh"]
