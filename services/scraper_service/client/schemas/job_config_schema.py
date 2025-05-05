import re
import logging
from enum import Enum
from typing import List, Optional, Dict, Any, Union, Tuple
from pydantic import BaseModel, model_validator, Field, HttpUrl
from datetime import datetime

from scraper_service.settings import rapid_api_settings

# Setup logger
logger = logging.getLogger(__name__)


class YesNoEnum(str, Enum):
    """Enum for simple yes/no choices."""
    YES = "yes"
    NO = "no"


class JobTypeEnum(str, Enum):
    """Enum defining the types of scraping jobs supported."""
    PROFILE_INFO = "profile_info"
    ENTITY_POSTS = "entity_posts"
    ACTIVITY_COMMENTS = "activity_comments"
    ACTIVITY_REACTIONS = "activity_reactions"
    SEARCH_POST_BY_KEYWORD = "search_post_by_keyword"
    SEARCH_POST_BY_HASHTAG = "search_post_by_hashtag"


class EntityTypeEnum(str, Enum):
    """Enum defining the type of LinkedIn entity (company or person)."""
    COMPANY = "company"
    PERSON = "person"


def parse_linkedin_url(data: Dict[str, Any], set_in_data: bool = True) -> Tuple[str, str]:
    """Parse a LinkedIn URL to extract the entity type and identifier."""
    if data.get('url'):
        url = HttpUrl(data['url'])
        if data.get("username") or data.get("type"):
            raise ValueError("'username' and 'type' cannot be provided if 'url' is provided.")
        # Parse LinkedIn URLs to extract username and entity type using regex
        if data.get('url'):
            url_str = str(url)
            logger.debug(f"Parsing LinkedIn URL: {url_str}")
            
            # Use regex to extract both entity type and username in a single pattern
            # Pattern matches:
            # - Group 1: Either "in" (person) or "company" (company)
            # - Group 2: The username/company name that follows
            linkedin_pattern = r"linkedin\.com/(?:(in|company))/([^/?#]+)"
            match = re.search(linkedin_pattern, url_str)
            
            if match:
                entity_prefix = match.group(1)
                identifier = match.group(2).strip('/')
                
                if entity_prefix == "in":
                    logger.info(f"Extracted person username '{identifier}' from URL")
                    username = identifier
                    _type = EntityTypeEnum.PERSON.value
                elif entity_prefix == "company":
                    logger.info(f"Extracted company name '{identifier}' from URL")
                    username = identifier
                    _type = EntityTypeEnum.COMPANY.value
                if set_in_data:
                    data['username'] = username
                    data['type'] = _type
            else:
                # URL doesn't match expected LinkedIn profile patterns
                logger.warning(f"URL {url_str} doesn't match expected LinkedIn profile patterns")
                raise ValueError(
                    "Invalid LinkedIn URL format. Expected patterns: "
                    "https://www.linkedin.com/in/username/ or "
                    "https://www.linkedin.com/company/company-name/"
                )
        return username, _type


class ScrapingRequest(BaseModel):
    """
    Configuration schema for a scraping job request. This schema defines the parameters
    needed to initiate various types of LinkedIn scraping tasks via an external API.
    It includes extensive validation to ensure that the request is well-formed and
    logically consistent before being processed or sent to the API.

    Attributes:
        job_type (JobTypeEnum): The primary type of job being requested. Must match exactly
                                one of the specific job flags set to 'yes'.
        type (Optional[EntityTypeEnum]): Specifies if the target entity is a 'company' or 'person'.
                                         Required for 'profile_info' and 'entity_posts' jobs.
        profile_info (YesNoEnum): Flag to indicate if profile information should be scraped.
                                  Defaults to 'no'. Only one job flag can be 'yes'.
        entity_posts (YesNoEnum): Flag to indicate if posts by the entity should be scraped.
                                  Defaults to 'no'. Only one job flag can be 'yes'.
                                  Must be 'yes' if 'post_comments' or 'post_reactions' is 'yes'.
        activity_comments (YesNoEnum): Flag to indicate if posts the user commented on should be scraped.
                                       Defaults to 'no'. Only one job flag can be 'yes'. Requires 'username'.
        activity_reactions (YesNoEnum): Flag to indicate if posts the user reacted to should be scraped.
                                        Defaults to 'no'. Only one job flag can be 'yes'. Requires 'username'.
        search_post_by_keyword (YesNoEnum): Flag to indicate if posts should be searched by keyword.
                                            Defaults to 'no'. Only one job flag can be 'yes'. Requires 'keyword'.
        search_post_by_hashtag (YesNoEnum): Flag to indicate if posts should be searched by hashtag.
                                            Defaults to 'no'. Only one job flag can be 'yes'. Requires 'hashtag'.
        username (Optional[str]): The LinkedIn username or profile URL identifier. Required for jobs involving
                                  a specific user or company profile ('profile_info', 'entity_posts',
                                  'activity_comments', 'activity_reactions').
        keyword (Optional[str]): The keyword to use for searching posts. Required for
                                 'search_post_by_keyword' job type.
        hashtag (Optional[str]): The hashtag to use for searching posts (without the '#'). Required for
                                 'search_post_by_hashtag' job type.
        post_limit (Optional[int]): The maximum number of posts to retrieve. Applicable when scraping
                                    entity posts or activity. Defaults to a configured value.
        post_comments (YesNoEnum): Flag to indicate if comments should be fetched for the scraped posts.
                                   Defaults to 'no'. Requires 'entity_posts' to be 'yes'.
        comment_limit (Optional[int]): The maximum number of comments to retrieve per post.
                                       Defaults to a configured value.
        post_reactions (YesNoEnum): Flag to indicate if reactions should be fetched for the scraped posts.
                                    Defaults to 'no'. Requires 'entity_posts' to be 'yes'.
        reaction_limit (Optional[int]): The maximum number of reactions to retrieve per post.
                                        Defaults to a configured value.
    """
    # Core job definition fields
    job_type: JobTypeEnum
    type: Optional[EntityTypeEnum] = None # Required for profile_info and entity_posts

    # Flags to indicate the specific job type - exactly one must be 'yes'
    profile_info: YesNoEnum = Field(default=YesNoEnum.NO, description="Scrape profile information?")
    entity_posts: YesNoEnum = Field(default=YesNoEnum.NO, description="Scrape posts by the entity?")
    activity_comments: YesNoEnum = Field(default=YesNoEnum.NO, description="Scrape posts the user commented on?")
    activity_reactions: YesNoEnum = Field(default=YesNoEnum.NO, description="Scrape posts the user reacted to?")
    search_post_by_keyword: YesNoEnum = Field(default=YesNoEnum.NO, description="Search posts by keyword?")
    search_post_by_hashtag: YesNoEnum = Field(default=YesNoEnum.NO, description="Search posts by hashtag?")

    # Input identifiers - required based on the job type
    url: Optional[HttpUrl] = Field(default=None, description="URL of the profile/entity to scrape.")
    username: Optional[str] = Field(default=None, description="Username/Profile URL for profile/entity specific jobs.")
    keyword: Optional[str] = Field(default=None, description="Keyword for post search.")
    hashtag: Optional[str] = Field(default=None, description="Hashtag for post search (without '#').")

    # Limits for data retrieval
    post_limit: Optional[int] = Field(default=None, description="Max posts to retrieve.")

    # Flags and limits for nested data within posts - require entity_posts='yes'
    post_comments: YesNoEnum = Field(default=YesNoEnum.NO, description="Fetch comments for scraped posts?")
    comment_limit: Optional[int] = Field(default=rapid_api_settings.DEFAULT_COMMENT_LIMIT, description="Max comments per post.")
    post_reactions: YesNoEnum = Field(default=YesNoEnum.NO, description="Fetch reactions for scraped posts?")
    reaction_limit: Optional[int] = Field(default=rapid_api_settings.DEFAULT_REACTION_LIMIT, description="Max reactions per post.")

    class Config:
        """Pydantic model configuration."""
        extra = 'forbid' # Forbid any extra fields not defined in the schema
        use_enum_values = True # Use enum values in the serialized output


    @model_validator(mode='before')
    @classmethod
    def validate_request_logic(cls, data: Any) -> Dict[str, Any]:
        """
        Performs comprehensive validation on the input data before creating the model instance.

        Ensures:
        1. Exactly one job type flag (e.g., 'profile_info', 'entity_posts') is set to 'yes'.
        2. The 'job_type' field is provided and correctly matches the single active job flag.
        3. Required identifiers ('username', 'keyword', 'hashtag', 'type') are present based on the job type.
        4. 'post_comments' or 'post_reactions' can only be 'yes' if 'entity_posts' is also 'yes'.

        Args:
            data (Any): The raw input data (expected to be a dictionary).

        Returns:
            Dict[str, Any]: The validated data dictionary.

        Raises:
            ValueError: If any validation rule is violated.
        """
        if not isinstance(data, dict):
            # Ensure data is a dictionary for further processing
            raise ValueError("Request data must be a dictionary.")

        parse_linkedin_url(data, set_in_data=True)

        # Define the flags that represent distinct job types
        job_flags = {
            JobTypeEnum.PROFILE_INFO: 'profile_info',
            JobTypeEnum.ENTITY_POSTS: 'entity_posts',
            JobTypeEnum.ACTIVITY_COMMENTS: 'activity_comments',
            JobTypeEnum.ACTIVITY_REACTIONS: 'activity_reactions',
            JobTypeEnum.SEARCH_POST_BY_KEYWORD: 'search_post_by_keyword',
            JobTypeEnum.SEARCH_POST_BY_HASHTAG: 'search_post_by_hashtag',
        }

        # --- Validation 1 & 3: Ensure exactly one job flag is 'yes' ---
        active_jobs = [flag for flag_name, flag in job_flags.items() if data.get(flag) == YesNoEnum.YES.value]

        if len(active_jobs) == 0:
            raise ValueError("No job type selected. At least one job flag ('profile_info', 'entity_posts', etc.) must be set to 'yes'.")
        if len(active_jobs) > 1:
            raise ValueError(f"Multiple job types selected ({', '.join(active_jobs)}). Only one job flag can be set to 'yes'.")

        # Identify the single active job flag name (e.g., 'profile_info')
        active_job_flag_name = active_jobs[0]

        # --- Validation 4: Assert 'job_type' field matches the active flag ---
        job_type_value = data.get('job_type')
        if not job_type_value:
            raise ValueError("'job_type' field is required.")

        # Convert the active flag name back to its corresponding JobTypeEnum value for comparison
        # This relies on the structure of the job_flags dictionary
        expected_job_type_enum = None
        for enum_member, flag_name_in_dict in job_flags.items():
            if flag_name_in_dict == active_job_flag_name:
                expected_job_type_enum = enum_member
                break

        # This should theoretically never happen if active_job_flag_name came from job_flags keys
        if not expected_job_type_enum:
             logger.error(f"Internal logic error: Could not map active flag '{active_job_flag_name}' back to JobTypeEnum.")
             raise ValueError("Internal configuration error during validation.")

        # Compare the provided job_type with the one derived from the active flag
        if job_type_value != expected_job_type_enum.value:
            raise ValueError(f"Mismatch between 'job_type' ('{job_type_value}') and the active job flag ('{active_job_flag_name}'). "
                             f"'job_type' must be '{expected_job_type_enum.value}'.")

        # --- Validation 4 (cont.): Assert required identifiers based on job_type ---
        active_job_type = expected_job_type_enum # Use the validated enum member

        if active_job_type in [JobTypeEnum.PROFILE_INFO, JobTypeEnum.ENTITY_POSTS]:
            if not data.get('username'):
                raise ValueError(f"'username' is required for job type '{active_job_type.value}'.")
            if not data.get('type'):
                 raise ValueError(f"'type' (company/person) is required for job type '{active_job_type.value}'.")
        elif active_job_type in [JobTypeEnum.ACTIVITY_COMMENTS, JobTypeEnum.ACTIVITY_REACTIONS]:
             if not data.get('username'):
                raise ValueError(f"'username' is required for job type '{active_job_type.value}'.")
        elif active_job_type == JobTypeEnum.SEARCH_POST_BY_KEYWORD:
            if not data.get('keyword'):
                raise ValueError(f"'keyword' is required for job type '{active_job_type.value}'.")
        elif active_job_type == JobTypeEnum.SEARCH_POST_BY_HASHTAG:
             if not data.get('hashtag'):
                raise ValueError(f"'hashtag' is required for job type '{active_job_type.value}'.")

        # --- Validation 2: Check conditional requirements for post_comments/post_reactions ---
        fetch_comments = data.get('post_comments') == YesNoEnum.YES.value
        fetch_reactions = data.get('post_reactions') == YesNoEnum.YES.value
        entity_posts_enabled = data.get('entity_posts') == YesNoEnum.YES.value

        # This validation is only relevant if the job involves fetching posts in the first place.
        # Currently, only 'entity_posts' allows fetching comments/reactions directly.
        # If other job types (like search) were extended to allow this, this logic might need adjustment.
        if fetch_comments or fetch_reactions:
            # Check if the primary job is entity_posts OR if entity_posts flag is explicitly yes
            # The second condition covers potential future scenarios or if entity_posts is set alongside another primary job (though disallowed by rule 1)
            if active_job_type not in [JobTypeEnum.ENTITY_POSTS, JobTypeEnum.ACTIVITY_COMMENTS, JobTypeEnum.ACTIVITY_REACTIONS] and not entity_posts_enabled:
                 raise ValueError("Cannot set 'post_comments' or 'post_reactions' to 'yes' unless the job type is 'entity_posts'.")
            # Defensive check: Ensure entity_posts flag is indeed yes if comments/reactions are requested.
            # This reinforces the logic, especially if the primary job *is* entity_posts.
            # if not entity_posts_enabled:
            #      raise ValueError("Cannot set 'post_comments' or 'post_reactions' to 'yes' if 'entity_posts' is not 'yes'.")


        # If all validations pass, return the original data dictionary
        # Pydantic will handle the rest of the type casting and model creation.
        return data


# if __name__ == "__main__":
#     import pprint
#     data = {
#         "job_type": "profile_info",
#         "url": "https://www.linkedin.com/in/username/",
#         "profile_info": "yes"
#     }
#     pprint.pprint(ScrapingRequest(**data).model_dump())

#     data = {
#         "job_type": "profile_info",
#         "url": "https://www.linkedin.com/company/company-name/",
#         "profile_info": "yes"
#     }
#     pprint.pprint(ScrapingRequest(**data).model_dump())

#     data = {
#         "job_type": "profile_info",
#         "url": "https://www.linkedin.com/in/user-name",
#         "profile_info": "yes"
#     }
#     pprint.pprint(ScrapingRequest(**data).model_dump())

#     data = {
#         "job_type": "profile_info",
#         "url": "https://www.linkedin.com/company/company-name",
#         "profile_info": "yes"
#     }
#     pprint.pprint(ScrapingRequest(**data).model_dump())
