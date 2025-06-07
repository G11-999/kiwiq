from fastapi import HTTPException, status

# --- Authentication / Security Exceptions ---

class CredentialsException(HTTPException):
    """Custom exception for invalid authentication credentials."""
    def __init__(self, detail: str = "Could not validate credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"}, # Important for OAuth2
        )

class InactiveUserException(HTTPException):
    """Custom exception for users who are marked as inactive."""
    def __init__(self, detail: str = "Inactive user"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

class UserNotVerifiedException(HTTPException):
    """Custom exception for users whose email is not verified."""
    def __init__(self, detail: str = "User email not verified"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

class InvalidTokenException(HTTPException):
    """Custom exception for invalid verification or reset tokens."""
    def __init__(self, detail: str = "Invalid or expired token"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

# --- User / Resource Exceptions ---

class UserNotFoundException(HTTPException):
    """Custom exception when a user is not found in the database."""
    def __init__(self, detail: str = "User not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class OrganizationSeatLimitExceededException(HTTPException):
    """Custom exception when a user tries to add a user to an organization that has reached the seat limit."""
    def __init__(self, detail: str = "Organization seat limit exceeded"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

class EmailAlreadyExistsException(HTTPException):
    """Custom exception for attempting to register with an existing email."""
    def __init__(self, detail: str = "Email already registered"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

class OrganizationNotFoundException(HTTPException):
    """Custom exception when an organization is not found."""
    def __init__(self, detail: str = "Organization not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class RoleNotFoundException(HTTPException):
    """Custom exception when a role is not found."""
    def __init__(self, detail: str = "Role not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class PermissionDeniedException(HTTPException):
    """Custom exception for insufficient permissions."""
    def __init__(self, detail: str = "Permission denied"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

# You can add more specific exceptions as needed 