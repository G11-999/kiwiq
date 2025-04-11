
**How to Use:**

1.  Launch your Amazon Linux 2023 EC2 instance, configure Security Groups, assign an Elastic IP, and get your SSH key.
2.  SSH into the instance: `ssh -i key.pem ec2-user@YOUR_IP`.
3.  Copy the content of the first script (`setup_ec2.sh`) into a file on the EC2 instance.
4.  Make it executable: `chmod +x setup_ec2.sh`.
5.  Run it: `./setup_ec2.sh`.
6.  **Log out (`exit`) and log back in via SSH.**
7.  Copy the content of the second block (Step 2: Application Deployment & Systemd Setup) into a second script file (e.g., `deploy_app.sh`) *or* run the commands one by one manually. If using a script, make it executable (`chmod +x deploy_app.sh`) and run it (`./deploy_app.sh`). Pay close attention during the `nano .env.prod` step to add your secrets.
8.  Monitor the output, especially the container status and logs, and the final systemd status check.
9.  Configure your DNS A record to point your domain/subdomain to the EC2 instance's Elastic IP.
10. Wait for DNS propagation, then verify HTTPS access. The Certbot process within the Nginx container should handle certificate acquisition automatically.


---

**Step 2: Application Deployment & Systemd Setup**

These commands should be run manually *after* running `setup_ec2.sh` and logging back in.

```bash
# --- 1. Clone Your Repository ---
# Replace <repo-url> and choose a deployment path
REPO_URL="https://github.com/your-username/your-repo.git"
DEPLOY_PATH="/home/ec2-user/my-app" # Example path

echo "Cloning repository from ${REPO_URL} to ${DEPLOY_PATH}..."
git clone "${REPO_URL}" "${DEPLOY_PATH}"

# --- 2. Navigate to Project Directory ---
cd "${DEPLOY_PATH}"
echo "Changed directory to $(pwd)"

# --- 3. Create Production Environment File ---
echo "Creating .env.prod file. Please paste your production secrets now."
echo "Save and exit the editor when done (Ctrl+X, then Y, then Enter in nano)."
# IMPORTANT: Add your actual production secrets here!
# Example content (REPLACE WITH YOUR VALUES):
# YOUR_DOMAIN=myapp.example.com
# CERTBOT_EMAIL=you@example.com
# APP_HOST=app
# APP_PORT=8000
# REDIS_HOST=redis
# MONGO_URI=mongodb://mongo:27017/
# RABBITMQ_URI=amqp://your_secure_user:your_very_secure_password@rabbitmq:5672/%2F
# PREFECT_API_URL=http://prefect-server:4200/api
# PREFECT_SERVER_DATABASE_CONNECTION_URL=postgresql+psycopg2://user:password@your-rds-endpoint...
# DATABASE_URL=postgresql+psycopg2://user:password@your-rds-endpoint...
# SECRET_KEY=your_production_secret_key
nano .env.prod

# --- 4. Secure the Environment File ---
echo "Setting permissions for .env.prod..."
chmod 600 .env.prod

# --- 5. Build and Start Docker Compose Stack ---
# Ensure your production compose file is named correctly (e.g., docker-compose.prod.yml)
COMPOSE_FILE="docker-compose.prod.yml"

echo "Building images (if needed)..."
docker compose -f "${COMPOSE_FILE}" build

echo "Starting Docker Compose stack in detached mode..."
docker compose -f "${COMPOSE_FILE}" up -d

echo "Waiting a few seconds for services to start..."
sleep 10 # Give containers a moment to initialize

echo "--- Current Container Status ---"
docker compose -f "${COMPOSE_FILE}" ps

echo "--- Check Logs (Press Ctrl+C to stop following) ---"
docker compose -f "${COMPOSE_FILE}" logs -f nginx app # Check logs for key services

# --- 6. Setup Systemd Service (for Reliability) ---
# This section creates and enables the systemd service to manage your stack.
# Run this AFTER confirming the stack starts correctly with the 'up -d' command above.

SERVICE_NAME="myapp-compose" # Choose a name for your service
USER="ec2-user" # User running the service
GROUP="docker" # Group for docker permissions
WORKING_DIRECTORY="${DEPLOY_PATH}" # Project directory path defined above
COMPOSE_FILE_PATH="${WORKING_DIRECTORY}/${COMPOSE_FILE}" # Full path to compose file

echo "Creating systemd service file at /etc/systemd/system/${SERVICE_NAME}.service..."

# Create the service file content using a heredoc
sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" > /dev/null <<EOF
[Unit]
Description=My App Docker Compose Stack (${SERVICE_NAME})
Requires=docker.service
After=docker.service

[Service]
User=${USER}
Group=${GROUP}
WorkingDirectory=${WORKING_DIRECTORY}

# Stop attempts after 5 minutes
TimeoutStartSec=300

# Compose commands (use full path to docker if needed, e.g., /usr/bin/docker)
ExecStart=$(which docker) compose -f "${COMPOSE_FILE_PATH}" up
ExecStop=$(which docker) compose -f "${COMPOSE_FILE_PATH}" down

# Restart policy
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "Enabling and starting ${SERVICE_NAME} service..."
# Enable means start on boot, --now starts it immediately
sudo systemctl enable --now "${SERVICE_NAME}.service"

echo "--- Checking status of ${SERVICE_NAME} service ---"
sudo systemctl status "${SERVICE_NAME}.service"

echo "--- Systemd setup complete. Your application should now be managed by systemd. ---"
echo "Use 'sudo systemctl stop/start/restart/status ${SERVICE_NAME}.service' to manage it."
```

