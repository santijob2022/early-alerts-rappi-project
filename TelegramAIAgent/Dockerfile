FROM python:3.13-slim

WORKDIR /app

# Install build deps for packages that need compilation
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir hatchling && pip install --no-cache-dir .

COPY . .

CMD ["python", "-m", "app.main"]
