import json
from abc import ABC
from pydantic import BaseModel, HttpUrl, field_validator, Field
from pydantic.fields import FieldInfo
from pydantic.json_schema import SkipJsonSchema

from typing import Optional, Union, ClassVar, Literal, get_origin, get_args, Type
import re

# allow HttpUrl or domain.com or xyz.domain.com type of urls

def get_annotation_from_model_field(model_field: FieldInfo) -> Optional[Type[BaseModel]]:
    annotation = model_field.annotation
    if annotation is not None:
        if get_origin(annotation) in [Optional, Union]:
            annotation = [arg for arg in get_args(annotation) if arg is not None][0]
    return annotation

class BaseProviderInternalTool(BaseModel, ABC):
    """Base class for provider internal tools."""
    RESERVED_FIELD_NAMES: ClassVar[list[str]] = ["type", "name"]

    # provider_name: ClassVar[LLMModelProvider]
    type: ClassVar[str]
    name: ClassVar[str]

    user_config: Optional[BaseModel] = None

    @classmethod
    def __pydantic_init_subclass__(cls, *args, **kwargs):
        super().__pydantic_init_subclass__(*args, **kwargs)

        annotation = get_annotation_from_model_field(cls.model_fields["user_config"])
        if not issubclass(annotation, BaseModel):
            raise ValueError(f"user_config must be a subclass of BaseModel -- {annotation}")
        
        if annotation is not None:
            # import ipdb; ipdb.set_trace()
            user_config_fields = annotation.model_fields
            if any(user_config_field_name in cls.RESERVED_FIELD_NAMES for user_config_field_name in user_config_fields.keys()):
                raise ValueError(f"User config field name {user_config_fields.keys()} is reserved keys: {cls.RESERVED_FIELD_NAMES} for internal use.")
    
    def get_tool(self):
        raise NotImplementedError("Subclasses must implement this method.")

    @classmethod
    def get_tool_json_schema(cls):
        user_config_annotation = get_annotation_from_model_field(cls.model_fields["user_config"])
        return {
            "name": cls.name,
            # "type": cls.type,
            "user_config": user_config_annotation.model_json_schema()
        }


class UserLocation(BaseModel):
    """Schema for user location data used in search configuration."""
    type: Literal["approximate"] = "approximate"  # Default to approximate location
    city: Optional[str] = None
    region: Optional[str] = None 
    country: Optional[str] = None
    timezone: Optional[str] = None
