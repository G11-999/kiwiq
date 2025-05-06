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
    """Demonstrates using the UserStateTestClient."""
    print("--- Starting User State API Test Client ---")
    
    # Replace with a real LinkedIn URL for testing initialization
    # IMPORTANT: Using a generic placeholder, as real LinkedIn URLs might be sensitive
    # or lead to actual scraping attempts if the backend is live.
    # For a true E2E test, a controlled, non-personal, or mock LinkedIn URL should be used.
    sample_linkedin_url = "https://www.linkedin.com/in/johndoe-tester" 
    # This will be used by the API to derive a docname, e.g., "johndoe-tester"

    created_docname: Optional[str] = None

    try:
        async with AuthenticatedClient() as auth_client:

            print("Authenticated successfully.")
            user_state_tester = UserStateTestClient(auth_client)

            # 1. Initialize User State
            print(f"\n1. Initializing User State with LinkedIn URL: {sample_linkedin_url}...")
            init_response = await user_state_tester.initialize_user_state(linkedin_profile_url=sample_linkedin_url)
            if init_response and init_response.docname and init_response.user_state:
                created_docname = init_response.docname
                print(f"   User State Initialized. Docname: {created_docname}")
                
                # Correctly access the 'is_active' state value from the UserStateEntry
                # init_response.user_state.states is Dict[str, UserStateEntry]
                # .get('is_active') returns a UserStateEntry object or None
                is_active_entry: Optional[us_schemas.UserStateEntry] = init_response.user_state.states.get('is_active')
                if is_active_entry:
                    # Access the 'state_value' attribute directly from the UserStateEntry object
                    initial_is_active_value: Any = is_active_entry.state_value
                    print(f"   Initial 'is_active' state: {initial_is_active_value}")
                else:
                    # Handle the case where 'is_active' might not be in the states dictionary
                    print("   Initial 'is_active' state: Not found in initial user state.")
            else:
                print("   User State initialization failed.")
                # If initialization failed, we might not have a docname to continue with.
                # Depending on the test, either return or try to use a known docname if applicable.
                # For this flow, we'll stop if init fails.
                return


            # 2. Get User State
            if created_docname:
                print(f"\n2. Getting User State for docname: {created_docname}...")
                get_response = await user_state_tester.get_user_state(docname=created_docname) # paths_to_get_str is None
                if get_response and get_response.retrieved_states:
                    # When get_user_state is called without paths_to_get_str, the server's get_state method
                    # returns a dictionary where keys are top-level state names (e.g., "is_active")
                    # and values are the actual state_value (not the UserStateEntry model).
                    # The original key f'{created_docname}/is_active' was incorrect for this case.
                    retrieved_is_active_value: Any = get_response.retrieved_states.get('is_active', 'N/A (not found)')
                    print(f"   Successfully retrieved user state. 'is_active': {retrieved_is_active_value}")
                    
                    # The comment below is still relevant for understanding how paths_to_get_str works.
                    # The key in retrieved_states might be just "is_active" if paths_to_get_str is not used or is for top level.
                    # The current UserState.get_state returns values for specific paths like "key1/subkey"
                    # Let's try to get a specific known path from the default init structure
                    specific_path_get = await user_state_tester.get_user_state(docname=created_docname, paths_to_get_str="is_active,linkedin_profile_url")
                    if specific_path_get and specific_path_get.retrieved_states:
                        print(f"   Retrieved 'is_active': {specific_path_get.retrieved_states.get('is_active')}")
                        print(f"   Retrieved 'linkedin_profile_url': {specific_path_get.retrieved_states.get('linkedin_profile_url')}")

                else:
                    print(f"   Failed to get user state for {created_docname}.")

            # 3. List User State Documents
            print("\n3. Listing User State Documents...")
            list_response = await user_state_tester.list_user_state_documents()
            if list_response and list_response.docnames is not None: # Check for None as empty list is valid
                print(f"   Found {len(list_response.docnames)} documents: {list_response.docnames}")
                if created_docname and created_docname in list_response.docnames:
                    print(f"   Newly created docname '{created_docname}' found in list.")
                elif created_docname:
                    print(f"   WARN: Newly created docname '{created_docname}' NOT found in list.")
            else:
                print("   Failed to list user state documents or no documents found.")

            # 4. List Active User State Docnames
            print("\n4. Listing Active User State Docnames...")
            active_list_response = await user_state_tester.list_active_user_state_docnames()
            if active_list_response and active_list_response.active_docnames is not None:
                print(f"   Found {len(active_list_response.active_docnames)} active documents: {active_list_response.active_docnames}")
                # The default initialized state should have 'is_active': True
                if created_docname and created_docname in active_list_response.active_docnames:
                     print(f"   Docname '{created_docname}' is listed as active.")
                elif created_docname:
                     print(f"   WARN: Docname '{created_docname}' is NOT listed as active, but was expected to be.")
            else:
                print("   Failed to list active user state documents or no active documents found.")


            # 5. Update User State
            if created_docname:
                print(f"\n5. Updating User State for docname: {created_docname}...")
                # Example: Update the 'is_active' state to False, and a sub-state of 'onboarded'
                # Ensure StateUpdate schema matches what the client expects.
                # Assuming us_schemas.StateUpdate can be instantiated like this:
                updates_payload = [
                    us_schemas.StateUpdate(keys=["is_active"], update_value=False, set_parents=True),
                    us_schemas.StateUpdate(keys=["onboarded", "page_1_linkedin", "state_value"], update_value=True, set_parents=True)
                ]
                # Need to correct the path for page_1_linkedin value. It's directly state_value
                # The UserStateEntry model itself: state_value.
                # So path would be "onboarded.page_1_linkedin" and then update its 'state_value'
                # The API `update.keys` are `List[str]`.
                # The StateUpdate model in app_state.py has `keys: List[str]` for path and `update_value: Any`.
                # My `us_schemas.StateUpdate` above is an example, ensure actual schema fields.
                # Assuming StateUpdate model is {keys: List[str], update_value: Any, set_parents: bool}
                
                # Correct usage for updates if StateUpdate is a Pydantic model:
                updates_to_send = [
                    us_schemas.StateUpdate(keys=["is_active"], update_value=False, set_parents=True),
                    # The path to a sub-state's value is typically just to the sub-state entry,
                    # and the update_value applies to its .state_value field.
                    # Example path to update a sub-state's value: ['onboarded', 'page_1_linkedin']
                    # The value 'True' will be applied to 'page_1_linkedin.state_value'
                    us_schemas.StateUpdate(keys=["onboarded", "page_1_linkedin"], update_value=True, set_parents=True)

                ]

                updated_state = await user_state_tester.update_user_state(
                    docname=created_docname,
                    updates=updates_to_send
                )
                if updated_state and updated_state.states:
                    print("   User State updated successfully.")
                    # Verify the update
                    is_active_state = updated_state.states.get("is_active")
                    if is_active_state:
                        print(f"   New 'is_active' state: {is_active_state.state_value}")
                        assert is_active_state.state_value is False, "is_active state was not updated to False!"
                    
                    onboarded_state = updated_state.states.get("onboarded")
                    if onboarded_state and onboarded_state.sub_states:
                        page_1_linkedin = onboarded_state.sub_states.get("page_1_linkedin")
                        if page_1_linkedin:
                             print(f"   New 'onboarded.page_1_linkedin.state_value': {page_1_linkedin.state_value}")
                             assert page_1_linkedin.state_value is True, "page_1_linkedin was not updated!"
                        # 'onboarded' state_value itself should recompute if its sub_states_combine_logic is AND
                        # and all its children become true.
                        print(f"   Overall 'onboarded' state_value after update: {onboarded_state.state_value}")


                else:
                    print("   Failed to update user state.")
            
            # 6. Delete User State Document
            if created_docname:
                print(f"\n6. Deleting User State Document: {created_docname}...")
                deleted = await user_state_tester.delete_user_state_document(docname=created_docname)
                if deleted:
                    print(f"   User state document '{created_docname}' deleted successfully.")
                    
                    # Verify deletion by trying to get it again (should fail with 404)
                    print(f"   Verifying deletion by trying to get '{created_docname}' again...")
                    verify_get = await user_state_tester.get_user_state(docname=created_docname)
                    if verify_get is None: # Expecting None due to 404 error handled by client
                        print("   Verification successful: Document not found after deletion.")
                    else:
                        print(f"   WARN: Document '{created_docname}' still found after deletion.")
                    
                    created_docname = None # Clear after successful deletion and verification
                else:
                    print(f"   Failed to delete user state document '{created_docname}'.")

    except AuthenticationError as e:
        print(f"Authentication Error: {e}")
    except ImportError as e:
        # This might catch the schema import error if not handled by the fallback
        print(f"Import Error: {e}. Check PYTHONPATH and schema locations for user_state_api_schemas.")
    except httpx.ConnectError as e:
        print(f"Connection Error: Could not connect to the API server at BASE URL. Ensure the server is running. Details: {e}")
    except Exception as e:
        print(f"An unexpected error occurred in the main test execution: {e}")
        logger.exception("Main test execution error:")
    finally:
        # Cleanup: If a document was created but not deleted due to an error
        if created_docname:
            print(f"\n--- Attempting Cleanup: Deleting user state document '{created_docname}' ---")
            # Need a new client session for cleanup if the main one closed due to error
            try:
                async with AuthenticatedClient() as cleanup_auth_client:
                    cleanup_tester = UserStateTestClient(cleanup_auth_client)
                    await cleanup_tester.delete_user_state_document(created_docname)
                    print(f"   Cleanup: Document '{created_docname}' deleted.")
            except Exception as cleanup_e:
                print(f"   Cleanup failed for doc '{created_docname}': {cleanup_e}")
        
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
