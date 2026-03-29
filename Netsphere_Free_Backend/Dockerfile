# Backend Dockerfile
FROM python:3.11-slim

WORKDIR /app

ARG TERRAFORM_VERSION=1.8.5

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    gcc \
    libffi-dev \
    libssl-dev \
    iputils-ping \
    nmap \
    unzip \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" -o /tmp/terraform.zip \
    && unzip /tmp/terraform.zip -d /usr/local/bin \
    && chmod +x /usr/local/bin/terraform \
    && rm -f /tmp/terraform.zip

# Copy dependency manifests first for caching
COPY requirements.txt requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
