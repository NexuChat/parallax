# The official Playwright image supplies Chromium and all of its system libraries.
FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY console ./console
COPY service ./service

# Parallax's optional Gemini lens needs google-genai; Pillow composes mosaics.
RUN pip install --no-cache-dir Pillow google-genai .

ENV PYTHONUNBUFFERED=1
ENV PORT=8080
EXPOSE 8080

CMD ["python", "-m", "service.app"]
