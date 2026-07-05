FROM python:3.12-slim

WORKDIR /srv/sitepilot

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "fastapi>=0.110" "uvicorn>=0.29" "pyjwt>=2.8" "bcrypt>=4.1" \
    "python-multipart>=0.0.9" "email-validator>=2.1" "reportlab>=4.1" \
    "psycopg[binary]>=3.1" "vercel_blob>=0.4"

COPY app ./app
COPY public ./public

ENV DATA_DIR=/data PORT=8000
VOLUME /data
EXPOSE 8000

# Seed runs only if the database is empty, then the API + SPA start.
CMD ["sh", "-c", "python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
