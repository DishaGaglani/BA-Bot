# Use official lightweight Python image
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UPLOAD_DIR=/app/uploads

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend source code
COPY . .

# Create directories for uploads and data persistence
RUN mkdir -p /app/uploads /app/data

# Expose port 8000
EXPOSE 8000

# Start FastAPI application
# --proxy-headers/--forwarded-allow-ips: trust X-Forwarded-For so rate limiting sees
# real client IPs rather than the Nginx container's. Safe here because only the
# frontend (Nginx) container publishes a port; the backend isn't directly reachable.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
