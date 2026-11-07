FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd -u 1000 -M -s /usr/sbin/nologin app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py streak.py ./
COPY templates ./templates
COPY static ./static

ENV DB_PATH=/data/overcast.db
RUN mkdir -p /data && chown -R 1000:1000 /data /app

USER 1000:1000
EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
