import logging
import os
from typing import Generator, List, Type

from sqlmodel import Session, SQLModel, delete

# --- Project Imports ---
# Adjust these import paths based on your actual project structure.
# Assuming 'kiwi_app' is a top-level package accessible in your PYTHONPATH.

# Import all relevant authentication models
from kiwi_app.auth.models import (
    RefreshToken,
    RolePermission,
    UserOrganizationRole,
    Permission,
    Role,
    Organization,
    User,
)
from kiwi_app.workflow_app.models import (
    NodeTemplate,
    SchemaTemplate,
    PromptTemplate,
    Workflow,
    WorkflowRun,
    UserNotification,
    HITLJob,
)
# Import the function to get a database session
# This is a placeholder; replace with your project's actual session provider.
# Common patterns include a context manager or a dependency injection function.
from libs.src.db.session import get_db_as_manager # <<< ADJUST THIS IMPORT >>>

# --- Logging Configuration ---
# Basic logging setup to provide feedback during script execution.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- Model Deletion Order ---
# Define the order in which tables should be cleared.
# This is CRUCIAL to respect foreign key constraints.
# Start with tables that have foreign keys pointing to other tables,
# or link tables, and end with the tables they point to.
#
# Order rationale:
# 1. RefreshToken: FK to User.
# 2. RolePermission: Link table, FKs to Role and Permission.
# 3. UserOrganizationRole: Link table, FKs to User, Organization, Role.
# 4. Permission: Referenced by RolePermission.
# 5. Role: Referenced by RolePermission, UserOrganizationRole.
# 6. Organization: Referenced by UserOrganizationRole.
# 7. User: Referenced by RefreshToken, UserOrganizationRole.
#
# If you add new models with relationships, carefully update this list.
MODELS_TO_DELETE: List[Type[SQLModel]] = [
    # NOTE: should be deleted in order to not trigger DB constraints on foreign keys!
    # Workflow Models
    HITLJob,
    UserNotification,
    WorkflowRun,
    Workflow,
    PromptTemplate,
    SchemaTemplate,
    NodeTemplate,
    
    # Auth Models
    RefreshToken,
    RolePermission,
    UserOrganizationRole,
    Permission, # Must be deleted after RolePermission
    Role,       # Must be deleted after RolePermission and UserOrganizationRole
    Organization, # Must be deleted after UserOrganizationRole
    User,       # Must be deleted after RefreshToken and UserOrganizationRole
]

# --- Safety Mechanism ---
# Require a specific environment variable to be set to 'true' to run the script.
# This acts as a safeguard against accidental execution, particularly in
# sensitive environments like staging or production.
CONFIRMATION_ENV_VAR = "CONFIRM_AUTH_DB_RESET"
EXPECTED_CONFIRMATION_VALUE = "true"

def reset_auth_tables(session: Session) -> None:
    """
    Deletes all records from the specified authentication-related database tables.

    Iterates through the `MODELS_TO_DELETE` list in the defined order and executes
    a DELETE statement without a WHERE clause for each corresponding table.
    This effectively truncates the tables while respecting foreign key constraints.

    Args:
        session: The database session object (SQLModel Session) used to execute
                 the delete statements.

    Raises:
        Exception: Propagates any exceptions raised by the database driver
                   or SQLAlchemy/SQLModel during the deletion process. Ensures
                   transaction rollback on failure.

    Important:
        - The order in `MODELS_TO_DELETE` is critical.
        - This function performs irreversible data deletion.
        - Ensure the session management handles transactions appropriately
          (commit on success, rollback on failure).
    """
    logger.info(f"Starting deletion of {len(MODELS_TO_DELETE)} auth-related tables...")
    # Using a single transaction for all deletions.
    # If any delete fails, the entire operation is rolled back.
    # import ipdb; ipdb.set_trace()
    try:
        for model in MODELS_TO_DELETE:
            # Get the actual table name for logging purposes
            # SQLModel models have a __tablename__ attribute.
            table_name = getattr(model, '__tablename__', model.__name__)
            logger.info(f"Executing DELETE statement for table: {table_name}...")

            # Create a delete statement for the current model
            # delete(model) creates a statement like DELETE FROM <tablename>;
            statement = delete(model)
            # session.query(model).delete(synchronize_session='fetch')


            # Execute the statement
            results = session.exec(statement)

            # Log the number of deleted rows for confirmation
            logger.info(f"Deleted {results.rowcount} records from {table_name}.")

        # If all deletes were successful, commit the transaction
        session.commit()
        logger.info("Successfully committed deletion transaction.")

    except Exception as e:
        # If any error occurs during the process, rollback the transaction
        logger.error(f"An error occurred during table deletion: {e}")
        logger.error("Rolling back transaction...")
        session.rollback()
        logger.error("Transaction rolled back.")
        # Re-raise the exception so the caller knows the operation failed
        raise
    finally:
        # Although commit/rollback should close the transaction state,
        # it's good practice ensure cleanup if session handling requires it.
        # The session closing is typically handled by the context manager (`main` func).
        pass

def main() -> None:
    """
    Main execution function for the authentication database reset script.

    Performs the following steps:
    1. Checks if the confirmation environment variable is set correctly. Exits if not.
    2. Acquires a database session using the project's session provider.
    3. Calls the `reset_auth_tables` function to perform the deletions.
    4. Handles session cleanup and logs success or failure messages.
    """
    logger.info("Auth DB Reset Script - Initializing...")
    logger.warning("!!! WARNING: This script will delete ALL data from auth tables !!!")

    # --- Safety Check ---
    confirmation = os.getenv(CONFIRMATION_ENV_VAR)
    if confirmation is None:
        logger.error(f"FATAL: Environment variable '{CONFIRMATION_ENV_VAR}' is not set.")
        logger.error("Aborting script to prevent accidental data loss.")
        logger.error(f"To run this script, set the variable: export {CONFIRMATION_ENV_VAR}={EXPECTED_CONFIRMATION_VALUE}")
        return # Exit the function early
    elif confirmation.lower() != EXPECTED_CONFIRMATION_VALUE:
        logger.error(f"FATAL: Environment variable '{CONFIRMATION_ENV_VAR}' is set to '{confirmation}', not '{EXPECTED_CONFIRMATION_VALUE}'.")
        logger.error("Aborting script.")
        return # Exit the function early

    logger.info(f"Confirmation '{CONFIRMATION_ENV_VAR}={EXPECTED_CONFIRMATION_VALUE}' received.")
    logger.info("Proceeding with database reset...")

    

    try:
        # Perform the actual deletion
        # --- Database Operation ---
        with get_db_as_manager() as session:
            reset_auth_tables(session)
        logger.info("Auth DB Reset Script Completed Successfully.")

    except Exception as e:
        # Error messages are logged within reset_auth_tables,
        # but log a final failure message here.
        logger.error(f"Auth DB Reset Script Failed. Error: {e}", exc_info=e)

    finally:
        # --- Session Cleanup ---
        logger.info("Auth DB Reset Script Finished.")


# --- Script Entry Point ---
if __name__ == "__main__":
    # Execute the main function when the script is run directly
    main()
