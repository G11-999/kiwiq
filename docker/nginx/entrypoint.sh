#!/bin/bash
# Exit immediately if a command exits with a non-zero status.
set -e

# --- Environment Variable Checks ---
# Ensure required environment variables are set. Fail script if not.
: "${YOUR_DOMAIN:?Error: YOUR_DOMAIN environment variable is not set.}"
: "${APP_HOST:?Error: APP_HOST environment variable is not set.}"
: "${APP_PORT:?Error: APP_PORT environment variable is not set.}"
: "${CERTBOT_EMAIL:?Error: CERTBOT_EMAIL environment variable is not set.}"

# --- Nginx Configuration Substitution ---
# Use `envsubst` to replace placeholder variables in the template file
# with actual environment variable values. The output is written to the
# final Nginx configuration file used by the running Nginx process.
# Specify only the variables that should be substituted.

echo "Substituting environment variables in Nginx config template..."
envsubst '${YOUR_DOMAIN} ${APP_HOST} ${APP_PORT}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf

echo "Nginx configuration generated:"
cat /etc/nginx/conf.d/default.conf # Output the generated config for verification/debugging

# --- Start Cron Service ---
# The cron daemon is responsible for running the scheduled Certbot renewal job.
echo "Starting Cron daemon..."
cron -f &
# Note: Running cron in the foreground (`-f`) within a background task (`&`) is a common pattern in containers.
# Alternatively, start it directly if it's the only long-running process besides Nginx.

# --- Certbot Certificate Management ---
# Define the path to the certificate file to check for existence.
CERT_PATH="/etc/letsencrypt/live/${YOUR_DOMAIN}/fullchain.pem"

# Check if the certificate file already exists.
if [ ! -f "${CERT_PATH}" ]; then
  echo "Certificate not found for ${YOUR_DOMAIN} at ${CERT_PATH}. Attempting to obtain..."

  # --- Obtain Initial Certificate ---
  # Use Certbot with the --nginx plugin to obtain a certificate.
  # The --nginx plugin automatically modifies the Nginx configuration
  # to handle the ACME challenge and then reverts the changes.
  # This usually requires Nginx to be stopped or port 80 to be temporarily free.

  # Stop Nginx to ensure port 80 is available for Certbot's challenge validation.
  # The `|| true` prevents the script from exiting if Nginx wasn't running.
  echo "Stopping Nginx temporarily to obtain certificate..."
  nginx -s stop || true

  echo "Running Certbot..."
  certbot certonly --nginx \
    -d "${YOUR_DOMAIN}" \
    --email "${CERTBOT_EMAIL}" \
    --agree-tos \
    --non-interactive \ # Run without user prompts
    --keep-until-expiring \ # Keep certificates until they are near expiry
    --rsa-key-size 4096 \ # Use a strong RSA key size
    --verbose # Provide more detailed output for debugging

  # Check the exit status of Certbot.
  if [ $? -ne 0 ]; then
    echo "Certbot failed to obtain certificate. Check Nginx configuration, DNS records, and Certbot logs (/var/log/letsencrypt)."
    # Optionally, dump logs here
    echo "--- Last 50 lines of Certbot log ---"
    tail -n 50 /var/log/letsencrypt/letsencrypt.log || echo "Could not tail Certbot log file."
    echo "------------------------------------"
    exit 1 # Exit the script if Certbot failed
  fi

  echo "Certificate obtained successfully."
  # Nginx will be started by the main CMD passed to this entrypoint script (see below).

else
  echo "Certificate found for ${YOUR_DOMAIN} at ${CERT_PATH}. Skipping initial issuance."
fi

# --- Start Nginx ---
# The final step is to execute the command passed to this entrypoint script.
# In the Dockerfile, this is typically `nginx -g 'daemon off;'`,
# which starts Nginx in the foreground, keeping the container running.
echo "Executing command: $@"
exec "$@"

# The `exec` command replaces the current shell process with the specified command.
# Control does not return here unless the command fails to execute. 