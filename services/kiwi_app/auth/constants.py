"""
Constants for the authentication and authorization module.
"""
from enum import Enum
from kiwi_app.workflow_app.constants import WorkflowPermissions
from kiwi_app.billing.constants import BillingPermissions

# --- Default Role Names ---
class DefaultRoles(str, Enum):
    ADMIN = "admin"
    TEAM_MEMBER = "team_member"
    BILLING = "billing"
    LINKEDIN_OAUTH_USER = "client"

# --- Permission Names (Org-Level Only) ---
# Define permissions granularly - all permissions operate within an organization context.
class Permissions(str, Enum):
    # Organization Management
    ORG_READ = "org:read"
    ORG_UPDATE = "org:update"
    ORG_DELETE = "org:delete" # Can delete the specific organization
    ORG_MANAGE_MEMBERS = "org:manage_members" # Add/remove/change roles within the org
    ORG_VIEW_MEMBERS = "org:view_members" # View members within the org
    ORG_MANAGE_ROLES = "org:manage_roles" # Create/update/delete custom roles within the org
    ORG_ADD_LINKEDIN_INTEGRATIONS = "org:add_linkedin_integrations" # Add LinkedIn integrations to the org
    ORG_DELETE_LINKEDIN_INTEGRATIONS = "org:delete_linkedin_integrations" # Delete LinkedIn integrations from the org
    # ORG_MANAGE_BILLING = "org:manage_billing"

    # # Workflow Management (within the org)
    # WORKFLOW_CREATE = "workflow:create"
    # WORKFLOW_READ = "workflow:read"
    # WORKFLOW_EXECUTE = "workflow:execute"
    # WORKFLOW_UPDATE = "workflow:update"
    # WORKFLOW_DELETE = "workflow:delete"

    # Add other org-specific permissions as needed...

ALL_PERMISSIONS = list(Permissions) + list(WorkflowPermissions) + list(BillingPermissions)

# --- Helper Function for Enum Description --- #
def get_permission_description(permission: Permissions) -> str:
    """Generates a human-readable description from a Permissions enum member."""
    return permission.name.replace("_", " ").title()

# --- Default Role to Permission Mapping ---
# This defines the initial permissions for the default roles within an organization.
DEFAULT_ROLE_PERMISSIONS = {
    DefaultRoles.ADMIN: [
        *ALL_PERMISSIONS # Grant all permissions
    ],
    DefaultRoles.LINKEDIN_OAUTH_USER: [
        Permissions.ORG_ADD_LINKEDIN_INTEGRATIONS, # Can add LinkedIn integrations to org
    ],
    DefaultRoles.TEAM_MEMBER: [
        Permissions.ORG_READ, # Can see org details
        Permissions.ORG_ADD_LINKEDIN_INTEGRATIONS, # Can add LinkedIn integrations to org
        # Permissions.ORG_VIEW_MEMBERS, # Can see org details
        WorkflowPermissions.WORKFLOW_CREATE,
        WorkflowPermissions.WORKFLOW_READ,
        WorkflowPermissions.WORKFLOW_EXECUTE,
        WorkflowPermissions.WORKFLOW_UPDATE,
        WorkflowPermissions.WORKFLOW_DELETE,

        WorkflowPermissions.RUN_READ,
        WorkflowPermissions.RUN_MANAGE,

        WorkflowPermissions.TEMPLATE_READ,
        WorkflowPermissions.TEMPLATE_CREATE,
        WorkflowPermissions.TEMPLATE_UPDATE,
        WorkflowPermissions.TEMPLATE_DELETE,

        WorkflowPermissions.ORG_DATA_READ,
        WorkflowPermissions.ORG_DATA_WRITE,

        # BillingPermissions.BILLING_READ,
        BillingPermissions.CREDIT_READ,
    ],
    DefaultRoles.BILLING: [
        Permissions.ORG_READ,
        BillingPermissions.CREDIT_READ,
        BillingPermissions.BILLING_READ,
        BillingPermissions.BILLING_MANAGE,
    ],
}

print(DEFAULT_ROLE_PERMISSIONS[DefaultRoles.ADMIN])

# --- Default Org / User Info ---
DEFAULT_ORG_NAME = "KiwiQ AI"
DEFAULT_SUPERUSER_EMAIL_ENV = "DEFAULT_SUPERUSER_EMAIL"
DEFAULT_SUPERUSER_PASSWORD_ENV = "DEFAULT_SUPERUSER_PASSWORD"
DEFAULT_FIRST_USER_ORG_SUFFIX = "'s Default Organization" 
