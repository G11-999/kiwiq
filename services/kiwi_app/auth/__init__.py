# Expose key components for easier access
from kiwi_app.auth import models
# from . import schemas
# from . import services
# from . import dependencies
from kiwi_app.auth import routers
# from . import constants

# Expose the main router instance
router = routers.router
# models.Permission.model_rebuild()
# models.Role.model_rebuild()
# models.UserOrganizationRole.model_rebuild()
# models.Organization.model_rebuild()
# models.User.model_rebuild()
# models.RefreshToken.model_rebuild()

# # Expose the service instance
# auth_service = services.auth_service

# Optionally expose specific dependencies or models if frequently needed elsewhere
# from .dependencies import get_current_active_user
# from .models import User, Organization

