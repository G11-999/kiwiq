
"""
Manages user-specific application state, stored as unversioned documents
in CustomerDataService.
"""

import uuid
from typing import List, Dict, Any, Optional, Type, Literal, Union, cast
from enum import Enum

from pydantic import BaseModel, Field, model_validator, PrivateAttr, HttpUrl

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

# To make UserStateEntry's forward reference to itself work:
UserStateEntry.model_rebuild()


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


class UserStateInitResponse(BaseModel):
    """Response model for initializing user state."""
    user_state: UserState
    docname: str

