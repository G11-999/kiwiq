import asyncio
import json
import logging
from typing import Any, Dict

from scraper_service.client.core_api_client import RapidAPIClient
from scraper_service.client.post_manager import LinkedinPostFetcher
from scraper_service.client.search_posts import SearchPosts
from scraper_service.client.schemas.job_config_schema import ScrapingRequest, JobTypeEnum, EntityTypeEnum, YesNoEnum
from scraper_service.settings import rapid_api_settings
from pydantic import ValidationError, BaseModel

# Setup logger
from global_config.logger import get_prefect_or_regular_python_logger
# Basic configuration for logging during development/testing.
# In a production environment, use a more robust logging setup.
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Client Initialization ---
# Retrieve API key and base URL from settings.
# It's crucial that these settings are configured correctly in scraper_service.settings
# via environment variables or a .env file.
api_key = rapid_api_settings.RAPID_API_KEY
base_url = rapid_api_settings.RAPID_API_HOST




async def execute_scraper_job(job_config: ScrapingRequest) -> Any:
    """
    Executes the appropriate scraping job based on the validated job configuration.

    This function acts as a router, taking a validated ScrapingRequest object
    and dispatching the request to the correct client method based on the
    specified job_type and other parameters. The input `job_config` is expected
    to have already passed Pydantic validation, ensuring logical consistency
    and presence of required fields based on the `job_type`.

    Args:
        job_config (ScrapingRequest): A validated Pydantic model instance containing
                                      all necessary parameters for the scraping job.

    Returns:
        Any: The result returned by the underlying scraping API client method.
             The structure of the result depends heavily on the specific job type executed
             and the response structure of the external API. It could be a list of
             Pydantic models, a single Pydantic model, or potentially a dictionary
             containing an 'error' key if the API call itself fails.

    Raises:
        ValueError: Although Pydantic validation handles most cases, this function
                    includes defensive checks. A ValueError might be raised if an
                    unexpected state occurs (e.g., an unhandled enum value).
        Exception: Propagates exceptions raised by the API client methods during execution,
                   such as network errors, timeouts, or errors returned by the external API.
    """
    logger = get_prefect_or_regular_python_logger(__name__)
    logger.info(f"Executing scraper job for type: {job_config.job_type} with config: {job_config.model_dump(exclude_none=True)}")

    # Instantiate the necessary API client classes.
    # These clients encapsulate the logic for interacting with the external scraping API.
    try:
        # Check if API key is present, as it's critical for function.
        if not api_key:
            raise ValueError("RAPID_API_KEY is not set in the environment or settings.")
        rapid_api_client = RapidAPIClient(api_key=api_key, base_url=base_url)
        linkedin_post_fetcher = LinkedinPostFetcher(api_key=api_key, base_url=base_url)
        search_post_client = SearchPosts(api_key=api_key, base_url=base_url)
        logger.info("API clients initialized successfully.")
    except ValueError as ve:
        logger.error(f"Configuration error during client initialization: {ve}")
        # Raise RuntimeError to indicate a fatal configuration issue preventing startup.
        raise RuntimeError("API Client initialization failed due to missing configuration.") from ve
    except Exception as e:
        # Log and raise an error if client initialization fails for other reasons.
        logger.exception("Failed to initialize API clients. Check API key and base URL settings.")
        raise RuntimeError("API Client initialization failed.") from e

    # Convert the validated Pydantic model to a dictionary.
    # Most underlying client methods currently expect a dictionary as input.
    # This provides flexibility if client methods are updated later.
    # Exclude None values for cleaner logs and potentially cleaner API calls.
    data_dict = job_config.model_dump(exclude_none=True)

    # --- Job Routing Logic ---
    # The ScrapingRequest's validator ensures exactly one job type flag is active
    # and that required fields (like username, keyword, hashtag, type) are present
    # based on the job_type. This logic routes the call to the appropriate client method.

    job_type = job_config.job_type
    entity_type = job_config.type # Will be None for jobs not specific to Person/Company profiles.

    try:
        # Route based on the primary job type defined in the config.
        if job_type == JobTypeEnum.PROFILE_INFO:
            # The validator ensures 'type' is set for this job_type.
            if entity_type == EntityTypeEnum.PERSON:
                logger.debug(f"Routing to get_profile_data for user: {job_config.username}")
                # Pass the full data dictionary to the client method.
                return await rapid_api_client.get_profile_data(data_dict)
            elif entity_type == EntityTypeEnum.COMPANY:
                logger.debug(f"Routing to get_company_data for company: {job_config.username}")
                # Pass the full data dictionary to the client method.
                return await rapid_api_client.get_company_data(data_dict)
            else:
                # This case should not be reachable due to Enum and validation,
                # but included for robustness.
                logger.error(f"Unsupported entity type '{entity_type}' encountered for PROFILE_INFO job.")
                raise ValueError(f"Unsupported entity type '{entity_type}' for PROFILE_INFO.")

        elif job_type == JobTypeEnum.ENTITY_POSTS:
            # The validator ensures 'type' is set for this job_type.
            if entity_type == EntityTypeEnum.PERSON:
                logger.debug(f"Routing to get_profile_posts for user: {job_config.username}")
                # Call the method for fetching posts associated with a person's profile.
                # Pass the full data dictionary.
                # Note: This was updated from a non-existent `get_entity_posts` method.
                return await linkedin_post_fetcher.get_profile_posts(data_dict)
            elif entity_type == EntityTypeEnum.COMPANY:
                logger.debug(f"Routing to get_company_posts for company: {job_config.username}")
                # Call the method for fetching posts associated with a company page.
                # Pass the full data dictionary.
                return await linkedin_post_fetcher.get_company_posts(data_dict)
            else:
                # Should not be reachable.
                logger.error(f"Unsupported entity type '{entity_type}' encountered for ENTITY_POSTS job.")
                raise ValueError(f"Unsupported entity type '{entity_type}' for ENTITY_POSTS.")

        elif job_type == JobTypeEnum.ACTIVITY_COMMENTS:
            # These jobs currently apply implicitly to 'person' based on API endpoint design.
            # The validator ensures 'username' is present.
            logger.debug(f"Routing to get_user_comments_with_details for user: {job_config.username}")
            # Pass the full data dictionary.
            return await linkedin_post_fetcher.get_user_comments_with_details(data_dict)

        elif job_type == JobTypeEnum.ACTIVITY_REACTIONS:
            # These jobs currently apply implicitly to 'person'.
            # The validator ensures 'username' is present.
            logger.debug(f"Routing to get_user_likes_with_details for user: {job_config.username}")
            # Pass the full data dictionary.
            return await linkedin_post_fetcher.get_user_likes_with_details(data_dict)

        elif job_type == JobTypeEnum.SEARCH_POST_BY_KEYWORD:
            # The validator ensures 'keyword' is present.
            # Defensive check retained for clarity, though redundant with validation.
            if job_config.keyword is None:
                 logger.error("Keyword missing for SEARCH_POST_BY_KEYWORD despite validation.")
                 raise ValueError("'keyword' is required for SEARCH_POST_BY_KEYWORD job.")
            logger.debug(f"Routing to search_post_by_keyword with keyword: '{job_config.keyword}'")
            # Pass specific arguments as expected by the client method signature.
            return await search_post_client.search_post_by_keyword(
                keyword=job_config.keyword,
                total_posts=job_config.post_limit # Pass post_limit as total_posts
            )

        elif job_type == JobTypeEnum.SEARCH_POST_BY_HASHTAG:
            # The validator ensures 'hashtag' is present.
             # Defensive check retained for clarity.
            if job_config.hashtag is None:
                 logger.error("Hashtag missing for SEARCH_POST_BY_HASHTAG despite validation.")
                 raise ValueError("'hashtag' is required for SEARCH_POST_BY_HASHTAG job.")
            logger.debug(f"Routing to search_post_by_hashtag with hashtag: '{job_config.hashtag}'")
            # Pass specific arguments as expected by the client method signature.
            return await search_post_client.search_post_by_hashtag(
                hashtag=job_config.hashtag,
                total_posts=job_config.post_limit # Pass post_limit as total_posts
            )

        elif job_type == JobTypeEnum.POST_DETAILS:
            # The validator ensures 'post_url_or_urn' is present and 'type' is set to POST.
            # Defensive check retained for clarity.
            if job_config.post_url_or_urn is None:
                logger.error("Post URL or URN missing for POST_DETAILS despite validation.")
                raise ValueError("'post_url_or_urn' is required for POST_DETAILS job.")
            logger.debug(f"Routing to get_post_details_with_enrichment for post URL/URN: '{job_config.post_url_or_urn}'")
            # Pass the full data dictionary to the client method.
            return await linkedin_post_fetcher.get_post_details_with_enrichment(data_dict)

        else:
            # This case should ideally not be reachable if JobTypeEnum is comprehensive
            # and the validator ensures one job type flag matches the job_type field.
            # Logging this helps identify gaps or unexpected enum values.
            logger.error(f"Unhandled job type encountered: {job_type}. This indicates a potential logic error or unsupported job type.")
            raise ValueError(f"Unsupported or unhandled job type: {job_type}")

    except Exception as e:
        # Catch any exception during the execution of the specific client method.
        # Log the exception with traceback information for debugging.
        logger.exception(f"Error executing scraper job '{job_type}' for user/entity '{job_config.username or job_config.keyword or job_config.hashtag}': {e}")
        # Re-raise the exception so it can be handled by the calling context
        # (e.g., a task queue worker or an API endpoint).
        raise


async def run_test(config_data: Dict[str, Any], test_name: str):
    """Helper async function to validate and run a test configuration."""
    print(f"\n\n\n\n--- Running Test: {test_name} ---")
    logger = get_prefect_or_regular_python_logger(__name__)
    try:
        # 1. Validate the configuration using the Pydantic model
        logger.info(f"Validating test configuration for '{test_name}': {config_data}")
        validated_config = ScrapingRequest.model_validate(config_data)
        logger.info(f"Validation successful for '{test_name}'.")

        # 2. Execute the job using the validated config
        # import ipdb; ipdb.set_trace()
        logger.info(f"Executing job '{validated_config.job_type}' for '{test_name}'...")
        result = await execute_scraper_job(validated_config)
        # import ipdb; ipdb.set_trace()
        logger.info(f"Job execution completed for '{test_name}'.")
        print(f"--- Job Result ({test_name}) ---")
        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            # Pretty print the result for better readability
            print("JOB SUCCESSFULLY EXECUTED!")
            result = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
            result = [(r.model_dump(mode="json") if isinstance(r, BaseModel) else r) for r in result] if isinstance(result, list) else result
            print(json.dumps(result, indent=4)[:500])
            # import pprint
            # pprint.pprint(result)
        print(f"-----------------------------")

    except ValidationError as e:
        # Log and print validation errors clearly.
        logger.error(f"Validation failed for test configuration '{test_name}'.")
        print(f"--- Validation Error ({test_name}) ---")
        # Pydantic v2 errors are nicely formatted.
        print(e)
        print(f"----------------------------------")
    except Exception as e:
        # Log and print any other errors during execution.
        logger.error(f"An error occurred during job execution for '{test_name}': {e}", exc_info=True) # Add exc_info for traceback
        print(f"--- Execution Error ({test_name}) ---")
        print(e)
        print(f"--------------------------------\n\n\n\n")


# --- Example Usage (for testing directly) ---
# This block allows running the entrypoint script directly for basic testing
# of different job configurations.
if __name__ == "__main__":

    PERSON_USERNAME = "example-user"
    URL = "https://www.linkedin.com/in/sytalal/"
    COMPANY_USERNAME = "microsoft"
    KEYWORD = "generative ai applications"
    HASHTAG = "genai"

    # Example 1: Get Company Posts (with comments)
    test_config_company_posts = {
        "job_type": JobTypeEnum.ENTITY_POSTS.value,
        "type": EntityTypeEnum.COMPANY.value,
        "entity_posts": YesNoEnum.YES.value, # Explicit flag matching job_type
        "username": COMPANY_USERNAME, # Example company username
        "post_limit": 1, # Limit the number of posts fetched
        "post_comments": YesNoEnum.YES.value, # Request comments for these posts
        "comment_limit": 3, # Limit comments per post
        "post_reactions": YesNoEnum.NO.value, # Do not fetch reactions
    }

    # Example 2: Get Person Posts (with reactions)
    test_config_person_posts = {
        "job_type": JobTypeEnum.ENTITY_POSTS.value,
        "type": EntityTypeEnum.PERSON.value,
        "entity_posts": YesNoEnum.YES.value,
        "username": PERSON_USERNAME, # Example person username
        "post_limit": 1,
        "post_comments": YesNoEnum.YES.value,
        "post_reactions": YesNoEnum.YES.value,
        "reaction_limit": 10,
    }

    # Example 3: Search by Keyword
    test_config_search_keyword = {
        "job_type": JobTypeEnum.SEARCH_POST_BY_KEYWORD.value,
        "search_post_by_keyword": YesNoEnum.YES.value, # Explicit flag matching job_type
        "keyword": KEYWORD,
        "post_limit": 7,
        # Other fields like type, username are not relevant/required for this job type.
    }

    # Example 4: Get User Activity (Likes)
    test_config_activity_likes = {
        "job_type": JobTypeEnum.ACTIVITY_REACTIONS.value,
        "activity_reactions": YesNoEnum.YES.value,
        "username": PERSON_USERNAME, # Example person username
        "post_limit": 1, # Limit the number of liked posts to retrieve
        # Optionally fetch comments/reactions *on* the posts the user liked
        "post_comments": YesNoEnum.YES.value,
        "comment_limit": 3,
        "post_reactions": YesNoEnum.YES.value,
        "reaction_limit": 10,
    }

    # Example 5: Get User Activity (Comments)
    test_config_activity_comments = {
        "job_type": JobTypeEnum.ACTIVITY_COMMENTS.value,
        "activity_comments": YesNoEnum.YES.value,
        "username": PERSON_USERNAME, # Example person username
        "post_limit": 1, # Limit the number of liked posts to retrieve
        # Optionally fetch comments/reactions *on* the posts the user liked
        "post_comments": YesNoEnum.YES.value,
        "comment_limit": 3,
        "post_reactions": YesNoEnum.YES.value,
        "reaction_limit": 10,
    }

    # Example 6: Get User Profile Info
    test_config_profile_info = {
        "job_type": JobTypeEnum.PROFILE_INFO.value,
        "profile_info": YesNoEnum.YES.value,
        "type": EntityTypeEnum.PERSON.value,
        "username": PERSON_USERNAME, # Example person username
    }

    test_config_profile_info_url = {
        "job_type": JobTypeEnum.PROFILE_INFO.value,
        "profile_info": YesNoEnum.YES.value,
        "url": URL,
    }

    # Example 7: Search by Hashtag 
    test_config_search_hashtag = {
        "job_type": JobTypeEnum.SEARCH_POST_BY_HASHTAG.value,
        "search_post_by_hashtag": YesNoEnum.YES.value,
        "hashtag": HASHTAG,
    }

    # Example 8: Get Company Profile Info
    test_config_company_info = {
        "job_type": JobTypeEnum.PROFILE_INFO.value,
        "profile_info": YesNoEnum.YES.value,
        "type": EntityTypeEnum.COMPANY.value,
        "username": COMPANY_USERNAME, # Example company username
    }

    # Example 9: Get Post Details with Enrichment
    test_config_post_details = {
        "job_type": JobTypeEnum.POST_DETAILS.value,
        "post_details": YesNoEnum.YES.value,
        "post_url_or_urn": "7335304292926451712",
        "post_comments": YesNoEnum.YES.value,
        "comment_limit": 50,
        "post_reactions": YesNoEnum.YES.value,
        "reaction_limit": 100,
    }

    

    # Define the list of tests to run
    tests_to_run = [
        # (test_config_company_posts, "Company Posts"),
        # (test_config_person_posts, "Person Posts"),
        # (test_config_search_keyword, "Keyword Search"),
        # (test_config_activity_likes, "User Activity (Likes)"),
        (test_config_profile_info, "User Profile Info"),
        # (test_config_profile_info_url, "User Profile Info (URL)"),
        # (test_config_company_info, "Company Profile Info"),
        # (test_config_search_hashtag, "Hashtag Search"),
        # (test_config_activity_comments, "User Activity (Comments)"),
        # (test_config_post_details, "Post Details with Enrichment"),
    ]

    # Run all defined tests asynchronously
    async def main():
        # Use asyncio.gather to run tests potentially concurrently,
        # although the underlying API calls might still be sequential depending
        # on client implementation and rate limits.
        await asyncio.gather(*(run_test(config, name) for config, name in tests_to_run))

    # Execute the main async function that runs all tests.
    asyncio.run(main())
