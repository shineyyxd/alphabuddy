FROM python:3.12-slim

WORKDIR /srv
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev || uv sync
COPY app ./app
COPY fixtures ./fixtures

ENV SQLITE_PATH=/srv/data/xbuddy.db
VOLUME /srv/data
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
