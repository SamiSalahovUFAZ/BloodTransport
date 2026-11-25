FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=5000 DATABASE_PATH=/data/transport.sqlite3
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --system transport \
    && useradd --system --gid transport transport \
    && install -d -o transport -g transport /data
COPY src ./src
USER transport
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c 'import os, urllib.request; urllib.request.urlopen("http://127.0.0.1:" + os.environ["PORT"] + "/health", timeout=3).close()'
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --access-logfile - src.app:app"]
