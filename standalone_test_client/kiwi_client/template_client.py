"""
API Test client for Template endpoints (/templates/).

This client interacts with:
- /templates/prompts/
- /templates/schemas/
"""
import asyncio
import json
import httpx
import logging
import uuid
from typing import Dict, Any, Optional, List, Union, TypeVar

# Import authenticated client and config
from kiwi_client.auth_client import AuthenticatedClient, AuthenticationError
from kiwi_client.test_config import CLIENT_LOG_LEVEL, PROMPT_TEMPLATES_URL, PROMPT_TEMPLATE_DETAIL_URL, PROMPT_TEMPLATES_SEARCH_URL, SCHEMA_TEMPLATES_URL, SCHEMA_TEMPLATE_DETAIL_URL, SCHEMA_TEMPLATES_SEARCH_URL

# Import pydantic for validation
from pydantic import ValidationError, TypeAdapter

# Import relevant schemas from the workflow app client schemas
from kiwi_client.schemas import workflow_api_schemas as wf_schemas


# Setup logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)

# Create TypeAdapters for validating lists of schemas
try:
    PromptTemplateReadListAdapter = TypeAdapter(List[wf_schemas.PromptTemplateRead])
    SchemaTemplateReadListAdapter = TypeAdapter(List[wf_schemas.SchemaTemplateRead])
except (AttributeError, NameError):
    logger.warning("TypeAdapters for TemplateRead lists could not be created.")
    PromptTemplateReadListAdapter = None
    SchemaTemplateReadListAdapter = None

# Type variable for response schemas
T = TypeVar('T')


class TemplateTestClient:
    """
    Provides methods to test the /templates/ endpoints (Prompts and Schemas).
    Uses schemas from kiwi_client.schemas.workflow_api_schemas for requests and response validation.
    """
    def __init__(self, auth_client: AuthenticatedClient):
        """
        Initializes the TemplateTestClient.

        Args:
            auth_client (AuthenticatedClient): An instance of AuthenticatedClient,
                                               assumed to be logged in.
        """
        self._auth_client = auth_client
        self._client: httpx.AsyncClient = auth_client.client
        self._created_prompt_template_id: Optional[uuid.UUID] = None # Store ID for cleanup/chaining
        self._created_schema_template_id: Optional[uuid.UUID] = None # Store ID for cleanup/chaining
        logger.info("TemplateTestClient initialized.")

    # --- Prompt Template Methods ---

    async def create_prompt_template(
        self,
        template_in: wf_schemas.PromptTemplateCreate
    ) -> Optional[wf_schemas.PromptTemplateRead]:
        """
        Tests creating a new prompt template via POST /templates/prompts/.

        Corresponds to the `create_prompt_template` route.

        Args:
            template_in (wf_schemas.PromptTemplateCreate): The prompt template data to create.

        Returns:
        Optional[wf_schemas.PromptTemplateRead]: The parsed and validated created prompt template,
                                                     or None on failure.
        """
        logger.info(f"Attempting to create prompt template: {template_in.name}")
        try:
            # API returns 201 Created, body is PromptTemplateRead
            response = await self._client.post(PROMPT_TEMPLATES_URL, json=template_in.model_dump(exclude_unset=True))
            response.raise_for_status() # Check for HTTP errors (4xx, 5xx)
            response_json = response.json()

            # Validate the response against PromptTemplateRead schema
            validated_template = wf_schemas.PromptTemplateRead.model_validate(response_json)
            self._created_prompt_template_id = validated_template.id
            logger.info(f"Successfully created prompt template ID: {self._created_prompt_template_id}")
            logger.debug(f"Create prompt template response validated: {validated_template.model_dump_json(indent=2)}")
            return validated_template
        except httpx.HTTPStatusError as e:
            logger.error(f"Error creating prompt template: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error creating prompt template: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error creating prompt template: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception("Unexpected error during prompt template creation.")
        return None

    async def list_prompt_templates(
        self,
        skip: int = 0,
        limit: int = 10,
        include_system: bool = True,
        owner_org_id: Optional[Union[str, uuid.UUID]] = None # Superuser only
    ) -> Optional[List[wf_schemas.PromptTemplateRead]]:
        """
        Tests listing prompt templates via GET /templates/prompts/.

        Corresponds to the `list_prompt_templates` route. Query parameters are based
        on `schemas.PromptTemplateListQuery`.

        Args:
            skip (int): Number of templates to skip. Defaults to 0.
            limit (int): Maximum number of templates to return. Defaults to 10.
            include_system (bool): Whether to include system-wide templates. Defaults to True.
            owner_org_id (Optional[Union[str, uuid.UUID]]): Filter by owner org ID (superuser only).

        Returns:
            Optional[List[wf_schemas.PromptTemplateRead]]: A list of parsed and validated prompt templates,
                                                          or None on failure.
        """
        logger.info(f"Attempting to list prompt templates (skip={skip}, limit={limit}, include_system={include_system})...")
        params: Dict[str, Any] = {"skip": skip, "limit": limit, "include_system": include_system}
        if owner_org_id:
            params["owner_org_id"] = str(owner_org_id)

        try:
            # API returns 200 OK, body is List[PromptTemplateRead]
            response = await self._client.get(PROMPT_TEMPLATES_URL, params=params)
            response.raise_for_status()
            response_json = response.json()

            # Validate the response list against List[PromptTemplateRead]
            if PromptTemplateReadListAdapter:
                validated_templates = PromptTemplateReadListAdapter.validate_python(response_json)
                logger.info(f"Successfully listed and validated {len(validated_templates)} prompt templates.")
                logger.debug(f"List prompt templates response (first item): {validated_templates[0].model_dump() if validated_templates else 'None'}")
                return validated_templates
            else:
                logger.warning("Schema validation skipped for list_prompt_templates due to import failure.")
                return response_json # Return raw data if validation unavailable
        except httpx.HTTPStatusError as e:
            logger.error(f"Error listing prompt templates: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error listing prompt templates: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error listing prompt templates: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception("Unexpected error during prompt template listing.")
        return None

    async def get_prompt_template(self, template_id: Union[str, uuid.UUID]) -> Optional[wf_schemas.PromptTemplateRead]:
        """
        Tests getting a specific prompt template by ID via GET /templates/prompts/{template_id}.

        Corresponds to the `get_prompt_template` route.

        Args:
            template_id (Union[str, uuid.UUID]): The ID of the prompt template to retrieve.

        Returns:
            Optional[wf_schemas.PromptTemplateRead]: The parsed and validated prompt template, or None on failure.
        """
        template_id_str = str(template_id)
        logger.info(f"Attempting to get prompt template ID: {template_id_str}")
        url = PROMPT_TEMPLATE_DETAIL_URL(template_id_str)
        try:
            # API returns 200 OK, body is PromptTemplateRead
            response = await self._client.get(url)
            response.raise_for_status()
            response_json = response.json()

            # Validate the response against PromptTemplateRead schema
            validated_template = wf_schemas.PromptTemplateRead.model_validate(response_json)
            logger.info(f"Successfully retrieved and validated prompt template ID: {validated_template.id}")
            logger.debug(f"Get prompt template response validated: {validated_template.model_dump_json(indent=2)}")
            return validated_template
        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting prompt template {template_id_str}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error getting prompt template {template_id_str}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error getting prompt template {template_id_str}: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception(f"Unexpected error getting prompt template {template_id_str}.")
        return None

    async def update_prompt_template(
        self,
        template_id: Union[str, uuid.UUID],
        template_update: wf_schemas.PromptTemplateUpdate
    ) -> Optional[wf_schemas.PromptTemplateRead]:
        """
        Tests updating a specific prompt template via PUT /templates/prompts/{template_id}.

        Corresponds to the `update_prompt_template` route.

        Args:
            template_id (Union[str, uuid.UUID]): The ID of the prompt template to update.
            template_update (wf_schemas.PromptTemplateUpdate): An object containing the fields to update.

        Returns:
            Optional[wf_schemas.PromptTemplateRead]: The parsed and validated updated prompt template,
                                                    or None on failure.
        """
        template_id_str = str(template_id)
        logger.info(f"Attempting to update prompt template ID: {template_id_str}")
        url = PROMPT_TEMPLATE_DETAIL_URL(template_id_str)
        try:
            # API returns 200 OK, body is PromptTemplateRead
            # Use exclude_unset=True to only send fields present in the update object
            response = await self._client.put(url, json=template_update.model_dump(exclude_unset=True))
            response.raise_for_status()
            response_json = response.json()

            # Validate the response against PromptTemplateRead schema
            validated_template = wf_schemas.PromptTemplateRead.model_validate(response_json)
            logger.info(f"Successfully updated and validated prompt template ID: {validated_template.id}")
            logger.debug(f"Update prompt template response validated: {validated_template.model_dump_json(indent=2)}")
            return validated_template
        except httpx.HTTPStatusError as e:
            logger.error(f"Error updating prompt template {template_id_str}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error updating prompt template {template_id_str}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error updating prompt template {template_id_str}: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception(f"Unexpected error updating prompt template {template_id_str}.")
        return None

    async def delete_prompt_template(self, template_id: Union[str, uuid.UUID]) -> bool:
        """
        Tests deleting a specific prompt template via DELETE /templates/prompts/{template_id}.

        Corresponds to the `delete_prompt_template` route which returns 204 No Content.

        Args:
            template_id (Union[str, uuid.UUID]): The ID of the prompt template to delete.

        Returns:
            bool: True if deletion was successful (status code 204), False otherwise.
        """
        template_id_str = str(template_id)
        logger.info(f"Attempting to delete prompt template ID: {template_id_str}")
        url = PROMPT_TEMPLATE_DETAIL_URL(template_id_str)
        try:
            response = await self._client.delete(url)
            response.raise_for_status() # Will raise for 4xx/5xx responses

            if response.status_code == 204:
                 logger.info(f"Successfully deleted prompt template ID: {template_id_str}")
                 # Clear the stored ID if it matches the deleted one
                 if self._created_prompt_template_id and str(self._created_prompt_template_id) == template_id_str:
                     self._created_prompt_template_id = None
                 return True
            else:
                # This case should ideally not happen if raise_for_status works correctly for 2xx
                logger.warning(f"Prompt template deletion returned unexpected status code: {response.status_code}")
                return False
        except httpx.HTTPStatusError as e:
            # Handle expected errors like 404 Not Found gracefully
            if e.response.status_code == 404:
                logger.warning(f"Attempted to delete non-existent prompt template {template_id_str} (404).")
            else:
                logger.error(f"Error deleting prompt template {template_id_str}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error deleting prompt template {template_id_str}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error deleting prompt template {template_id_str}.")
        return False

    async def search_prompt_templates(
        self,
        search_query: wf_schemas.PromptTemplateSearchQuery
    ) -> Optional[List[wf_schemas.PromptTemplateRead]]:
        """
        Tests searching for prompt templates via POST /templates/prompts/search.

        Corresponds to the `search_prompt_templates` route.

        Args:
            search_query (wf_schemas.PromptTemplateSearchQuery): The search criteria.

        Returns:
            Optional[List[wf_schemas.PromptTemplateRead]]: A list of matching prompt templates, or None on failure.
        """
        logger.info(f"Searching prompt templates with query: {search_query.model_dump()}")
        try:
            response = await self._client.post(PROMPT_TEMPLATES_SEARCH_URL, json=search_query.model_dump())
            response.raise_for_status()
            response_json = response.json()

            # Validate the response list
            if PromptTemplateReadListAdapter:
                validated_templates = PromptTemplateReadListAdapter.validate_python(response_json)
                logger.info(f"Found {len(validated_templates)} prompt templates matching search criteria.")
                return validated_templates
            else:
                logger.warning("Schema validation skipped for search_prompt_templates due to import failure.")
                return response_json
        except httpx.HTTPStatusError as e:
            logger.error(f"Error searching prompt templates: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error searching prompt templates: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error searching prompt templates: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception("Unexpected error during prompt template search.")
        return None


    # --- Schema Template Methods ---

    async def create_schema_template(
        self,
        template_in: wf_schemas.SchemaTemplateCreate
    ) -> Optional[wf_schemas.SchemaTemplateRead]:
        """
        Tests creating a new schema template via POST /templates/schemas/.

        Corresponds to the `create_schema_template` route.

        Args:
            template_in (wf_schemas.SchemaTemplateCreate): The schema template data to create.

        Returns:
            Optional[wf_schemas.SchemaTemplateRead]: The parsed and validated created schema template,
                                                     or None on failure.
        """
        logger.info(f"Attempting to create schema template: {template_in.name}")
        try:
            # API returns 201 Created, body is SchemaTemplateRead
            response = await self._client.post(SCHEMA_TEMPLATES_URL, json=template_in.model_dump(exclude_unset=True))
            response.raise_for_status() # Check for HTTP errors
            response_json = response.json()

            # Validate the response against SchemaTemplateRead schema
            validated_template = wf_schemas.SchemaTemplateRead.model_validate(response_json)
            self._created_schema_template_id = validated_template.id
            logger.info(f"Successfully created schema template ID: {self._created_schema_template_id}")
            logger.debug(f"Create schema template response validated: {validated_template.model_dump_json(indent=2)}")
            return validated_template
        except httpx.HTTPStatusError as e:
            logger.error(f"Error creating schema template: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error creating schema template: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error creating schema template: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception("Unexpected error during schema template creation.")
        return None

    async def list_schema_templates(
        self,
        skip: int = 0,
        limit: int = 10,
        include_system: bool = True,
        owner_org_id: Optional[Union[str, uuid.UUID]] = None # Superuser only
    ) -> Optional[List[wf_schemas.SchemaTemplateRead]]:
        """
        Tests listing schema templates via GET /templates/schemas/.

        Corresponds to the `list_schema_templates` route. Query parameters are based
        on `schemas.SchemaTemplateListQuery`.

        Args:
            skip (int): Number of templates to skip. Defaults to 0.
            limit (int): Maximum number of templates to return. Defaults to 10.
            include_system (bool): Whether to include system-wide templates. Defaults to True.
            owner_org_id (Optional[Union[str, uuid.UUID]]): Filter by owner org ID (superuser only).

        Returns:
            Optional[List[wf_schemas.SchemaTemplateRead]]: A list of parsed and validated schema templates,
                                                          or None on failure.
        """
        logger.info(f"Attempting to list schema templates (skip={skip}, limit={limit}, include_system={include_system})...")
        params: Dict[str, Any] = {"skip": skip, "limit": limit, "include_system": include_system}
        if owner_org_id:
            params["owner_org_id"] = str(owner_org_id)

        try:
            # API returns 200 OK, body is List[SchemaTemplateRead]
            response = await self._client.get(SCHEMA_TEMPLATES_URL, params=params)
            response.raise_for_status()
            response_json = response.json()

            # Validate the response list against List[SchemaTemplateRead]
            if SchemaTemplateReadListAdapter:
                validated_templates = SchemaTemplateReadListAdapter.validate_python(response_json)
                logger.info(f"Successfully listed and validated {len(validated_templates)} schema templates.")
                logger.debug(f"List schema templates response (first item): {validated_templates[0].model_dump() if validated_templates else 'None'}")
                return validated_templates
            else:
                logger.warning("Schema validation skipped for list_schema_templates due to import failure.")
                return response_json # Return raw data if validation unavailable
        except httpx.HTTPStatusError as e:
            logger.error(f"Error listing schema templates: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error listing schema templates: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error listing schema templates: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception("Unexpected error during schema template listing.")
        return None

    async def get_schema_template(self, template_id: Union[str, uuid.UUID]) -> Optional[wf_schemas.SchemaTemplateRead]:
        """
        Tests getting a specific schema template by ID via GET /templates/schemas/{template_id}.

        Corresponds to the `get_schema_template` route.

        Args:
            template_id (Union[str, uuid.UUID]): The ID of the schema template to retrieve.

        Returns:
            Optional[wf_schemas.SchemaTemplateRead]: The parsed and validated schema template, or None on failure.
        """
        template_id_str = str(template_id)
        logger.info(f"Attempting to get schema template ID: {template_id_str}")
        url = SCHEMA_TEMPLATE_DETAIL_URL(template_id_str)
        try:
            # API returns 200 OK, body is SchemaTemplateRead
            response = await self._client.get(url)
            response.raise_for_status()
            response_json = response.json()

            # Validate the response against SchemaTemplateRead schema
            validated_template = wf_schemas.SchemaTemplateRead.model_validate(response_json)
            logger.info(f"Successfully retrieved and validated schema template ID: {validated_template.id}")
            logger.debug(f"Get schema template response validated: {validated_template.model_dump_json(indent=2)}")
            return validated_template
        except httpx.HTTPStatusError as e:
            logger.error(f"Error getting schema template {template_id_str}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error getting schema template {template_id_str}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error getting schema template {template_id_str}: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception(f"Unexpected error getting schema template {template_id_str}.")
        return None

    async def update_schema_template(
        self,
        template_id: Union[str, uuid.UUID],
        template_update: wf_schemas.SchemaTemplateUpdate
    ) -> Optional[wf_schemas.SchemaTemplateRead]:
        """
        Tests updating a specific schema template via PUT /templates/schemas/{template_id}.

        Corresponds to the `update_schema_template` route.

        Args:
            template_id (Union[str, uuid.UUID]): The ID of the schema template to update.
            template_update (wf_schemas.SchemaTemplateUpdate): An object containing the fields to update.

        Returns:
            Optional[wf_schemas.SchemaTemplateRead]: The parsed and validated updated schema template,
                                                    or None on failure.
        """
        template_id_str = str(template_id)
        logger.info(f"Attempting to update schema template ID: {template_id_str}")
        url = SCHEMA_TEMPLATE_DETAIL_URL(template_id_str)
        try:
            # API returns 200 OK, body is SchemaTemplateRead
            # Use exclude_unset=True to only send fields present in the update object
            response = await self._client.put(url, json=template_update.model_dump(exclude_unset=True))
            response.raise_for_status()
            response_json = response.json()

            # Validate the response against SchemaTemplateRead schema
            validated_template = wf_schemas.SchemaTemplateRead.model_validate(response_json)
            logger.info(f"Successfully updated and validated schema template ID: {validated_template.id}")
            logger.debug(f"Update schema template response validated: {validated_template.model_dump_json(indent=2)}")
            return validated_template
        except httpx.HTTPStatusError as e:
            logger.error(f"Error updating schema template {template_id_str}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error updating schema template {template_id_str}: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error updating schema template {template_id_str}: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception(f"Unexpected error updating schema template {template_id_str}.")
        return None

    async def delete_schema_template(self, template_id: Union[str, uuid.UUID]) -> bool:
        """
        Tests deleting a specific schema template via DELETE /templates/schemas/{template_id}.

        Corresponds to the `delete_schema_template` route which returns 204 No Content.

        Args:
            template_id (Union[str, uuid.UUID]): The ID of the schema template to delete.

        Returns:
            bool: True if deletion was successful (status code 204), False otherwise.
        """
        template_id_str = str(template_id)
        logger.info(f"Attempting to delete schema template ID: {template_id_str}")
        url = SCHEMA_TEMPLATE_DETAIL_URL(template_id_str)
        try:
            response = await self._client.delete(url)
            response.raise_for_status() # Will raise for 4xx/5xx responses

            if response.status_code == 204:
                 logger.info(f"Successfully deleted schema template ID: {template_id_str}")
                 # Clear the stored ID if it matches the deleted one
                 if self._created_schema_template_id and str(self._created_schema_template_id) == template_id_str:
                     self._created_schema_template_id = None
                 return True
            else:
                 logger.warning(f"Schema template deletion returned unexpected status code: {response.status_code}")
                 return False
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Attempted to delete non-existent schema template {template_id_str} (404).")
            else:
                logger.error(f"Error deleting schema template {template_id_str}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error deleting schema template {template_id_str}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error deleting schema template {template_id_str}.")
        return False

    async def search_schema_templates(
        self,
        search_query: wf_schemas.SchemaTemplateSearchQuery
    ) -> Optional[List[wf_schemas.SchemaTemplateRead]]:
        """
        Tests searching for schema templates via POST /templates/schemas/search.

        Corresponds to the `search_schema_templates` route.

        Args:
            search_query (wf_schemas.SchemaTemplateSearchQuery): The search criteria.

        Returns:
            Optional[List[wf_schemas.SchemaTemplateRead]]: A list of matching schema templates, or None on failure.
        """
        logger.info(f"Searching schema templates with query: {search_query.model_dump()}")
        try:
            response = await self._client.post(SCHEMA_TEMPLATES_SEARCH_URL, json=search_query.model_dump())
            response.raise_for_status()
            response_json = response.json()

            # Validate the response list
            if SchemaTemplateReadListAdapter:
                validated_templates = SchemaTemplateReadListAdapter.validate_python(response_json)
                logger.info(f"Found {len(validated_templates)} schema templates matching search criteria.")
                return validated_templates
            else:
                logger.warning("Schema validation skipped for search_schema_templates due to import failure.")
                return response_json
        except httpx.HTTPStatusError as e:
            logger.error(f"Error searching schema templates: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error searching schema templates: {e}")
        except ValidationError as e:
            logger.error(f"Response validation error searching schema templates: {e}")
            logger.debug(f"Invalid response JSON: {response_json}")
        except Exception as e:
            logger.exception("Unexpected error during schema template search.")
        return None

    # --- Helper properties ---
    @property
    def created_prompt_template_id(self) -> Optional[uuid.UUID]:
        """Returns the UUID of the last successfully created prompt template in this session."""
        return self._created_prompt_template_id

    @property
    def created_schema_template_id(self) -> Optional[uuid.UUID]:
        """Returns the UUID of the last successfully created schema template in this session."""
        return self._created_schema_template_id


# --- Example Usage --- (for testing this module directly)
async def main():
    """Demonstrates using the TemplateTestClient."""
    print("--- Starting Template API Test --- ")
    temp_prompt_id: Optional[uuid.UUID] = None
    temp_schema_id: Optional[uuid.UUID] = None
    try:
        async with AuthenticatedClient() as auth_client:
            print("Authenticated.")
            template_tester = TemplateTestClient(auth_client)

            # --- Test Prompt Templates ---
            print("\n--- Testing Prompt Templates ---")

            # 1. Create Prompt Template
            print("\n1. Creating Prompt Template...")
            prompt_create_data = wf_schemas.PromptTemplateCreate(
                name=f"Client Test Prompt {uuid.uuid4().hex[:6]}",
                description="A prompt template created via test client.",
                template_content="This is a test prompt for {{entity}}.",
                variables=[{"name": "entity", "description": "The entity"}],
                version="1.0.0",
                is_public=False,
                is_system_entity=False # Assume regular user cannot create system entities
            )
            created_prompt = await template_tester.create_prompt_template(prompt_create_data)
            if created_prompt:
                temp_prompt_id = created_prompt.id
                print(f"   Prompt Template Created: ID = {temp_prompt_id}, Name = {created_prompt.name}")
            else:
                print("   Prompt Template creation failed.")
                # Optionally stop or continue based on test requirements
                # return

            # 2. List Prompt Templates
            if temp_prompt_id: # Only proceed if creation was successful
                print("\n2. Listing Prompt Templates...")
                prompt_list = await template_tester.list_prompt_templates(limit=5, include_system=False)
                if prompt_list is not None:
                    print(f"   Found {len(prompt_list)} prompt templates (limit 5, non-system).")
                    found_prompt = next((p for p in prompt_list if p.id == temp_prompt_id), None)
                    if found_prompt:
                        print(f"   Newly created prompt template {temp_prompt_id} found in list.")
                    else:
                        print(f"   WARN: Newly created prompt template {temp_prompt_id} not found in first 5.")
                else:
                    print("   Prompt Template listing failed.")

            # 3. Get Prompt Template
            if temp_prompt_id:
                print(f"\n3. Getting Prompt Template {temp_prompt_id}...")
                fetched_prompt = await template_tester.get_prompt_template(temp_prompt_id)
                if fetched_prompt:
                    print(f"   Successfully fetched prompt template: {fetched_prompt.name}")
                    assert fetched_prompt.id == temp_prompt_id
                else:
                    print("   Failed to fetch prompt template.")

            # 4. Update Prompt Template
            if temp_prompt_id:
                print(f"\n4. Updating Prompt Template {temp_prompt_id}...")
                prompt_update_data = wf_schemas.PromptTemplateUpdate(description="Updated description.")
                updated_prompt = await template_tester.update_prompt_template(temp_prompt_id, prompt_update_data)
                if updated_prompt:
                    print(f"   Successfully updated prompt template. New Description: {updated_prompt.description}")
                    assert updated_prompt.description == prompt_update_data.description
                else:
                    print("   Failed to update prompt template.")

            # 5. Search Prompt Templates
            if temp_prompt_id:
                print(f"\n5. Searching for Prompt Template '{prompt_create_data.name}'...")
                search_query_prompt = wf_schemas.PromptTemplateSearchQuery(name=prompt_create_data.name, version=prompt_create_data.version)
                search_results_prompt = await template_tester.search_prompt_templates(search_query_prompt)
                if search_results_prompt is not None:
                    print(f"   Found {len(search_results_prompt)} results.")
                    found_in_search = any(p.id == temp_prompt_id for p in search_results_prompt)
                    print(f"   Newly created prompt template found in search: {found_in_search}")
                else:
                     print("   Prompt template search failed.")

            # 6. Delete Prompt Template
            if temp_prompt_id:
                print(f"\n6. Deleting Prompt Template {temp_prompt_id}...")
                deleted_prompt = await template_tester.delete_prompt_template(temp_prompt_id)
                if deleted_prompt:
                    print(f"   Prompt Template {temp_prompt_id} successfully deleted.")
                    # Verify deletion
                    verify_fetch = await template_tester.get_prompt_template(temp_prompt_id)
                    if verify_fetch is None:
                        print("   Verification successful: Prompt template not found after deletion.")
                    else:
                        print("   WARN: Prompt template still found after attempting deletion.")
                    temp_prompt_id = None
                else:
                    print("   Failed to delete prompt template.")

            # --- Test Schema Templates ---
            print("\n--- Testing Schema Templates ---")

            # 1. Create Schema Template
            print("\n1. Creating Schema Template...")
            schema_create_data = wf_schemas.SchemaTemplateCreate(
                name=f"Client Test Schema {uuid.uuid4().hex[:6]}",
                description="A schema template created via test client.",
                json_schema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
                    "required": ["name"]
                },
                version="1.0.0",
                is_public=False,
                is_system_entity=False # Assume regular user cannot create system entities
            )
            created_schema = await template_tester.create_schema_template(schema_create_data)
            if created_schema:
                temp_schema_id = created_schema.id
                print(f"   Schema Template Created: ID = {temp_schema_id}, Name = {created_schema.name}")
            else:
                print("   Schema Template creation failed.")
                # return # Optional: stop if creation failed

            # 2. List Schema Templates
            if temp_schema_id:
                print("\n2. Listing Schema Templates...")
                schema_list = await template_tester.list_schema_templates(limit=5, include_system=False)
                if schema_list is not None:
                    print(f"   Found {len(schema_list)} schema templates (limit 5, non-system).")
                    found_schema = next((s for s in schema_list if s.id == temp_schema_id), None)
                    if found_schema:
                        print(f"   Newly created schema template {temp_schema_id} found in list.")
                    else:
                        print(f"   WARN: Newly created schema template {temp_schema_id} not found in first 5.")
                else:
                    print("   Schema Template listing failed.")

            # 3. Get Schema Template
            if temp_schema_id:
                print(f"\n3. Getting Schema Template {temp_schema_id}...")
                fetched_schema = await template_tester.get_schema_template(temp_schema_id)
                if fetched_schema:
                    print(f"   Successfully fetched schema template: {fetched_schema.name}")
                    assert fetched_schema.id == temp_schema_id
                else:
                    print("   Failed to fetch schema template.")

            # 4. Update Schema Template
            if temp_schema_id:
                print(f"\n4. Updating Schema Template {temp_schema_id}...")
                schema_update_data = wf_schemas.SchemaTemplateUpdate(description="Updated schema description.")
                updated_schema = await template_tester.update_schema_template(temp_schema_id, schema_update_data)
                if updated_schema:
                    print(f"   Successfully updated schema template. New Description: {updated_schema.description}")
                    assert updated_schema.description == schema_update_data.description
                else:
                    print("   Failed to update schema template.")

            # 5. Search Schema Templates
            if temp_schema_id:
                print(f"\n5. Searching for Schema Template '{schema_create_data.name}'...")
                search_query_schema = wf_schemas.SchemaTemplateSearchQuery(name=schema_create_data.name, version=schema_create_data.version)
                search_results_schema = await template_tester.search_schema_templates(search_query_schema)
                if search_results_schema is not None:
                    print(f"   Found {len(search_results_schema)} results.")
                    found_in_search = any(s.id == temp_schema_id for s in search_results_schema)
                    print(f"   Newly created schema template found in search: {found_in_search}")
                else:
                     print("   Schema template search failed.")

            # 6. Delete Schema Template
            if temp_schema_id:
                print(f"\n6. Deleting Schema Template {temp_schema_id}...")
                deleted_schema = await template_tester.delete_schema_template(temp_schema_id)
                if deleted_schema:
                    print(f"   Schema Template {temp_schema_id} successfully deleted.")
                    # Verify deletion
                    verify_fetch = await template_tester.get_schema_template(temp_schema_id)
                    if verify_fetch is None:
                        print("   Verification successful: Schema template not found after deletion.")
                    else:
                        print("   WARN: Schema template still found after attempting deletion.")
                    temp_schema_id = None
                else:
                    print("   Failed to delete schema template.")

    except AuthenticationError as e:
        print(f"Authentication Error: {e}")
    except ImportError as e:
        print(f"Import Error: {e}. Check schemas location and imports.")
    except Exception as e:
        print(f"An unexpected error occurred in the main test execution: {e}")
        logger.exception("Main test execution error:")
    finally:
        # --- Cleanup ---
        # Attempt cleanup if an error occurred before delete and IDs exist
        cleanup_needed = temp_prompt_id or temp_schema_id
        if cleanup_needed:
            print("\n--- Attempting Final Cleanup ---")
            try:
                # Need a new client for cleanup if the main context manager exited
                async with AuthenticatedClient() as cleanup_auth_client:
                    cleanup_tester = TemplateTestClient(cleanup_auth_client)
                    if temp_prompt_id:
                        print(f"   Cleaning up Prompt Template {temp_prompt_id}...")
                        await cleanup_tester.delete_prompt_template(temp_prompt_id)
                        print(f"      Prompt Template {temp_prompt_id} cleanup attempted.")
                    if temp_schema_id:
                        print(f"   Cleaning up Schema Template {temp_schema_id}...")
                        await cleanup_tester.delete_schema_template(temp_schema_id)
                        print(f"      Schema Template {temp_schema_id} cleanup attempted.")
            except Exception as cleanup_e:
                print(f"   Cleanup failed: {cleanup_e}")

        print("--- Template API Test Finished --- ")

if __name__ == "__main__":
    # Ensure API server is running and config/schemas are correct
    # Run with: poetry run python -m kiwi_client.template_client
    print("Running Template Test Client main function...")
    asyncio.run(main()) # Uncomment to execute the test sequence
    print("\nNote: Example usage in main() is commented out by default. Uncomment `asyncio.run(main())` to execute.")
    print("Ensure the backend server is running and accessible.")
