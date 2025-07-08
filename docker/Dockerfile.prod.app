# Use Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies (including curl for installing Poetry, build tools, and postgres client dev libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    build-essential \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry (using the official installer)
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    mv $HOME/.local/bin/poetry /usr/local/bin/poetry

# Copy only the files necessary for dependency installation
COPY pyproject.toml poetry.lock* ./
# Copy the local 'libs' path dependency so poetry can find it
COPY libs ./libs

# 2) Bump pip timeout & retries
ENV PIP_DEFAULT_TIMEOUT=120
RUN pip install --upgrade pip \
 && pip config --global set global.timeout 120 \
 && pip config --global set global.retries 5

# Install dependencies with Poetry (no virtualenv since we're in a container)
RUN poetry config virtualenvs.create false && poetry install --without dev --no-interaction --no-ansi

# Copy the rest of the application code
COPY . .
# Set execution permissions for the setup script
RUN chmod +x /app/docker/setup.sh
# Copy prod env
# NOTE: to use same cmd in local and remote, just copy local prod .env to remote machine!
# COPY .env.prod /app/.env

# Set PYTHONPATH so that both the project root and services folder are in the path
ENV PYTHONPATH=/app:/app/services

# Define the application port as an environment variable
ENV APP_PORT=8000

# Expose the application port
EXPOSE ${APP_PORT}

# Set the working directory in the container
WORKDIR /app

ENTRYPOINT ["/app/docker/setup.sh"]

# Default command: run the application
# For production, you might run: poetry run python app.py
# For testing, override the command with: PYTHONPATH=$(pwd):$(pwd)/services poetry run pytest
# Virtual env not needed as poetry is installed without virtual env
# Use the actual port number directly in CMD to avoid substitution issues with ENTRYPOINT/exec
# Add --reload flag and --reload-dir for development live reloading
# , "--workers", "4"
CMD ["uvicorn", "services.kiwi_app.main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "8000"]
# PYTHONPATH=$(pwd):$(pwd)/services  poetry run uvicorn services.kiwi_app.main:app --host 0.0.0.0 --port 8000
