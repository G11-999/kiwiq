from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import uuid


class UserDnaDocModel(BaseModel):
    schema_template_name: Optional[str] = None
    schema_template_version: Optional[str] = None
    is_system_entity: bool = Field(False, description="Indicates if it's a system-level document")
    on_behalf_of_user_id: Optional[str]
    data: Dict[str, Any]


class ContentStrategyDocModel(UserDnaDocModel):
    pass


class UserSourceAnalysisModel(UserDnaDocModel):
    pass


class UploadedFilesModel(UserDnaDocModel):
    pass


class CoreBeliefsPerspectivesDocModel(UserDnaDocModel):
    pass


class ContentPillarsDocModel(UserDnaDocModel):
    pass


class UserPreferencesDocModel(UserDnaDocModel):
    pass


class ContentAnalysisDocModel(UserDnaDocModel):
    pass


class LinkedInScrapedProfileDocModel(UserDnaDocModel):
    pass


class LinkedInScrapedPostsDocModel(UserDnaDocModel):
    pass


class MethodologyImplementationAICopilotModel(BaseModel):
    schema_template_name: Optional[str] = None
    schema_template_version: Optional[str] = None
    is_system_entity: bool = Field(False, description="Indicates if it's a system-level document")
    # on_behalf_of_user_id: str
    data: Dict[str, Any]
    is_system_entity: bool = Field(False, description="System-level document")
    is_complete : bool = Field(True, description="System-level document")

class BuildingBlocksContentMethodologyModel(MethodologyImplementationAICopilotModel):
    pass


class LinkedInPostEvaluationFrameworkModel(MethodologyImplementationAICopilotModel):
    pass


class LinkedInPostScoringFrameworkModel(MethodologyImplementationAICopilotModel):
    pass


class LinkedInContentOptimizationGuideModel(MethodologyImplementationAICopilotModel):
    pass