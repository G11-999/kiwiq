#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Function to check if a command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# NOTE: this may have unintended side effects of overwriting docker compose ENV overwrites!
# # Source the .env file
# if [ -f /app/.env ]; then
#   source /app/.env
# fi

# --- Configuration ---
# Read PostgreSQL connection details from environment variables
# Provide defaults for local development if needed, but fail if essential ones are missing
: "${POSTGRES_USER:?Error: POSTGRES_USER environment variable is not set.}"
: "${POSTGRES_PASSWORD:?Error: POSTGRES_PASSWORD environment variable is not set.}"
: "${POSTGRES_HOST:?Error: POSTGRES_HOST environment variable is not set.}"
: "${POSTGRES_PORT:?Error: POSTGRES_PORT environment variable is not set.}"
: "${POSTGRES_DATABASES:?Error: POSTGRES_DATABASES environment variable is not set (comma-separated).}"

# Export PGPASSWORD so psql doesn't prompt for password
export PGPASSWORD="${POSTGRES_PASSWORD}"

# --- Check Dependencies ---
if ! command_exists psql; then
  echo "Error: psql command not found. Please install PostgreSQL client tools."
  exit 1
fi

if ! command_exists python; then
  echo "Error: python command not found. Please ensure Python is installed and in PATH."
  exit 1
fi

if ! command_exists alembic; then
  echo "Warning: alembic command not found. Skipping migrations. Ensure it's installed if needed."
  # Depending on requirements, you might want to exit 1 here instead
fi

# --- Database Creation ---
echo "Checking and creating PostgreSQL databases..."

# Use a temporary default database (like 'postgres') to connect for checking/creating others
DB_CHECK_CONN_OPTS="-U ${POSTGRES_USER} -h ${POSTGRES_HOST} -p ${POSTGRES_PORT} -d postgres -tAc"

# Split the comma-separated list of databases
IFS=',' read -ra DB_NAMES <<< "$POSTGRES_DATABASES"

for db_name in "${DB_NAMES[@]}"; do
  # Trim whitespace
  db_name=$(echo "$db_name" | xargs)
  if [[ -z "$db_name" ]]; then
    continue # Skip empty names
  fi

  echo "Checking database: $db_name"
  # Check if the database exists
  # The query returns '1' if the database exists, empty otherwise.
  # Redirect stderr to /dev/null to suppress "database doesn't exist" errors if connecting to 'postgres' initially fails (e.g., first run)
  db_exists=$(psql $DB_CHECK_CONN_OPTS "SELECT 1 FROM pg_database WHERE datname='$db_name'" 2>/dev/null || echo "")

  if [[ "$db_exists" == "1" ]]; then
    echo "Database '$db_name' already exists."
  else
    echo "Database '$db_name' does not exist. Creating..."
    # Create the database. Use double quotes for the SQL command.
    # Connect to the default 'postgres' database to run the CREATE DATABASE command.
    psql $DB_CHECK_CONN_OPTS "CREATE DATABASE "$db_name";"
    echo "Database '$db_name' created."
  fi
done

echo "Database checks complete."

# --- Run Initial Setup Scripts ---
# Assumes the current working directory is the project root
# and the Python environment has necessary dependencies installed.
# These scripts should ideally read database connection info from environment variables
# (e.g., DATABASE_URL or individual POSTGRES_* variables).

echo "Running initial DB setup script..."
python services/kiwi_app/scripts/db_setup.py
echo "DB setup script finished."

echo "Running LangGraph Postgres setup script..."
python services/kiwi_app/scripts/langgraph_postgres_setup.py
echo "LangGraph Postgres setup script finished."

# --- Run Alembic Migrations ---
if command_exists alembic; then
  echo "Running Alembic migrations..."
  # Alembic typically reads database connection URL from alembic.ini or environment variable (DATABASE_URL)
  alembic -c /app/libs/src/db/alembic.ini upgrade head
  echo "Alembic migrations complete."
else
    echo "Skipping Alembic migrations (command not found)."
fi


# --- Set execution permissions ---
# This line is commented out as it should be run once manually after creating the file,
# not every time the script itself runs.
# chmod +x setup.sh

echo "Setup script completed successfully."

# Unset PGPASSWORD for security
unset PGPASSWORD

# Execute the command passed as arguments (e.g., the CMD from Dockerfile)
# NOTE this runs the CMD for eg: CMD ["poetry", "run", "uvicorn", "services.kiwi_app.main:app", "--host", "0.0.0.0", "--port", ${APP_PORT}]
echo "Executing command: $@"
exec "$@"

# Exit 0 should not be reached if exec is successful
exit 0 
