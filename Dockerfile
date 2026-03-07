FROM python:3.11-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y build-essential libpq-dev ffmpeg curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y libpq-dev ffmpeg && rm -rf /var/lib/apt/lists/*
COPY --from=builder /install /usr/local
COPY . .
RUN adduser --disabled-password --gecos '' flaskuser && chown -R flaskuser:flaskuser /app
USER flaskuser
ENV FLASK_APP=wsgi.py
ENV GUNICORN_CMD_ARGS="--config gunicorn.conf.py"
CMD ["gunicorn", "wsgi:app"]
