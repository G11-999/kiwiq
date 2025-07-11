"""
API Test client for User Application State endpoints (/app-state/).

Tests:
- Initialize User State
- List User State Documents
- List Active User State Document Names
- Get User State by docname
- Update User State
- Delete User State Document
"""
import asyncio
import httpx
import logging
import uuid
from typing import Dict, Any, Optional, List, Union

# Import authenticated client and config
from kiwi_client.auth_client import AuthenticatedClient, AuthenticationError
from kiwi_client.test_config import (
    # Assuming these will be added to test_config.py
    # If not, define them here or pass them appropriately.
    # E.g., USER_STATE_BASE_URL, USER_STATE_DETAIL_URL_FUNC, etc.
    CLIENT_LOG_LEVEL,
    USER_STATE_INITIALIZE_URL,
    USER_STATE_LIST_DOCUMENTS_URL,
    USER_STATE_ACTIVE_DOCNAMES_URL,
    USER_STATE_DETAIL_URL,
)

# Import pydantic for validation
from pydantic import ValidationError, HttpUrl

# Import schemas from the user_state app
# Attempt to import schemas, with a fallback mechanism if they're not found

from kiwi_client.schemas import app_state_schemas as us_schemas




# Setup logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)


class UserStateTestClient:
    """
    Provides methods to test the /app-state/ endpoints.
    Uses schemas from kiwi_client.schemas.user_state_api_schemas for requests and response validation.
    """
    def __init__(self, auth_client: AuthenticatedClient):
        """
        Initializes the UserStateTestClient.

        Args:
            auth_client (AuthenticatedClient): An instance of AuthenticatedClient, assumed to be logged in.
        """
        self._auth_client: AuthenticatedClient = auth_client
        self._client: httpx.AsyncClient = auth_client.client
        logger.info("UserStateTestClient initialized.")

    async def initialize_user_state(
        self,
        linkedin_profile_url: Union[str, HttpUrl],
        on_behalf_of_user_id: Optional[uuid.UUID] = None
    ) -> Optional[us_schemas.UserStateInitResponse]:
        """
        Initializes a new user application state document based on a LinkedIn profile URL.
        Corresponds to POST /app-state.

        Args:
            linkedin_profile_url (Union[str, HttpUrl]): The LinkedIn profile URL.
            on_behalf_of_user_id (Optional[uuid.UUID]): User ID to act on behalf of (superusers only).

        Returns:
            Optional[us_schemas.UserStateInitResponse]: The initialized user state and document name, or None on failure.
        """
        logger.info(f"Attempting to initialize user state with LinkedIn URL: {linkedin_profile_url}")
        
        payload_data = {
            "linkedin_profile_url": str(linkedin_profile_url)
        }
        if on_behalf_of_user_id:
            payload_data["on_behalf_of_user_id"] = str(on_behalf_of_user_id)

        try:
            # Validate payload with Pydantic model before sending if desired,
            # or let the server validate. Here, we construct dict then pass to json.
            # For strict client-side validation:
            # request_model = us_schemas.InitializeUserStateRequest(**payload_data)
            # payload = request_model.model_dump(exclude_none=True)

            response = await self._client.post(USER_STATE_INITIALIZE_URL, json=payload_data)
            response.raise_for_status()  # Check for HTTP errors (4xx, 5xx)
            response_json = response.json()

            # Validate the response against UserStateInitResponse schema
            validated_response = us_schemas.UserStateInitResponse.model_validate(response_json)
            logger.info(f"Successfully initialized user state. Docname: {validated_response.docname}")
            logger.debug(f"Initialize response validated: {validated_response.model_dump_json(indent=2)}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error initializing user state: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error initializing user state: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error initializing user state: {e}")
            # logger.debug(f"Invalid response JSON: {response_json}") # response_json might not be defined if error is before .json()
        except Exception as e:
            logger.exception("Unexpected error during user state initialization.")
        return None

    async def list_user_state_documents(
        self,
        on_behalf_of_user_id: Optional[uuid.UUID] = None
    ) -> Optional[us_schemas.ListUserStateDocumentsResponse]:
        """
        Lists all user app state document names for the current user.
        Corresponds to GET /app-state/list.

        Args:
            on_behalf_of_user_id (Optional[uuid.UUID]): User ID to act on behalf of (superusers only).

        Returns:
            Optional[us_schemas.ListUserStateDocumentsResponse]: List of document names or None on failure.
        """
        logger.info("Attempting to list user state documents.")
        params: Dict[str, Any] = {}
        if on_behalf_of_user_id:
            params["on_behalf_of_user_id"] = str(on_behalf_of_user_id)

        try:
            response = await self._client.get(USER_STATE_LIST_DOCUMENTS_URL, params=params if params else None)
            response.raise_for_status()
            response_json = response.json()

            validated_response = us_schemas.ListUserStateDocumentsResponse.model_validate(response_json)
            logger.info(f"Successfully listed {len(validated_response.docnames)} user state documents.")
            logger.debug(f"List documents response: {validated_response.model_dump_json(indent=2)}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error listing user state documents: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error listing user state documents: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error listing user state documents: {e}")
        except Exception as e:
            logger.exception("Unexpected error during user state document listing.")
        return None

    async def list_active_user_state_docnames(
        self,
        on_behalf_of_user_id: Optional[uuid.UUID] = None
    ) -> Optional[us_schemas.ActiveUserStateDocnamesResponse]:
        """
        Lists active user application state document names.
        Corresponds to GET /app-state/active-docnames.

        Args:
            on_behalf_of_user_id (Optional[uuid.UUID]): User ID to act on behalf of (superusers only).

        Returns:
            Optional[us_schemas.ActiveUserStateDocnamesResponse]: List of active docnames or None on failure.
        """
        logger.info("Attempting to list active user state document names.")
        params: Dict[str, Any] = {}
        if on_behalf_of_user_id:
            params["on_behalf_of_user_id"] = str(on_behalf_of_user_id)
        
        try:
            response = await self._client.get(USER_STATE_ACTIVE_DOCNAMES_URL, params=params if params else None)
            response.raise_for_status()
            response_json = response.json()
            
            validated_response = us_schemas.ActiveUserStateDocnamesResponse.model_validate(response_json)
            logger.info(f"Successfully listed {len(validated_response.active_docnames)} active user state documents.")
            logger.debug(f"List active docnames response: {validated_response.model_dump_json(indent=2)}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error listing active user state docnames: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error listing active user state docnames: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error listing active user state docnames: {e}")
        except Exception as e:
            logger.exception("Unexpected error listing active user state docnames.")
        return None

    async def get_user_state(
        self,
        docname: str,
        paths_to_get_str: Optional[str] = None,
        on_behalf_of_user_id: Optional[uuid.UUID] = None
    ) -> Optional[us_schemas.GetUserStateResponse]:
        """
        Retrieves a user application state document or specific parts of it.
        Corresponds to GET /app-state/{docname}.

        Args:
            docname (str): The name of the user state document.
            paths_to_get_str (Optional[str]): Comma-separated paths to retrieve (e.g., 'key1.sub,key2').
            on_behalf_of_user_id (Optional[uuid.UUID]): User ID to act on behalf of (superusers only).

        Returns:
            Optional[us_schemas.GetUserStateResponse]: The retrieved state data, or None on failure.
        """
        logger.info(f"Attempting to get user state for docname: {docname}")
        url = USER_STATE_DETAIL_URL(docname)
        params: Dict[str, Any] = {}
        if paths_to_get_str:
            params["paths_to_get_str"] = paths_to_get_str
        if on_behalf_of_user_id:
            params["on_behalf_of_user_id"] = str(on_behalf_of_user_id)

        try:
            response = await self._client.get(url, params=params if params else None)
            response.raise_for_status()
            response_json = response.json()

            validated_response = us_schemas.GetUserStateResponse.model_validate(response_json)
            logger.info(f"Successfully retrieved user state for docname: {docname}")
            logger.debug(f"Get user state response: {validated_response.model_dump_json(indent=2)}")
            return validated_response
        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting user state {docname}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error getting user state {docname}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error getting user state {docname}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error getting user state {docname}.")
        return None

    async def update_user_state(
        self,
        docname: str,
        updates: List[us_schemas.StateUpdate], # Assuming StateUpdate is a Pydantic model
        on_behalf_of_user_id: Optional[uuid.UUID] = None
    ) -> Optional[us_schemas.UserState]:
        """
        Applies partial updates to a user application state document.
        Corresponds to PUT /app-state/{docname}.

        Args:
            docname (str): The name of the user state document to update.
            updates (List[us_schemas.StateUpdate]): A list of update operations.
            on_behalf_of_user_id (Optional[uuid.UUID]): User ID to act on behalf of (superusers only).

        Returns:
            Optional[us_schemas.UserState]: The full updated user state, or None on failure.
        """
        logger.info(f"Attempting to update user state for docname: {docname}")
        url = USER_STATE_DETAIL_URL(docname)
        
        # The API expects a body like: {"updates": [...], "on_behalf_of_user_id": "..."}
        # So, construct this payload.
        payload_dict = {
            "updates": [upd.model_dump() for upd in updates] # Convert StateUpdate objects to dicts
        }
        if on_behalf_of_user_id:
            payload_dict["on_behalf_of_user_id"] = str(on_behalf_of_user_id)
        
        # Optional: Validate payload_dict against UpdateUserStateRequest if it's defined and includes on_behalf_of_user_id
        # request_model = us_schemas.UpdateUserStateRequest(updates=updates, on_behalf_of_user_id=on_behalf_of_user_id)
        # payload_to_send = request_model.model_dump(exclude_none=True)
        
        try:
            response = await self._client.put(url, json=payload_dict)
            response.raise_for_status()
            response_json = response.json()

            # The response is the full UserState model
            validated_state = us_schemas.UserState.model_validate(response_json)
            logger.info(f"Successfully updated user state for docname: {docname}")
            logger.debug(f"Update user state response: {validated_state.model_dump_json(indent=2)}")
            return validated_state
        except httpx.HTTPStatusError as e:
            logger.error(f"Error updating user state {docname}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error updating user state {docname}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error updating user state {docname}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error updating user state {docname}.")
        return None

    async def delete_user_state_document(
        self,
        docname: str,
        on_behalf_of_user_id: Optional[uuid.UUID] = None
    ) -> bool:
        """
        Deletes a specific user application state document.
        Corresponds to DELETE /app-state/{docname}.
        Note: The API expects `on_behalf_of_user_id` in the body for DELETE.

        Args:
            docname (str): The name of the document to delete.
            on_behalf_of_user_id (Optional[uuid.UUID]): User ID to act on behalf of (superusers only), sent in body.

        Returns:
            bool: True if deletion was successful (HTTP 204), False otherwise.
        """
        logger.info(f"Attempting to delete user state document: {docname}")
        url = USER_STATE_DETAIL_URL(docname)
        
        # The API's DELETE /app-state/{docname} expects on_behalf_of_user_id in the body.
        # Construct a JSON body: {"on_behalf_of_user_id": "uuid_string_if_provided_else_null_or_omit"}
        # If on_behalf_of_user_id is None, sending an empty dict or a dict with null value depends on server leniency.
        # An empty dict {} might be safer if the server treats missing field as None.
        # Or more explicitly:
        body_payload: Dict[str, Any] = {}
        if on_behalf_of_user_id is not None:
            body_payload["on_behalf_of_user_id"] = str(on_behalf_of_user_id)
        # If on_behalf_of_user_id is None and the field is optional on server, 
        # sending {} or None for json param might be okay.
        # Let's assume an empty dict `json={}` is fine if `on_behalf_of_user_id` is None
        # and the server handles it. Or send `json=None` if no body is intended when it's null.
        # For this implementation, if body_payload is empty, pass None to json.

        try:
            response = await self._client.request("DELETE", url, json=body_payload if body_payload else None)
            response.raise_for_status() # Raises for 4xx/5xx. 204 is success.
            
            if response.status_code == 204: # Successfully deleted
                logger.info(f"Successfully deleted user state document: {docname}")
                return True
            else:
                # This case should ideally be caught by raise_for_status for non-2xx codes,
                # but as a safeguard if server returns 2xx other than 204 for delete.
                logger.warning(f"Delete request for {docname} returned status {response.status_code} but expected 204.")
                return False
        except httpx.HTTPStatusError as e:
            # Specific handling for 404 (Not Found) might be useful if you want to treat "already deleted" as non-error for some flows
            if e.response.status_code == 404:
                 logger.warning(f"User state document {docname} not found for deletion (already deleted or never existed).")
            else:
                logger.error(f"Error deleting user state document {docname}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error deleting user state document {docname}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error deleting user state document {docname}.")
        return False


# --- Example Usage --- (for testing this module directly)
async def main():
    """Demonstrates using the UserStateTestClient with delete, initialize, and update workflow."""
    print("--- Starting User State API Test Client ---")
    
    # =============================================================================
    # CONFIGURATION VARIABLES - Update these values before running
    # =============================================================================
    
    # Document name to delete (if it exists)
    DOCNAME_TO_DELETE = "user_state_example-user-2"  # Update this with your actual docname
    
    # LinkedIn URL for initialization
    LINKEDIN_PROFILE_URL = "https://www.linkedin.com/in/example-user-2/"  # Update this with actual LinkedIn URL
    
    # Organization UUID (for on_behalf_of_user_id parameter)
    ON_BEHALF_OF_USER_ID = "ddf46605-7c10-4549-a2f8-2d180f375f42"  # Update this with actual org UUID
    
    # Convert string UUID to uuid.UUID object if provided
    on_behalf_of_user_id = uuid.UUID(ON_BEHALF_OF_USER_ID) if ON_BEHALF_OF_USER_ID else None
    
    # =============================================================================
    
    created_docname: Optional[str] = None

    try:
        async with AuthenticatedClient() as auth_client:
            print("Authenticated successfully.")
            user_state_tester = UserStateTestClient(auth_client)

            # Step 1: Delete existing user state document
            print(f"\n1. Deleting existing User State Document: {DOCNAME_TO_DELETE}...")
            deleted = await user_state_tester.delete_user_state_document(
                docname=DOCNAME_TO_DELETE, 
                on_behalf_of_user_id=on_behalf_of_user_id
            )
            if deleted:
                print(f"   User state document '{DOCNAME_TO_DELETE}' deleted successfully.")
            else:
                print(f"   Failed to delete or document '{DOCNAME_TO_DELETE}' not found (continuing with initialization).")

            # Step 2: Initialize User State
            print(f"\n2. Initializing User State with LinkedIn URL: {LINKEDIN_PROFILE_URL}...")
            init_response = await user_state_tester.initialize_user_state(
                linkedin_profile_url=LINKEDIN_PROFILE_URL,
                on_behalf_of_user_id=on_behalf_of_user_id
            )
            if init_response and init_response.docname and init_response.user_state:
                created_docname = init_response.docname
                print(f"   User State Initialized. Docname: {created_docname}")
                
                # Display initial onboarded status
                onboarded_entry = init_response.user_state.states.get('onboarded')
                if onboarded_entry:
                    print(f"   Initial 'onboarded' state: {onboarded_entry.state_value}")
                else:
                    print("   Initial 'onboarded' state: Not found in initial user state.")
            else:
                print("   User State initialization failed.")
                return

            # Step 3: Update all onboarded page statuses to True
            if created_docname:
                print(f"\n3. Updating all onboarded page statuses to True for docname: {created_docname}...")
                
                # List of all onboarded pages that need to be set to True
                onboarded_pages = [
                    "page_1_linkedin",
                    "page_2_sources", 
                    "page_3_goals",
                    "page_4_audience",
                    "page_5_time",
                    "page_6_content_perspectives",
                    "page_7_content_beliefs",
                    "page_8_content_pillars",
                    "page_9_strategy",
                    "page_10_dna_summary",
                    "page_11_content_style_analysis",
                    "page_12_style_test"
                ]
                
                # Create StateUpdate objects for each onboarded page
                updates_to_send = []
                for page in onboarded_pages:
                    updates_to_send.append(
                        us_schemas.StateUpdate(
                            keys=["onboarded", page], 
                            update_value=True
                        )
                    )
                
                print(f"   Updating {len(updates_to_send)} onboarded page statuses...")
                
                updated_state = await user_state_tester.update_user_state(
                    docname=created_docname,
                    updates=updates_to_send,
                    on_behalf_of_user_id=on_behalf_of_user_id
                )
                
                if updated_state and updated_state.states:
                    print("   All onboarded page statuses updated successfully.")
                    
                    # Verify the overall onboarded status
                    onboarded_state = updated_state.states.get("onboarded")
                    if onboarded_state:
                        print(f"   Overall 'onboarded' status: {onboarded_state.state_value}")
                        
                        # Display status of each page
                        if onboarded_state.sub_states:
                            print("   Individual page statuses:")
                            for page_name, page_state in onboarded_state.sub_states.items():
                                print(f"     - {page_name}: {page_state.state_value}")
                        
                        if onboarded_state.state_value:
                            print("   ✅ SUCCESS: User is now fully onboarded!")
                        else:
                            print("   ⚠️  WARNING: Overall onboarded status is still False")
                    else:
                        print("   ERROR: Could not find 'onboarded' state in updated response.")
                else:
                    print("   Failed to update onboarded page statuses.")

            # Step 4: Verify final state by getting the document
            if created_docname:
                print(f"\n4. Verifying final state for docname: {created_docname}...")
                final_state = await user_state_tester.get_user_state(
                    docname=created_docname,
                    on_behalf_of_user_id=on_behalf_of_user_id
                )
                if final_state and final_state.retrieved_states:
                    onboarded_status = final_state.retrieved_states.get('onboarded', 'Not found')
                    print(f"   Final verification - 'onboarded' status: {onboarded_status}")
                else:
                    print("   Failed to retrieve final state for verification.")

    except AuthenticationError as e:
        print(f"Authentication Error: {e}")
    except ImportError as e:
        print(f"Import Error: {e}. Check PYTHONPATH and schema locations for user_state_api_schemas.")
    except httpx.ConnectError as e:
        print(f"Connection Error: Could not connect to the API server at BASE URL. Ensure the server is running. Details: {e}")
    except Exception as e:
        print(f"An unexpected error occurred in the main test execution: {e}")
        logger.exception("Main test execution error:")
    finally:
        # Cleanup note - we intentionally keep the created document since the goal is to have it onboarded
        if created_docname:
            print(f"\n--- Workflow completed. Document '{created_docname}' should now be fully onboarded ---")
        
        print("\n--- User State API Test Client Finished ---")

if __name__ == "__main__":
    # Ensure API server is running and config (auth, URLs) is correct.
    # Run this script with:
    # PYTHONPATH=[path_to_project_root] python standalone_test_client/kiwi_client/user_state_client.py
    # (Adjust path as necessary)
    print("Attempting to run UserStateTestClient main function...")
    # To run the main function, uncomment the line below:
    asyncio.run(main())
    print("\nNote: Example usage in main() is designed to be run. ")
    print("Ensure your environment (PYTHONPATH, server availability, credentials) is correctly set up.")
