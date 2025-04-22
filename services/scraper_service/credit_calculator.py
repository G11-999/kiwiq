import math
from typing import Tuple, Union, Dict, Any

from scraper_service.settings import rapid_api_settings
from scraper_service.client.schemas import (
    PostsRequest,
    ProfileRequest,
    CompanyRequest,
    PostReactionsRequest,
    ProfilePostCommentsRequest,
    CompanyPostCommentsRequest
)
from scraper_service.client.utils.enums import JobType
from global_config.logger import get_logger
logger = get_logger(__name__)

POSTS_BATCH_SIZE = rapid_api_settings.BATCH_SIZE 
REACTORS_BATCH_SIZE = rapid_api_settings.DEFAULT_REACTION_LIMIT 

#  Union of possible request schemas
RequestSchemaUnion = Union[
    PostsRequest,
    ProfileRequest,
    CompanyRequest,
    PostReactionsRequest,
    ProfilePostCommentsRequest,
    CompanyPostCommentsRequest
]

# --- Helper function for reaction cost calculation ---
def _calculate_reaction_credits(limit: Any) -> Tuple[int, int]:
    """Calculates min/max credits for fetching reactions based on limit."""
    reaction_limit = limit or rapid_api_settings.DEFAULT_REACTION_LIMIT
    if reaction_limit <= 0:
        return 0, 0
    
    batches = math.ceil(reaction_limit / REACTORS_BATCH_SIZE)
    cost = batches * 1 # Assuming 1 credit per batch of reactions
    return cost, cost

# --- Main Calculation Function ---
def calculate_credits(job_type: JobType, request_data: RequestSchemaUnion) -> Tuple[int, int]:
    """
    Calculates the estimated minimum and maximum credits required for a scraping job.

    Args:
        job_type (JobType): The type of scraping job to perform.
        request_data (RequestSchemaUnion): The Pydantic model instance containing
                                           the request parameters for the job.

    Returns:
        Tuple[int, int]: A tuple containing (min_credits, max_credits).
                         Returns (0, 0) for unknown job types or invalid input.

    Raises:
        TypeError: If request_data is not of the expected type for the job_type.
    """
    min_credits = 0
    max_credits = 0

    # === Profile Fetching ===
    if job_type in [JobType.FETCH_USER_PROFILE, JobType.FETCH_COMPANY_PROFILE]:
        if not isinstance(request_data, (ProfileRequest, CompanyRequest)):
             raise TypeError(f"Expected ProfileRequest or CompanyRequest for {job_type.value}, got {type(request_data)}")
        # 1 credit per profile fetch
        min_credits = 1
        max_credits = 1

    # === Post List Fetching (User, Company, Likes) ===
    elif job_type in [JobType.FETCH_USER_POSTS, JobType.FETCH_COMPANY_POSTS, JobType.FETCH_USER_LIKES]:
        if not isinstance(request_data, PostsRequest):
            raise TypeError(f"Expected PostsRequest for {job_type.value}, got {type(request_data)}")

        req: PostsRequest = request_data
        # Check if post_limit is explicitly set to 0 first, as 0 is falsy
        if req.post_limit == 0:
            return 0, 0
        post_limit = req.post_limit if req.post_limit is not None else rapid_api_settings.DEFAULT_POST_LIMIT
        
        # Base cost for fetching the posts/likes list (paginated)
        post_batches = math.ceil(post_limit / POSTS_BATCH_SIZE)
        base_post_cost = post_batches * 1 # 1 credit per batch of posts/likes
        min_credits += base_post_cost
        max_credits += base_post_cost

        # --- Per-Post Costs (if fetching comments/reactions for EACH post) ---
        credits_per_post_for_comments = 0
        if req.post_comments == "yes":
            # 1 credit per post to fetch its comments list
            credits_per_post_for_comments = 1

        min_credits_per_post_for_reactions = 0
        max_credits_per_post_for_reactions = 0
        if req.post_reactions == "yes":
            min_cost, max_cost = _calculate_reaction_credits(req.reaction_limit)
            min_credits_per_post_for_reactions = min_cost
            max_credits_per_post_for_reactions = max_cost

        # Add costs for comments/reactions *per post* fetched
        effective_posts = post_limit
        min_credits += effective_posts * (credits_per_post_for_comments + min_credits_per_post_for_reactions)
        max_credits += effective_posts * (credits_per_post_for_comments + max_credits_per_post_for_reactions)

    # === User Activity: Comments Made By User ===
    elif job_type == JobType.FETCH_USER_COMMENTS_ACTIVITY:
        if not isinstance(request_data, ProfileRequest):
             raise TypeError(f"Expected ProfileRequest for {job_type.value}, got {type(request_data)}")
        # Fetching comments made by a user is 1 credit flat.
        # The API endpoint /get-profile-comments doesn't is not paginated in the client that is why.
        min_credits = 1
        max_credits = 1

    # === Single Post Details: Reactions ===
    elif job_type == JobType.FETCH_POST_REACTIONS:
        if not isinstance(request_data, PostReactionsRequest):
            raise TypeError(f"Expected PostReactionsRequest for {job_type.value}, got {type(request_data)}")
        req: PostReactionsRequest = request_data
        # Fetching reactions for a single post depends on the reaction_limit passed to the *method*
        reaction_limit_for_calc = rapid_api_settings.DEFAULT_REACTION_LIMIT 
        min_cost, max_cost = _calculate_reaction_credits(reaction_limit_for_calc)
        min_credits = min_cost
        max_credits = max_cost


    # === Single Post Details: Comments ===
    elif job_type == JobType.FETCH_POST_COMMENTS:
         if not isinstance(request_data, (ProfilePostCommentsRequest, CompanyPostCommentsRequest)):
             raise TypeError(f"Expected ProfilePostCommentsRequest or CompanyPostCommentsRequest for {job_type.value}, got {type(request_data)}")
         # Fetching comments for a single post is 1 credit flat.
         # The API endpoints /get-profile-posts-comments and /get-company-post-comments as are not paginated in the client.
         min_credits = 1
         max_credits = 1

    else:
        # Optional: Log a warning for unhandled job types
        logger.warning(f"Credit calculation not implemented for job type: {job_type}")
        # pass

    # Ensure non-negative credits
    min_credits = max(0, min_credits)
    max_credits = max(0, max_credits)

    return min_credits, max_credits
