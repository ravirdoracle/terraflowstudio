FROM python:3.12-slim

WORKDIR /app

# Install curl (for healthcheck), unzip (for Terraform)
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Terraform
ARG TERRAFORM_VERSION=1.14.9
RUN curl -fsSL "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_$(dpkg --print-architecture).zip" \
    -o /tmp/terraform.zip \
    && unzip /tmp/terraform.zip -d /usr/local/bin/ \
    && rm /tmp/terraform.zip \
    && terraform version

# Install OpenTofu
ARG OPENTOFU_VERSION=1.9.0
RUN curl -fsSL "https://github.com/opentofu/opentofu/releases/download/v${OPENTOFU_VERSION}/tofu_${OPENTOFU_VERSION}_linux_$(dpkg --print-architecture).zip" \
    -o /tmp/tofu.zip \
    && unzip /tmp/tofu.zip -d /usr/local/bin/ \
    && rm /tmp/tofu.zip \
    && tofu version

# Install Python dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application code
COPY . .

# Create data directory for FileStore fallback
RUN mkdir -p /app/data

LABEL org.opencontainers.image.title="Terraflow Studio" \
      org.opencontainers.image.source="https://github.com/ravirdoracle/terraflowstudio"

EXPOSE 5000

# Run with Gunicorn in production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "60", "app:app"]
