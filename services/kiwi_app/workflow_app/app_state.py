"""
Manages user-specific application state, stored as unversioned documents
in CustomerDataService.
"""

import uuid
from typing import List, Dict, Any, Optional, Type, Literal, Union, cast
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, status, Path, Query, Body
from pydantic import BaseModel, Field, model_validator, PrivateAttr, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_async_db_dependency
from kiwi_app.auth.dependencies import get_current_active_verified_user
from kiwi_app.auth.models import User
from kiwi_app.workflow_app.dependencies import (
    get_active_org_id,
    RequireOrgDataReadActiveOrg, # Assuming read for GET
    RequireOrgDataWriteActiveOrg, # Assuming write for POST/PUT
    get_customer_data_service_dependency,
)
from kiwi_app.workflow_app.service_customer_data import CustomerDataService
from kiwi_app.utils import get_kiwi_logger
from kiwi_app.settings import settings

# Attempt to import from scraper_service. If not found, log a warning.
# This is for development flexibility; in a deployed environment, this should be resolvable.
from scraper_service.client.schemas.job_config_schema import parse_linkedin_url

app_state_logger = get_kiwi_logger(name="kiwi_app.app_state")

# --- Type Mapping ---

# Supported types for state values
TYPE_MAP: Dict[str, Type] = {
    "int": int,
    "str": str,
    "bool": bool,
    "float": float,
    "list": list,
    "dict": dict,
}
SUPPORTED_TYPE_NAMES = Literal["int", "str", "bool", "float", "list", "dict"]

# --- Pydantic Models ---

class UserStateEntry(BaseModel):
    """
    Represents a single entry in the user's application state.
    It can hold a value of a specified type and can have nested sub-states.
    """
    state_value_type_name: SUPPORTED_TYPE_NAMES = Field(
        ...,
        description="The name of the type for state_value (e.g., 'int', 'str', 'bool')."
    )
    description: str = Field(
        "",
        description="A human-readable description of what this state entry represents."
    )
    state_value: Any = Field(
        ...,
        description="The actual value of this state entry, validated against state_value_type_name."
    )
    sub_states: Dict[str, 'UserStateEntry'] = Field(
        default_factory=dict,
        description="Nested state entries. Keys are the names of the sub-states."
    )
    combine_values_from_sub_states: bool = Field(
        False,
        description="If True, implies sub-states' values contribute to this state_value based on combine_logic. "
                    "This does not strictly enforce sub-state types but their combinability."
    )
    sub_states_combine_logic: Optional[Literal["OR", "AND", "SUM", "AVERAGE"]] = Field(
        None,
        description="Logic to combine sub_states' values into state_value. "
                    "Requires combine_values_from_sub_states to be True."
    )

    _actual_state_value_type: Optional[Type] = PrivateAttr(None)

    @model_validator(mode='after')
    def _validate_and_initialize_entry(self) -> 'UserStateEntry':
        """
        Validates state_value against state_value_type_name and sets internal type.
        Also recursively computes value from substates if applicable upon initialization.
        """
        # Validate and set the actual type
        type_name = self.state_value_type_name
        if type_name not in TYPE_MAP:
            raise ValueError(f"Unsupported state_value_type_name: {type_name}. Supported types are: {list(TYPE_MAP.keys())}")
        self._actual_state_value_type = TYPE_MAP[type_name]

        # Validate the current state_value
        if self._actual_state_value_type and not isinstance(self.state_value, self._actual_state_value_type):
            try:
                # Attempt type coercion for basic types if validation fails initially
                # This is a simple coercion, more complex cases might need custom logic
                if self._actual_state_value_type in [int, float, str, bool]:
                    self.state_value = self._actual_state_value_type(self.state_value)
                else:
                    raise TypeError() # Fallback to raise error for list/dict or uncoercible types
            except (TypeError, ValueError) as e:
                raise ValueError(
                    f"state_value '{self.state_value}' (type: {type(self.state_value).__name__}) "
                    f"does not match state_value_type_name '{type_name}' "
                    f"(expected type: {self._actual_state_value_type.__name__}). Coercion failed: {e}"
                ) from e
        
        # Initial computation if logic is defined
        # Note: This means initial state_value might be overwritten if combine logic is present
        # and sub-states are provided. If state_value should be preserved as initial,
        # then this computation should be triggered explicitly after initialization.
        if self.combine_values_from_sub_states and self.sub_states_combine_logic and self.sub_states:
            self.compute_value_from_substates(is_initialization=True)
            # Re-validate after computation
            if self._actual_state_value_type and not isinstance(self.state_value, self._actual_state_value_type):
                 raise ValueError(
                    f"Computed state_value '{self.state_value}' (type: {type(self.state_value).__name__}) "
                    f"does not match state_value_type_name '{type_name}' "
                    f"(expected type: {self._actual_state_value_type.__name__}) after sub_state computation."
                )

        return self

    def _get_sub_value_for_computation(self, sub_entry: 'UserStateEntry') -> Any:
        """Helper to get a sub-entry's value, converting bool to int (0/1) if needed by logic."""
        if self.sub_states_combine_logic in ["SUM", "AVERAGE"] and isinstance(sub_entry.state_value, bool):
            return int(sub_entry.state_value)
        return sub_entry.state_value

    def compute_value_from_substates(self, is_initialization: bool = False) -> bool:
        """
        Computes the state_value from sub_states based on sub_states_combine_logic.
        Updates self.state_value.

        Args:
            is_initialization: If True, this is part of the model init.

        Returns:
            bool: True if self.state_value was changed, False otherwise.
                  If is_initialization is True, this return value might not be directly useful
                  as it's part of setting the initial state.
        """
        if not self.sub_states or not self.combine_values_from_sub_states or not self.sub_states_combine_logic:
            return False

        original_value = self.state_value
        new_value = original_value # Default to original if computation fails or not applicable

        sub_values = [self._get_sub_value_for_computation(sub) for sub in self.sub_states.values() if sub.state_value is not None]

        if not sub_values: # No sub-state values to compute from
            return False

        try:
            current_type = TYPE_MAP.get(self.state_value_type_name)
            if not current_type: # Should not happen due to validator
                app_state_logger.error(f"Cannot compute substate: unknown state_value_type_name {self.state_value_type_name}")
                return False

            if self.sub_states_combine_logic == "OR":
                if current_type is not bool:
                    raise ValueError("OR logic can only be applied to a boolean state_value_type.")
                new_value = any(bool(v) for v in sub_values)
            elif self.sub_states_combine_logic == "AND":
                if current_type is not bool:
                    raise ValueError("AND logic can only be applied to a boolean state_value_type.")
                new_value = all(bool(v) for v in sub_values)
            elif self.sub_states_combine_logic == "SUM":
                if current_type not in [int, float]:
                    raise ValueError("SUM logic can only be applied to int or float state_value_type.")
                # Ensure all sub_values are numbers (int, float, or bools converted to int)
                numeric_sub_values = []
                for v in sub_values:
                    if not isinstance(v, (int, float)):
                         raise ValueError(f"Cannot SUM non-numeric sub-state value: {v} (type: {type(v)})")
                    numeric_sub_values.append(v)
                new_value = sum(numeric_sub_values)
                if current_type is int:
                    new_value = int(new_value)
            elif self.sub_states_combine_logic == "AVERAGE":
                if current_type not in [int, float]:
                    raise ValueError("AVERAGE logic can only be applied to int or float state_value_type.")
                numeric_sub_values = []
                for v in sub_values:
                    if not isinstance(v, (int, float)):
                         raise ValueError(f"Cannot AVERAGE non-numeric sub-state value: {v} (type: {type(v)})")
                    numeric_sub_values.append(v)
                
                if numeric_sub_values:
                    new_value = sum(numeric_sub_values) / len(numeric_sub_values)
                    if current_type is int: # Typically average results in float, but if parent is int, truncate.
                        new_value = int(new_value) 
                # else: new_value remains original_value (or could be 0, NaN, or raise error)
            
            # Only update if different or during initialization (where original_value might be a placeholder)
            if new_value != original_value or is_initialization:
                self.state_value = new_value
                # Re-validate type after computation
                if not isinstance(self.state_value, current_type):
                    app_state_logger.warning(f"Computed value {self.state_value} type mismatch with {current_type}. Attempting to cast.")
                    try:
                        self.state_value = current_type(self.state_value)
                    except Exception:
                        # If cast fails, revert or raise error. For now, log and keep computed.
                        app_state_logger.error(f"Failed to cast computed value {self.state_value} to {current_type}. Original value was {original_value}")
                        # self.state_value = original_value # Option to revert
                        # raise # Option to make it a hard error
                return True
            return False

        except (ValueError, TypeError) as e:
            app_state_logger.error(f"Error computing value from sub-states: {e}")
            # Optionally, re-raise or handle gracefully by not changing the value
            # For now, we don't change self.state_value if computation errors out
            return False

    def get_actual_type(self) -> Optional[Type]:
        """Returns the actual Python type for state_value, if resolved."""
        return self._actual_state_value_type


class StateUpdate(BaseModel):
    """
    Represents an update operation to be applied to the UserState.
    """
    keys: List[str] = Field(
        ...,
        description="Path to the state entry to update. E.g., ['settings', 'notifications', 'email_enabled']"
    )
    update_value: Any = Field(
        ...,
        description="The new value to set for the state entry."
    )
    set_parents: bool = Field(
        True,
        description="If True, after updating the target state, attempt to recompute parent states "
                    "based on their sub_states_combine_logic."
    )


class UserState(BaseModel):
    """
    Root model for user's application state. Contains a dictionary of UserStateEntry.
    """
    states: Dict[str, UserStateEntry] = Field(
        default_factory=dict,
        description="A dictionary of top-level state entries. Keys are the names of the states."
    )

    @classmethod
    def initialize(cls, json_dict: Dict[str, Any]) -> 'UserState':
        """
        Initializes the entire user state from a JSON-like dictionary.
        This is a convenience method for `model_validate`.

        Args:
            json_dict: A dictionary representing the entire UserState structure.

        Returns:
            UserState: An instance of UserState.
        """
        app_state_logger.debug(f"Initializing UserState from dict: {json_dict}")
        return cls.model_validate(json_dict)

    def _get_entry_at_path(self, path: List[str]) -> Optional[UserStateEntry]:
        """Helper to retrieve a UserStateEntry at a given path."""
        current_level_states = self.states
        entry: Optional[UserStateEntry] = None
        for i, key in enumerate(path):
            entry = current_level_states.get(key)
            if entry is None:
                return None
            if i < len(path) - 1: # If not the last key, move to sub_states
                current_level_states = entry.sub_states
            # If it's the last key, 'entry' is our target
        return entry

    def _recompute_parents(self, path: List[str]):
        """Recursively recomputes parent states up the given path."""
        for i in range(len(path) - 1, 0, -1): # Iterate from parent of target up to root's child
            parent_path = path[:i]
            parent_entry = self._get_entry_at_path(parent_path)
            if parent_entry:
                changed = parent_entry.compute_value_from_substates()
                if changed:
                    app_state_logger.debug(f"Parent state at path {parent_path} recomputed and changed.")
                # If a parent changes, its parents might also need recomputing,
                # but this loop structure handles it by iterating upwards.
            else:
                # This should ideally not happen if the path was valid.
                app_state_logger.warning(f"Could not find parent entry at path {parent_path} for recomputation.")


    def state_update(self, updates: List[StateUpdate]) -> bool:
        """
        Applies a list of updates to the user state.

        Args:
            updates: A list of StateUpdate objects.

        Returns:
            bool: True if any state was changed, False otherwise.
        
        Raises:
            ValueError: If a path is invalid or an update value type is incorrect.
        """
        app_state_logger.debug(f"Applying state updates: {updates}")
        overall_changed = False
        for update in updates:
            if not update.keys:
                raise ValueError("StateUpdate 'keys' path cannot be empty.")

            entry_to_update = self._get_entry_at_path(update.keys)

            if entry_to_update is None:
                raise ValueError(f"Invalid path: Could not find state entry at '{'/'.join(update.keys)}'.")

            target_type = entry_to_update.get_actual_type()
            if target_type is None: # Should be set during UserStateEntry init
                 target_type_name = entry_to_update.state_value_type_name
                 if target_type_name not in TYPE_MAP:
                     raise ValueError(f"Path '{'/'.join(update.keys)}' has an unknown state type '{target_type_name}'.")
                 target_type = TYPE_MAP[target_type_name]
                 entry_to_update._actual_state_value_type = target_type # Ensure it's set if somehow missed
            
            # Validate and set the new value
            new_value = update.update_value
            if not isinstance(new_value, target_type):
                try:
                    # Attempt coercion for basic types
                    if target_type in [int, float, str, bool]:
                        new_value = target_type(new_value)
                    else:
                        raise TypeError() # Fallback to raise error for list/dict
                except (TypeError, ValueError) as e:
                    raise ValueError(
                        f"Update value '{new_value}' (type: {type(new_value).__name__}) for path '{'/'.join(update.keys)}' "
                        f"does not match target type '{target_type.__name__}'. Coercion failed: {e}"
                    ) from e
            
            if entry_to_update.state_value != new_value:
                entry_to_update.state_value = new_value
                overall_changed = True
                app_state_logger.debug(f"State at path '{'/'.join(update.keys)}' updated to: {new_value}")

                # If this node itself has combine logic, recompute (e.g. its own sub-states changed its meaning)
                # This is more for consistency if its sub_states are not the primary driver for this update
                entry_to_update.compute_value_from_substates()


                if update.set_parents:
                    self._recompute_parents(update.keys)
            else:
                app_state_logger.debug(f"State at path '{'/'.join(update.keys)}' no change needed for value: {new_value}")
        
        return overall_changed

    def get_state(self, paths: List[List[str]]) -> Dict[str, Any]:
        """
        Retrieves specific state values from the user state.

        Args:
            paths: A list of paths (each path being a list of keys) to retrieve.
                   If empty, retrieves all top-level states.

        Returns:
            Dict[str, Any]: A dictionary where keys are stringified paths 
                            (e.g., "settings/notifications/email_enabled") and values are the
                            corresponding state values. Returns the UserStateEntry model if path is to an entry.
        """
        app_state_logger.debug(f"Getting state for paths: {paths}")
        result: Dict[str, Any] = {}

        if not paths: # Get all top-level states if no specific paths
            # Retrieve the full UserStateEntry model for each top-level state
            for key, entry in self.states.items():
                result[key] = entry.state_value # Return only the value
            return result

        for path in paths:
            if not path:
                continue 
            
            str_path = "/".join(path)
            entry = self._get_entry_at_path(path)
            if entry is not None:
                result[str_path] = entry.state_value # Return only the value
            else:
                result[str_path] = None # Or raise error, or omit from results
        
        return result

# To make UserStateEntry's forward reference to itself work:
UserStateEntry.model_rebuild()

# --- API Request/Response Models ---

class InitializeUserStateRequest(BaseModel):
    """
    Request model for initializing user state from a LinkedIn URL.
    The actual state structure will be generated based on this URL.
    """
    linkedin_profile_url: HttpUrl = Field(
        ...,
        description="The LinkedIn profile URL to initialize the state from."
    )
    # initial_state_dict: Dict[str, Any] = Field(  # This field is no longer used for this init flow
    #     ...,
    #     description="A dictionary representing the entire UserState structure. "
    #                 "See UserState model for schema."
    # )
    # is_shared: bool = Field(False, description="True if this is an organization-shared state, False for user-specific.") # Hardcoded to False
    on_behalf_of_user_id: Optional[uuid.UUID] = Field(None, description="User ID to act on behalf of (superusers only).")
    # is_system_entity: bool = Field(False, description="Whether this is a system entity (superusers only).") # Hardcoded to False


class UpdateUserStateRequest(BaseModel):
    """Request model for updating user state."""
    updates: List[StateUpdate]
    # is_shared: bool = Field(False, description="True if this is an organization-shared state, False for user-specific.")
    on_behalf_of_user_id: Optional[uuid.UUID] = Field(None, description="User ID to act on behalf of (superusers only).")
    # is_system_entity: bool = Field(False, description="Whether this is a system entity (superusers only).")


class GetUserStateResponse(BaseModel):
    """Response model for getting user state."""
    retrieved_states: Dict[str, Any]


class ListUserStateDocumentsResponse(BaseModel):
    """Response model for listing user state document names."""
    docnames: List[str]


class ActiveUserStateDocnamesResponse(BaseModel):
    """
    Response model for listing active user state document names.
    An active document is one where the 'is_active' state entry is true.
    """
    active_docnames: List[str]


class DeleteUserStateDocumentResponse(BaseModel):
    """Response model for deleting a user state document."""
    message: str
    docname: str

# --- FastAPI Router ---

app_state_router = APIRouter(prefix="/app-state", tags=["User Application State"])

class UserStateInitResponse(BaseModel):
    """Response model for initializing user state."""
    user_state: UserState
    docname: str


@app_state_router.post(
    "",
    response_model=UserStateInitResponse, # Return the full state after initialization with the state docname
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Initialize User Application State from LinkedIn URL",
    description=(
        "Initializes a new user application state document based on a LinkedIn profile URL. "
    )
)
async def initialize_user_state(
    request_data: InitializeUserStateRequest,
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    db: AsyncSession = Depends(get_async_db_dependency),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """
    Initializes or completely overwrites the user application state for the given
    namespace and document name, based on a LinkedIn URL.
    """

    namespace = settings.USER_STATE_NAMESPACE

    # Parse LinkedIn URL to get username
    try:
        # parse_linkedin_url expects a dict with a 'url' key
        parsed_url_data_dict = {'url': str(request_data.linkedin_profile_url)}
        # The function modifies the dict in place if set_in_data is True, and also returns username, type
        entity_username, _ = parse_linkedin_url(parsed_url_data_dict, set_in_data=False) # set_in_data False as we only need return

        docname = settings.USER_STATE_DOCNAME.format(entity_username=entity_username)
        app_state_logger.info(
            f"Attempting to initialize app state for org {active_org_id}, user {current_user.id} "
            f"at path {namespace}/{docname} using LinkedIn URL: {request_data.linkedin_profile_url}"
        )
        
        if not entity_username:
            raise ValueError("Could not extract username from LinkedIn URL.")
            
    except ValueError as e:
        app_state_logger.warning(f"Invalid LinkedIn URL provided '{request_data.linkedin_profile_url}': {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid LinkedIn URL: {e}")
    except Exception as e:
        app_state_logger.error(f"Error parsing LinkedIn URL '{request_data.linkedin_profile_url}': {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing LinkedIn URL.")

    # --- Construct the default initial state dictionary ---
    initial_state_dict_payload = {
        "states": {
            "is_active": {
                "state_value_type_name": "bool",
                "description": "Whether this user application state is active.",
                "state_value": True
            },
            "linkedin_profile_url": {
                "state_value_type_name": "str",
                "description": "The user's full LinkedIn profile URL.",
                "state_value": str(request_data.linkedin_profile_url)
            },
            "entity_username": {
                "state_value_type_name": "str",
                "description": "The username extracted from the LinkedIn profile URL.",
                "state_value": entity_username
            },
            "is_completed": {
                "state_value_type_name": "bool",
                "description": "Overall status tracking completion of various document generation stages.",
                "state_value": False, # Computed by UserStateEntry
                "combine_values_from_sub_states": True,
                "sub_states_combine_logic": "AND",
                "sub_states": {
                    "linkedin_scraped_profile_doc": {"state_value_type_name": "bool", "description": "Profile scraping document creation status.", "state_value": False},
                    "linkedin_scraped_posts_doc": {"state_value_type_name": "bool", "description": "Posts scraping document creation status.", "state_value": False},
                    "content_analysis_doc": {"state_value_type_name": "bool", "description": "Content analysis document creation status.", "state_value": False},
                    "user_source_analysis": {"state_value_type_name": "bool", "description": "User source analysis document creation status.", "state_value": False},
                    "user_preferences_doc": {"state_value_type_name": "bool", "description": "User preferences document creation status.", "state_value": False},
                    "core_beliefs_perspectives_doc": {"state_value_type_name": "bool", "description": "Core beliefs and perspectives document creation status.", "state_value": False},
                    "content_pillars_doc": {"state_value_type_name": "bool", "description": "Content pillars document creation status.", "state_value": False},
                    "content_strategy_doc": {"state_value_type_name": "bool", "description": "Content strategy document creation status.", "state_value": False},
                    "user_dna_doc": {"state_value_type_name": "bool", "description": "User DNA document creation status.", "state_value": False},
                }
            },
            "onboarded": {
                "state_value_type_name": "bool",
                "description": "Overall onboarding completion status, true if all onboarding pages are completed.",
                "state_value": False, # This will be computed based on sub_states
                "combine_values_from_sub_states": True,
                "sub_states_combine_logic": "AND",
                "sub_states": {
                    "page_1_linkedin": {
                        "state_value_type_name": "bool",
                        "description": "LinkedIn URL input and validation.",
                        "state_value": False
                    },
                    "page_2_sources": {
                        "state_value_type_name": "bool",
                        "description": "Upload source docs or input manually.",
                        "state_value": False
                    },
                    "page_3_goals": {
                        "state_value_type_name": "bool",
                        "description": "Select content goals.",
                        "state_value": False
                    },
                    "page_4_audience": {
                        "state_value_type_name": "bool",
                        "description": "Select target audiences.",
                        "state_value": False
                    },
                    "page_5_time": {
                        "state_value_type_name": "bool",
                        "description": "Choose posting time and automation level.",
                        "state_value": False
                    },
                    "page_6_content_perspectives": {
                        "state_value_type_name": "bool",
                        "description": "Add answers to perspective questions.",
                        "state_value": False
                    },
                    "page_7_content_beliefs": {
                        "state_value_type_name": "bool",
                        "description": "Add answers to belief questions.",
                        "state_value": False
                    },
                    "page_8_content_pillars": {
                        "state_value_type_name": "bool",
                        "description": "Review and update content pillars.",
                        "state_value": False
                    },
                    "page_9_strategy": {
                        "state_value_type_name": "bool",
                        "description": "Generate and edit content strategy document.",
                        "state_value": False
                    },
                    "page_10_dna_summary": {
                        "state_value_type_name": "bool",
                        "description": "Review user DNA and complete onboarding.",
                        "state_value": False
                    }
                }
            }
        }
    }

    try:
        user_state = UserState.initialize(initial_state_dict_payload)
    except Exception as e:
        app_state_logger.error(f"Error initializing UserState from generated dict: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid initial state structure generated: {e}")

    try:
        _, _ = await service.create_or_update_unversioned_document(
            db=db,
            org_id=active_org_id,
            namespace=namespace, # "user_state"
            docname=docname,     # entity_username
            is_shared=False,     # Hardcoded
            user=current_user,
            data=user_state.model_dump(exclude_none=True), # Store the validated and initialized state
            on_behalf_of_user_id=request_data.on_behalf_of_user_id,
            is_system_entity=False, # Hardcoded
        )
        app_state_logger.info(f"App state for {namespace}/{docname} initialized/overwritten successfully via LinkedIn URL.")
        # Return the full state after initialization with the state docname
        return UserStateInitResponse(user_state=user_state, docname=docname)
    except HTTPException as e:
        # Re-raise known HTTP exceptions from the service
        raise e
    except Exception as e:
        app_state_logger.error(f"Failed to save app state for {namespace}/{docname}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save application state.")


@app_state_router.get(
    "/list",
    response_model=ListUserStateDocumentsResponse,
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="List User Application State Documents",
    description="Lists all user app state document names for the current user in the current active organization."
)
async def list_user_state_documents(
    on_behalf_of_user_id: Optional[uuid.UUID] = Query(None, description="User ID to act on behalf of (superusers only)."),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """
    Retrieves a list of all document names stored in the user state namespace
    for the currently active organization and user.
    """
    namespace = settings.USER_STATE_NAMESPACE
    app_state_logger.info(
        f"Listing app state documents for org {active_org_id}, user {current_user.id} in namespace '{namespace}'."
    )
    try:
        # Assuming is_shared=False for user-specific states and is_system_entity=False
        doc_metadata_list = await service.list_documents(
            org_id=active_org_id,
            namespace_filter=namespace,
            include_user_specific=True,
            include_shared=False, # User states are not shared
            include_system_entities=False, # User states are not system entities
            limit=100, # Consider if this limit is appropriate for all use cases
            user=current_user,
            on_behalf_of_user_id=on_behalf_of_user_id,
        )
        return ListUserStateDocumentsResponse(docnames=[doc_metadata.docname for doc_metadata in doc_metadata_list])
    except HTTPException as e:
        # Re-raise HTTP exceptions from the service directly
        app_state_logger.warning(
            f"HTTPException while listing documents for org {active_org_id}, user {current_user.id} in namespace '{namespace}': {e.detail}"
        )
        raise e
    except Exception as e:
        app_state_logger.error(
            f"Unexpected error listing documents for org {active_org_id}, user {current_user.id} in namespace '{namespace}': {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list application state documents."
        )


@app_state_router.get(
    "/active-docnames",
    response_model=ActiveUserStateDocnamesResponse,
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="List Active User Application State Document Names",
    description=(
        "Retrieves a list of document names from the user application state "
        "that are marked as 'active'. This involves fetching each document "
        "and checking its 'is_active' state. Documents that cannot be processed "
        "or are not active will be skipped."
    )
)
async def list_active_user_state_docnames(
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
    on_behalf_of_user_id: Optional[uuid.UUID] = Query(None, description="User ID to act on behalf of (superusers only)."),
) -> ActiveUserStateDocnamesResponse:
    """
    Lists all user application state document names that are currently active.

    This function performs the following steps:
    1. Retrieves all document metadata for the user in the user state namespace.
    2. For each document:
        a. Fetches the full document content.
        b. Parses the content into a `UserState` object.
        c. Checks if the `is_active` state entry exists and its `state_value` is `True`.
    3. Collects the names of all documents that are confirmed to be active.
    4. Returns the list of active document names.

    Errors during fetching or processing individual documents are logged, and
    such documents are skipped, rather than failing the entire operation.
    """
    namespace = settings.USER_STATE_NAMESPACE
    app_state_logger.info(
        f"Attempting to list active app state documents for org {active_org_id}, user {current_user.id} in namespace '{namespace}'."
    )

    active_docnames_list: List[str] = []

    try:
        # Step 1: Retrieve all document metadata
        # Using a potentially higher limit to ensure all documents are considered for active check.
        # Adjust limit as necessary based on expected number of documents.
        doc_metadata_list = await service.list_documents(
            org_id=active_org_id,
            namespace_filter=namespace,
            include_user_specific=True,
            include_shared=False,
            include_system_entities=False,
            limit=1000, # Increased limit for fetching all docs to check activity
            user=current_user,
            on_behalf_of_user_id=on_behalf_of_user_id,
        )
    except HTTPException as e:
        app_state_logger.error(
            f"HTTPException while listing all documents for active check for org {active_org_id}, user {current_user.id}: {e.detail}",
            exc_info=True
        )
        # If listing documents fails, we cannot proceed.
        raise HTTPException(
            status_code=e.status_code, # Propagate service error status
            detail=f"Failed to list documents for active check: {e.detail}"
        )
    except Exception as e:
        app_state_logger.error(
            f"Unexpected error listing all documents for active check for org {active_org_id}, user {current_user.id}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while trying to list documents for active check."
        )

    # Step 2 & 3: Fetch each document, parse, check 'is_active' state
    for doc_meta in doc_metadata_list:
        docname = doc_meta.docname
        try:
            # Step 2a: Fetch the full document content
            raw_state_data = await service.get_unversioned_document(
                org_id=active_org_id,
                namespace=namespace,
                docname=docname,
                is_shared=False, # User states are not shared
                user=current_user,
                on_behalf_of_user_id=on_behalf_of_user_id,
                is_system_entity=False, # User states are not system entities
            )

            if not raw_state_data:
                app_state_logger.warning(
                    f"Document '{docname}' in namespace '{namespace}' for org {active_org_id} is empty. Skipping active check."
                )
                continue

            # Step 2b: Parse the content into a UserState object
            user_state = UserState.model_validate(raw_state_data)

            # Step 2c: Check if the 'is_active' state entry exists and its state_value is True
            is_active_entry = user_state.get_state([["is_active"]])["is_active"]
            if is_active_entry:
                active_docnames_list.append(docname)
            else:
                app_state_logger.debug(
                    f"Document '{docname}' is not active or 'is_active' state is missing/invalid. Skipping."
                )

        except HTTPException as e:
            if e.status_code == status.HTTP_404_NOT_FOUND:
                app_state_logger.warning(
                    f"Document '{docname}' not found while checking active status for org {active_org_id}. Skipping."
                )
            else:
                app_state_logger.error(
                    f"HTTPException while fetching/processing document '{docname}' for active check (org {active_org_id}): {e.detail}. Skipping."
                )
            continue # Skip this document
        except Exception as e: # Includes Pydantic validation errors, etc.
            app_state_logger.error(
                f"Unexpected error processing document '{docname}' for active check (org {active_org_id}): {e}. Skipping.",
                exc_info=True
            )
            continue # Skip this document

    app_state_logger.info(
        f"Found {len(active_docnames_list)} active documents for org {active_org_id}, user {current_user.id}."
    )
    return ActiveUserStateDocnamesResponse(active_docnames=active_docnames_list)


@app_state_router.delete(
    "/{docname}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Delete User Application State Document",
    description="Deletes a specific document from the user application state namespace."
)
async def delete_user_state_document(
    docname: str = Path(..., description="The name of the document to delete."),
    on_behalf_of_user_id: Optional[uuid.UUID] = Body(None, embed=True, description="User ID to act on behalf of (superusers only)."), 
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
    # on_behalf_of_user_id: Optional[uuid.UUID] = Query(None, description="User ID to act on behalf of (superusers only).") # If needed for superuser actions
):
    """
    Deletes a specific user application state document identified by `docname`.
    """
    namespace = settings.USER_STATE_NAMESPACE
    app_state_logger.info(
        f"Attempting to delete app state document '{docname}' in namespace '{namespace}' for org {active_org_id}, user {current_user.id}."
    )

    try:
        deleted = await service.delete_unversioned_document(
            org_id=active_org_id,
            namespace=namespace,
            docname=docname,
            is_shared=False, # User state is not shared
            user=current_user,
            on_behalf_of_user_id=on_behalf_of_user_id, # If superuser capability is needed
            # is_system_entity=False # User state is not a system entity
        )
        if not deleted:
            # This case might occur if the document didn't exist but delete_unversioned_document
            # doesn't raise an error for it (e.g., returns False).
            # The service method is expected to raise HTTPException for 404.
            app_state_logger.warning(
                f"Document '{docname}' in namespace '{namespace}' not found for deletion or already deleted for org {active_org_id}, user {current_user.id}."
            )
            # Ensure a 404 if the service method doesn't already do it.
            # However, CustomerDataService.delete_unversioned_document currently raises 404 if not found.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Application state document '{docname}' not found.")
        
        app_state_logger.info(
            f"Successfully deleted app state document '{docname}' in namespace '{namespace}' for org {active_org_id}, user {current_user.id}."
        )
        # For HTTP 204, no response body is sent.
        # If a response body is desired (e.g. for HTTP 200), you can return a model.
        # return DeleteUserStateDocumentResponse(message="Document deleted successfully", docname=docname)
        return # Implicitly returns 204 No Content due to status_code in decorator

    except HTTPException as e:
        # Log and re-raise known HTTP exceptions (like 404 from the service)
        app_state_logger.warning(
            f"HTTPException while deleting document '{docname}' for org {active_org_id}, user {current_user.id}: {e.detail}"
        )
        raise e
    except Exception as e:
        app_state_logger.error(
            f"Unexpected error deleting document '{docname}' for org {active_org_id}, user {current_user.id}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete application state document '{docname}'."
        )


@app_state_router.get(
    "/{docname}",
    response_model=GetUserStateResponse, # Or UserState if returning the whole object
    dependencies=[Depends(RequireOrgDataReadActiveOrg)],
    summary="Get User Application State",
    description="Retrieves the user application state or specific parts of it."
)
async def get_user_state_route(
    docname: str = Path(..., description="Name for the app state document."),
    paths_to_get_str: Optional[str] = Query(None, description="Comma-separated list of paths to retrieve (dot-separated keys, e.g., 'is_completed.linkedin_scraped_profile_doc,onboarding_steps.page_1_linkedin.completed'). If empty, retrieves all top-level states as UserStateEntry models."),
    # is_shared: bool = Query(False, description="True if this is an organization-shared state, False for user-specific."),
    on_behalf_of_user_id: Optional[uuid.UUID] = Query(None, description="User ID to act on behalf of (superusers only)."),
    # is_system_entity: bool = Query(False, description="Whether this is a system entity (superusers only)."),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """
    Retrieves the user application state.
    - `paths_to_get_str`: Provide comma-separated paths like "key1.subkeyA,key2".
                          If not provided, the values of top-level states are returned.
    """
    namespace = settings.USER_STATE_NAMESPACE
    app_state_logger.info(
        f"Getting app state for org {active_org_id}, user {current_user.id} "
        f"at {namespace}/{docname}."
    )
    try:
        raw_state_data = await service.get_unversioned_document(
            org_id=active_org_id,
            namespace=namespace,
            docname=docname,
            is_shared=False,
            user=current_user,
            on_behalf_of_user_id=on_behalf_of_user_id,
            is_system_entity=False,
        )
    except HTTPException as e:
        if e.status_code == status.HTTP_404_NOT_FOUND:
            app_state_logger.warning(f"App state not found for {namespace}/{docname}.")
            # Depending on desired behavior, could return empty state or 404
            # For now, let 404 propagate as the document doesn't exist.
        raise e
    except Exception as e:
        app_state_logger.error(f"Failed to fetch app state for {namespace}/{docname}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve application state.")

    if not raw_state_data: # Should be caught by 404 from service, but as a safeguard
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application state document is empty or not found.")

    try:
        user_state = UserState.model_validate(raw_state_data)
    except Exception as e:
        app_state_logger.error(f"Error validating stored app state for {namespace}/{docname}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid application state data encountered.")

    parsed_paths: List[List[str]] = []
    if paths_to_get_str:
        path_strings = [p.strip() for p in paths_to_get_str.split(',') if p.strip()]
        for ps in path_strings:
            parsed_paths.append([key.strip() for key in ps.split('.') if key.strip()])
    
    retrieved_data = user_state.get_state(parsed_paths)
    return GetUserStateResponse(retrieved_states=retrieved_data)


@app_state_router.put(
    "/{docname}",
    response_model=UserState, # Return the full state after update
    dependencies=[Depends(RequireOrgDataWriteActiveOrg)],
    summary="Update User Application State",
    description="Applies partial updates to the user application state document."
)
async def update_user_state_route(
    request_data: UpdateUserStateRequest,
    docname: str = Path(..., description="Name for the app state document."),
    active_org_id: uuid.UUID = Depends(get_active_org_id),
    current_user: User = Depends(get_current_active_verified_user),
    db: AsyncSession = Depends(get_async_db_dependency),
    service: CustomerDataService = Depends(get_customer_data_service_dependency),
):
    """
    Applies a list of updates to the user application state.
    If `set_parents` is true in an update, parent states will be recomputed.
    """
    namespace = settings.USER_STATE_NAMESPACE
    app_state_logger.info(
        f"Updating app state for org {active_org_id}, user {current_user.id} "
        f"at {namespace}/{docname}."
    )
    try:
        raw_state_data = await service.get_unversioned_document(
            org_id=active_org_id,
            namespace=namespace,
            docname=docname,
            is_shared=False,  # request_data.is_shared,
            user=current_user,
            on_behalf_of_user_id=request_data.on_behalf_of_user_id,
            is_system_entity=False,  # request_data.is_system_entity,
        )
    except HTTPException as e:
        if e.status_code == status.HTTP_404_NOT_FOUND:
            # If document doesn't exist, update is not possible.
            # Alternatively, one could choose to initialize it here if updates are on an empty state.
            # For now, require initialization first.
            app_state_logger.warning(f"Cannot update: App state not found for {namespace}/{docname}.")
        raise e # Re-raise 404 or other service errors
    except Exception as e:
        app_state_logger.error(f"Failed to fetch app state for update {namespace}/{docname}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve application state for update.")

    if not raw_state_data:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application state document is empty or not found, cannot update.")

    try:
        user_state = UserState.model_validate(raw_state_data)
        
        # The explicit management of 'onboarded' state is no longer needed here.
        # The UserState.state_update method, through _recompute_parents,
        # will trigger compute_value_from_substates on the 'onboarded' UserStateEntry
        # if any of its sub-states (page_1_linkedin, etc.) are updated.

        changed = user_state.state_update(request_data.updates)
        
    except ValueError as e: # Catch validation errors from state_update (e.g. bad path, type mismatch)
        app_state_logger.warning(f"Invalid state update for {namespace}/{docname}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e: # Catch other errors during model validation or update logic
        app_state_logger.error(f"Error processing state update for {namespace}/{docname}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error applying updates to application state.")

    if changed:
        app_state_logger.info(f"App state for {namespace}/{docname} updated. Saving changes.")
        try:
            await service.create_or_update_unversioned_document(
                db=db,
                org_id=active_org_id,
                namespace=namespace,
                docname=docname,
                is_shared=False,  # request_data.is_shared,
                user=current_user,
                data=user_state.model_dump(exclude_none=True),
                on_behalf_of_user_id=request_data.on_behalf_of_user_id,
                is_system_entity=False,  # request_data.is_system_entity,
            )
        except Exception as e:
            app_state_logger.error(f"Failed to save updated app state for {namespace}/{docname}: {e}", exc_info=True)
            # Potentially inconsistent state if DB save fails after in-memory update.
            # Consider rollback or more robust error handling if critical.
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save updated application state.")
    else:
        app_state_logger.info(f"App state for {namespace}/{docname} had no effective changes from the update request.")

    return user_state


