"""
# poetry run python -m kiwi_client.auth_client

Provides an authenticated HTTP client for interacting with the API.
Handles login, token storage, and setting necessary headers.
"""
import httpx
import logging
from typing import Optional, Dict, Any, Union
import uuid

# Import configuration details
from kiwi_client.test_config import (
    API_BASE_URL,
    TEST_USER_EMAIL,
    TEST_USER_PASSWORD,
    TEST_ORG_ID,
    BASE_HEADERS,
    LOGIN_URL,
    REFRESH_URL,
    USERS_ME_URL,
    CLIENT_LOG_LEVEL,
    ADMIN_REGISTER_URL,
    ORGANIZATIONS_URL,
    ORG_DETAIL_URL
)
from kiwi_client.schemas.auth_schemas import (
    UserAdminCreate,
    OrganizationUpdate
)

# Setup logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)


class AuthenticationError(Exception):
    """Custom exception for authentication failures."""
    pass


class AuthenticatedClient:
    """
    Manages an authenticated httpx session for API testing.

    Handles login, stores access token, manages refresh token cookies,
    and provides an authenticated httpx.AsyncClient instance.
    """
    def __init__(
        self,
        base_url: str = API_BASE_URL,
        email: str = TEST_USER_EMAIL,
        password: str = TEST_USER_PASSWORD,
        active_org_id: str = str(TEST_ORG_ID)
    ) -> None:
        """
        Initializes the AuthenticatedClient.

        Args:
            base_url: The base URL of the API.
            email: The email for the test user.
            password: The password for the test user.
            active_org_id: The organization ID to use for the X-Active-Org header.
        """
        self._base_url = base_url
        self._email = email
        self._password = password
        self._active_org_id = active_org_id
        self._access_token: Optional[str] = None
        # Use httpx.AsyncClient with cookie handling enabled
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=self._base_url,
            headers=BASE_HEADERS.copy(), # Start with base headers
            timeout=30.0 # Set a reasonable timeout
        )
        self._is_authenticated: bool = False
        logger.info("AuthenticatedClient initialized.")

    @property
    def client(self) -> httpx.AsyncClient:
        """
        Returns the authenticated httpx.AsyncClient instance.
        Ensures the client is authenticated before returning.
        """
        if not self._is_authenticated:
            raise AuthenticationError("Client is not authenticated. Call login() first.")
        return self._client

    @property
    def active_org_id(self) -> str:
        """Returns the active organization ID being used."""
        return self._active_org_id

    async def _update_auth_header(self) -> None:
        """Updates the Authorization header in the client."""
        if self._access_token:
            self._client.headers["Authorization"] = f"Bearer {self._access_token}"
            logger.debug("Authorization header updated.")
        else:
            # Should not happen if login was successful, but handle defensively
            if "Authorization" in self._client.headers:
                del self._client.headers["Authorization"]
            logger.warning("Attempted to update auth header with no access token.")

    async def _update_org_header(self) -> None:
        """Updates the X-Active-Org header in the client."""
        self._client.headers["X-Active-Org"] = self._active_org_id
        logger.debug(f"X-Active-Org header set to: {self._active_org_id}")

    async def login(self) -> None:
        """
        Logs in the user using the provided credentials and stores the access token
        and refresh token cookie.
        """
        logger.info(f"Attempting login for user: {self._email}...")
        try:
            # Use form data for login as required by OAuth2PasswordRequestForm
            login_data = {"username": self._email, "password": self._password}
            response = await self._client.post(
                LOGIN_URL, # Use absolute URL from config
                data=login_data,
                # Override content type for form data
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            # Check response status before trying to parse JSON
            response.raise_for_status() # Raises HTTPStatusError for 4xx/5xx

            token_data = response.json()
            self._access_token = token_data.get("access_token")

            if not self._access_token:
                logger.error("Login response did not contain an access token.")
                raise AuthenticationError("Login failed: No access token received.")

            # Update headers
            await self._update_auth_header()
            await self._update_org_header() # Set org header after successful login

            self._is_authenticated = True
            logger.info(f"Login successful for user: {self._email}. Access token stored. Refresh cookie set by server.")

        except httpx.RequestError as e:
            logger.error(f"Login request failed: {e}", exc_info=True)
            raise AuthenticationError(f"Login failed: Network error connecting to {e.request.url!r}.")
        except httpx.HTTPStatusError as e:
            logger.error(f"Login failed with status {e.response.status_code}: {e.response.text}")
            self._is_authenticated = False
            detail = "Unknown authentication error."
            try:
                # Try to get more specific error detail from response
                error_details = e.response.json()
                detail = error_details.get("detail", detail)
            except Exception:
                pass # Ignore if response is not JSON or parsing fails
            raise AuthenticationError(f"Login failed: {detail} (Status: {e.response.status_code})")
        except Exception as e:
            logger.exception("An unexpected error occurred during login.")
            self._is_authenticated = False
            raise AuthenticationError(f"Login failed due to an unexpected error: {e}")

    async def refresh_token(self) -> bool:
        """
        Attempts to refresh the access token using the refresh token cookie.
        Updates the stored access token and client headers on success.

        Returns:
            True if refresh was successful, False otherwise.
        """
        logger.info("Attempting to refresh access token...")
        if not self._client.cookies.get("refresh_token"):
             logger.warning("No refresh token cookie found. Cannot refresh.")
             return False
        try:
            # The refresh endpoint expects no body, it uses the cookie
            response = await self._client.post(REFRESH_URL) # Use absolute URL
            response.raise_for_status()

            token_data = response.json()
            new_access_token = token_data.get("access_token")

            if not new_access_token:
                logger.error("Token refresh response did not contain a new access token.")
                return False

            self._access_token = new_access_token
            await self._update_auth_header() # Update header with new token
            logger.info("Access token refreshed successfully.")
            return True

        except httpx.HTTPStatusError as e:
            logger.error(f"Token refresh failed with status {e.response.status_code}: {e.response.text}")
            # If refresh fails (e.g., 401), mark as unauthenticated
            self._is_authenticated = False
            self._access_token = None
            if "Authorization" in self._client.headers:
                del self._client.headers["Authorization"]
            return False
        except httpx.RequestError as e:
            logger.error(f"Token refresh request failed: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.exception("An unexpected error occurred during token refresh.")
            return False

    async def admin_register_user(
        self,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        is_verified: bool = True,
        is_superuser: bool = False
    ) -> Dict[str, Any]:
        """
        Register a new user with admin privileges.
        
        This method allows superusers to create new users with specified
        verification status and superuser privileges. The caller must
        be authenticated as a superuser to use this endpoint.
        
        Args:
            email: Email address for the new user
            password: Password for the new user
            full_name: Optional full name for the user
            is_verified: Whether the user's email should be considered verified
            is_superuser: Whether the user should have superuser privileges
            
        Returns:
            Dict[str, Any]: The newly created user data
            
        Raises:
            httpx.HTTPStatusError: If the request fails due to a 4xx/5xx status code
            AuthenticationError: If the client is not authenticated
        """
        if not self._is_authenticated:
            raise AuthenticationError("Client is not authenticated. Call login() first.")
        
        logger.info(f"Registering new user as admin: {email} (verified={is_verified}, superuser={is_superuser})")
        
        # Create user data using the UserAdminCreate schema
        user_data = UserAdminCreate(
            email=email,
            password=password,
            full_name=full_name,
            is_verified=is_verified,
            is_superuser=is_superuser
        ).model_dump()
        
        try:
            response = await self._client.post(
                ADMIN_REGISTER_URL,
                json=user_data
            )
            response.raise_for_status()
            
            user_result = response.json()
            logger.info(f"Successfully registered user {email} with admin privileges")
            return user_result
            
        except httpx.HTTPStatusError as e:
            error_detail = "Unknown error"
            try:
                error_detail = e.response.json().get("detail", error_detail)
            except Exception:
                pass
            
            logger.error(f"Failed to register user {email} as admin: {error_detail} (Status: {e.response.status_code})")
            raise
            
        except Exception as e:
            logger.exception(f"Unexpected error registering user {email} as admin")
            raise

    async def update_organization(
        self,
        org_id: Union[str, uuid.UUID],
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update an organization's details.
        
        This method allows updating the name and/or description of an organization.
        The authenticated user must have the 'org:update' permission within the
        organization to perform this operation.
        
        Args:
            org_id: UUID of the organization to update
            name: New name for the organization (optional)
            description: New description for the organization (optional)
            
        Returns:
            Dict[str, Any]: The updated organization data
            
        Raises:
            httpx.HTTPStatusError: If the request fails due to a 4xx/5xx status code
            AuthenticationError: If the client is not authenticated
            ValueError: If neither name nor description is provided
        """
        if not self._is_authenticated:
            raise AuthenticationError("Client is not authenticated. Call login() first.")
            
        if not (name or description):
            raise ValueError("At least one of name or description must be provided")
            
        # Convert org_id to string if it's a UUID
        org_id_str = str(org_id)
        
        # Create update data using the OrganizationUpdate schema
        update_data = OrganizationUpdate(
            name=name,
            description=description
        ).model_dump(exclude_none=True)  # Only include fields that were provided
        
        logger.info(f"Updating organization {org_id_str}: {update_data}")
        
        try:
            response = await self._client.patch(
                ORG_DETAIL_URL(org_id_str),
                json=update_data
            )
            response.raise_for_status()
            
            updated_org = response.json()
            logger.info(f"Successfully updated organization {org_id_str}")
            return updated_org
            
        except httpx.HTTPStatusError as e:
            error_detail = "Unknown error"
            try:
                error_detail = e.response.json().get("detail", error_detail)
            except Exception:
                pass
            
            logger.error(f"Failed to update organization {org_id_str}: {error_detail} (Status: {e.response.status_code})")
            raise
            
        except Exception as e:
            logger.exception(f"Unexpected error updating organization {org_id_str}")
            raise

    async def close(self) -> None:
        """Closes the underlying httpx client."""
        await self._client.aclose()
        logger.info("AuthenticatedClient closed.")

    async def __aenter__(self) -> "AuthenticatedClient":
        """Enables use as an async context manager, performing login."""
        await self.login()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Closes the client when exiting the context."""
        await self.close()


# Example Usage (for testing this module directly)
async def main():
    """Example of using the AuthenticatedClient."""
    print("Testing AuthenticatedClient...")
    auth_client = AuthenticatedClient()
    try:
        # Using context manager automatically handles login and close
        async with auth_client:
            print(f"Login successful. Using Org ID: {auth_client.active_org_id}")
            client = auth_client.client # Get the authenticated client
            print("Headers:", client.headers)

            # Example: Make an authenticated request (replace with a valid endpoint)
            try:
                # me_url = "/auth/users/me" # Relative path is okay here
                response = await client.get(USERS_ME_URL)
                response.raise_for_status()
                user_data = response.json()
                print(f"Successfully fetched /users/me: {user_data.get('email')}")
            except httpx.HTTPStatusError as e:
                print(f"Error fetching /users/me: {e.response.status_code} - {e.response.text}")
            except Exception as e:
                print(f"An error occurred: {e}")

            # Example: Test token refresh (optional, uncomment to test)
            print("Testing token refresh...")
            refreshed = await auth_client.refresh_token()
            if refreshed:
                print("Token refreshed successfully.")
                print("New Headers:", client.headers)
            else:
                print("Token refresh failed.")
                
            # Example: Test admin user registration (Requires superuser permissions)
            # Uncomment to test (makes actual API changes!)
            
            # try:
            #     print("Testing admin user registration...")
            #     new_user = await auth_client.admin_register_user(
            #         email="newadmin@example.com",
            #         password="SecurePassword123!",
            #         full_name="New Admin User",
            #         is_verified=True,
            #         is_superuser=False  # Regular admin, not superuser
            #     )
            #     print(f"Successfully registered new admin user: {new_user.get('email')}")
            # except httpx.HTTPStatusError as e:
            #     print(f"Error registering admin user: {e.response.status_code} - {e.response.text}")
            # except Exception as e:
            #     print(f"An error occurred during admin registration: {e}")
            
            
            # Example: Test organization update (Requires org:update permission)
            # Uncomment to test (makes actual API changes!)
            
            # try:
            #     print("Testing organization update...")
            #     org_id = auth_client.active_org_id  # Use the current active org
            #     updated_org = await auth_client.update_organization(
            #         org_id=org_id,
            #         name="Updated Organization Name",
            #         description="This organization was updated via the API client."
            #     )
            #     print(f"Successfully updated organization: {updated_org.get('name')}")
            # except httpx.HTTPStatusError as e:
            #     print(f"Error updating organization: {e.response.status_code} - {e.response.text}")
            # except Exception as e:
            #     print(f"An error occurred during organization update: {e}")
            

    except AuthenticationError as e:
        print(f"Authentication Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        # Ensure closure if not using context manager or if login failed before entering
        if not auth_client._client.is_closed:
            await auth_client.close()

if __name__ == "__main__":
    import asyncio
    # Before running, ensure your API server is running and the credentials/org ID
    # in test_config.py are correct.
    # You might need to register the user first if they don't exist.
    asyncio.run(main())
    print("Run this script with `PYTHONPATH=. python services/kiwi_app/workflow_app/test_clients/auth_client.py`")
    print("Note: Example usage is commented out by default.") 
