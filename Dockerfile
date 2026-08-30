# The official Playwright image supplies Chromium and all of its system libraries.
FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY console ./console
COPY service ./service
# service/app.py serves web/index.html at "/"; without this the root is a 404.
COPY web ./web

# Parallax declares its own runtime dependencies, so this single install pulls
# Playwright, Pillow and google-genai. The base image supplies the browsers.
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
ENV PORT=8080
EXPOSE 8080

CMD ["python", "-m", "service.app"]
