# Production Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (ffmpeg for pydub)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application
COPY . .

# Production server
EXPOSE 5000
# Single worker for in-memory job state, long timeout for SSE
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--timeout", "300", "app:app"]
