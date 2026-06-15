# Remndrs container — runs the Flask app + APScheduler in one process.
# Multi-arch base, so this builds natively on x86-64 and on arm64 boards
# (Raspberry Pi, NVIDIA Jetson, etc.). All deps ship aarch64 wheels, so no
# compiler/Rust toolchain is needed.
FROM python:3.11-slim

# tzdata lets TIMEZONE pinning (time.tzset) resolve IANA zones inside the
# container — without it reminders fire on UTC wall-clock time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first so code changes don't bust the dependency layer cache.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code (local state + secrets are excluded via .dockerignore).
COPY . .

ENV PYTHONUNBUFFERED=1 \
    PORT=3000 \
    NOTES_FOLDER=/app/notes

# Created so they exist even before volumes mount; persisted via volumes.
RUN mkdir -p /app/data /app/uploads /app/notes

EXPOSE 3000

# app.py starts the scheduler (reminders/digest/calendar) AND the web server,
# binds 0.0.0.0, and honours $PORT. Run exactly one instance — the scheduler is
# in-process, so multiple workers would double-fire reminders.
CMD ["python3", "app.py"]
