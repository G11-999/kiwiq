"""
Comprehensive tests for all LinkedIn API client modules.

This module provides a complete test suite for all RapidAPI LinkedIn client classes and methods.
Tests include both basic functionality tests and real API interaction tests with proper error handling.
"""

import asyncio
import math

from scraper_service.client.core_api_client import RapidAPIClient 
from scraper_service.client.post_manager import LinkedinPostFetcher
from scraper_service.settings import rapid_api_settings
from scraper_service.client.schemas import ProfileRequest, CompanyRequest, ProfileResponse, CompanyResponse , ProfilePost ,PostsRequest, LikeItem , GetProfileCommentResponse, PostsRequest, PostReactionsRequest, ProfilePostCommentsRequest, CompanyPostCommentsRequest
from scraper_service.credit_calculator import calculate_credits, JobType
from global_config.logger import get_logger
logger = get_logger(__name__)

# Get API credentials and test data from settings
API_KEY = rapid_api_settings.RAPID_API_KEY
API_HOST = rapid_api_settings.RAPID_API_HOST

# Test data from settings
TEST_PROFILE_USERNAME = rapid_api_settings.TEST_PROFILE_USERNAME
TEST_PROFILE_URL = rapid_api_settings.TEST_PROFILE_URL
TEST_POST_PROFILE_USERNAME = rapid_api_settings.TEST_POST_PROFILE_USERNAME
TEST_POST_COMPANY_USERNAME = rapid_api_settings.TEST_POST_COMPANY_USERNAME
TEST_COMPANY_USERNAME = rapid_api_settings.TEST_COMPANY_USERNAME
TEST_COMPANY_URL = rapid_api_settings.TEST_COMPANY_URL


# Retry configuration from settings
MAX_RETRIES = rapid_api_settings.MAX_RETRIES
RETRY_DELAY = rapid_api_settings.RETRY_DELAY



async def test_core_client():
    """Test core RapidAPIClient functionality."""
    print("\n--- Testing RapidAPIClient Core Functionality ---")
    
    # Create client instance
    client = RapidAPIClient(api_key=API_KEY, base_url=API_HOST)
    
    # Test validation methods
    print("Testing API key validation...")
    is_valid = client.validate_api_key()
    print(f"API key validation: {'✓ Valid' if is_valid else '✗ Invalid'}")
    
    print("\nTesting direct get profile data...")
    request = ProfileRequest(username=TEST_PROFILE_USERNAME)
    response = await client.get_profile_data(request)
    
    if isinstance(response, ProfileResponse):
        try:
            profile_response = ProfileResponse.model_validate(response)
            print(f"✓ Successfully parsed profile response with Pydantic model")
            print(f"Profile details: {profile_response.firstName} {profile_response.lastName}, {profile_response.headline}")
        except Exception as e:
            print(f"✗ Failed to parse profile response: {str(e)}")
            print(f"Response keys: {list(response.keys())[:10]}")
      

    print("\nTesting get profile comments data...")
    request = ProfileRequest(username=TEST_PROFILE_USERNAME)
    raw_response = await client.get_profile_post_comments(request)
    response = GetProfileCommentResponse(**raw_response)
    print("Profile comments data")
    print(response, "response")
    print(response.highlightedComments, "highlightedComments")
    print(response.highlightedCommentsActivityCounts, "highlightedCommentsActivityCounts")
    print(response.text, "text")
    print(response.totalReactionCount, "totalReactionCount")
    print(response.likeCount, "likeCount")
    print(response.appreciationCount, "appreciationCount")
    
        
    print("\nTesting get company data...")
    request = CompanyRequest(username=TEST_COMPANY_USERNAME)
    response = await client.get_company_data(request)
    
    if isinstance(response, CompanyResponse):
        try:
            # Try to parse the response using our updated model
            company_response = CompanyResponse.model_validate(response)
            print(f"✓ Successfully parsed company response with Pydantic model")
            print(f"Company details: {company_response.data.name}, {company_response.data.tagline}")
            print(f"Followers: {company_response.data.followerCount}")

        except Exception as e:
            print(f"✗ Failed to parse company response: {str(e)}")
    
    return client




async def test_posts_client():
    """Test posts-related functionality."""
    print("\n--- Testing Posts Client for A User profile Functionality ---")

    # Initialize post fetcher client
    post_fetcher = LinkedinPostFetcher(api_key=API_KEY, base_url=API_HOST)

    # === 1. Test get_profile_posts ===
    request_profile = PostsRequest(
        username=TEST_POST_PROFILE_USERNAME,
        post_comments="yes",
        post_reactions="yes",
    )

    print("\nTesting get_profile_posts method...")
    try:
        posts_response = await post_fetcher.get_profile_posts(request_profile)

        if isinstance(posts_response, list) and posts_response:
            print(f"✓ Retrieved {len(posts_response)} profile posts")
            first_post: ProfilePost = posts_response[0]

            print("First profile post details:")
            print(f"Text: {first_post.text[:100]}..." if first_post.text else "No text found")
            print(f"Reactions: {first_post.totalreactions}")
            print(f"Comments: {first_post.totalcomments}")
            print(f"Comments: {first_post.comments}")
            print(f"Reactions: {first_post.reactions}")
            print(f"Post URL: {first_post.postUrl}")
        else:
            print("✗ No profile posts returned or empty list")
    except Exception as e:
        print(f"✗ Error while fetching profile posts: {str(e)}")

    # === 2. Test get_company_posts ===

    print("\n--- Testing Posts Client for A Company Page Functionality ---")
    request_company = PostsRequest(
        username=TEST_POST_COMPANY_USERNAME,
        post_comments="yes",
        post_reactions="yes",
    )

    print("\nTesting get_company_posts method...")
    try:
        company_posts = await post_fetcher.get_company_posts(request_company)

        if isinstance(company_posts, list) and company_posts:
            print(f"✓ Retrieved {len(company_posts)} company posts")
            first_company_post = company_posts[0]

            print("First company post details:")
            print(f"Text: {first_company_post.text[:100]}..." if first_company_post.text else "No text found")
            print(f"Reactions: {first_company_post.totalReactionCount}")
            print(f"Comments: {first_company_post.commentsCount}")
            print(f"Comments: {first_company_post.comments}")
            print(f"Reactions: {first_company_post.reactions}")
            print(f"Post URL: {first_company_post.postUrl}")
        else:
            print("✗ No company posts returned or empty list")
    except Exception as e:
        print(f"✗ Error while fetching company posts: {str(e)}")


    # === 3. Test get_user_post_likes ===
    post_fetcher = LinkedinPostFetcher(api_key=API_KEY, base_url=API_HOST)
    likes_request  = PostsRequest(
        username=TEST_POST_PROFILE_USERNAME,
        post_comments="no",
        post_reactions="no",
    )
    likes_response = await post_fetcher.get_user_likes_with_details(likes_request)

    if isinstance(likes_response, list):
        print(f"✓ Retrieved {len(likes_response)} likes")
        if likes_response:
            first_like: LikeItem = likes_response[0]
            print(f"First Like Post URL: {first_like.postUrl}")
            print(f"First Like Owner: {first_like.owner.firstName} {first_like.owner.lastName}")
        else:
            print("✗ No likes returned.")
    else:
        print("✗ Response is not a list.")
    
    


async def test_credit_calculator():
    """Test credit calculator functionality for various job types."""
    print("\n--- Testing Credit Calculator Functionality ---")

    # Get batch sizes from settings for calculations
    POST_BATCH = rapid_api_settings.BATCH_SIZE or 50
    REACTION_BATCH = rapid_api_settings.DEFAULT_REACTION_LIMIT or 30

    # --- Helper for Reaction Cost ---
    def expected_reaction_cost(limit):
        if not limit or limit <= 0: return 0
        return math.ceil(limit / REACTION_BATCH) * 1

    # --- Define Test Cases ---
    test_cases = [
        # --- Profile Fetching ---
        {
            "name": "Fetch User Profile",
            "job_type": JobType.FETCH_USER_PROFILE,
            "request": ProfileRequest(username="testuser"),
            "expected_min": 1,
            "expected_max": 1
        },
        {
            "name": "Fetch Company Profile",
            "job_type": JobType.FETCH_COMPANY_PROFILE,
            "request": CompanyRequest(username="testcompany"),
            "expected_min": 1,
            "expected_max": 1
        },

        # --- Post List Fetching (User/Company/Likes) ---
        {
            "name": "Fetch User Posts (No posts, no extras)",
            "job_type": JobType.FETCH_USER_POSTS,
            "request": PostsRequest(username="testuser", post_limit=0, post_comments="no", post_reactions="no"),
            "expected_min": 0,
            "expected_max": 0
        },
        {
            "name": "Fetch Company Posts (10 posts, no extras)",
            "job_type": JobType.FETCH_COMPANY_POSTS,
            "request": PostsRequest(username="testcompany", post_limit=10, post_comments="no", post_reactions="no"),
            "expected_min": math.ceil(10 / POST_BATCH) * 1,
            "expected_max": math.ceil(10 / POST_BATCH) * 1
        },
        {
            "name": "Fetch User Likes (10 likes with comments)",
            "job_type": JobType.FETCH_USER_LIKES,
            "request": PostsRequest(username="testuser", post_limit=10, post_comments="yes", post_reactions="no"),
            "expected_min": (math.ceil(10 / POST_BATCH) * 1) + (10 * 1), # Base post cost + 1 credit per post for comments
            "expected_max": (math.ceil(10 / POST_BATCH) * 1) + (10 * 1)
        },
        {
            "name": "Fetch User Posts (10 posts with reactions, limit 30)",
            "job_type": JobType.FETCH_USER_POSTS,
            "request": PostsRequest(username="testuser", post_limit=10, post_comments="no", post_reactions="yes", reaction_limit=30),
            "expected_min": (math.ceil(10 / POST_BATCH) * 1) + (10 * expected_reaction_cost(30)), # Base + 10 posts * reaction cost
            "expected_max": (math.ceil(10 / POST_BATCH) * 1) + (10 * expected_reaction_cost(30))
        },
        {
            "name": "Fetch Company Posts (10 posts with reactions, limit 100)",
            "job_type": JobType.FETCH_COMPANY_POSTS,
            "request": PostsRequest(username="testcompany", post_limit=10, post_comments="no", post_reactions="yes", reaction_limit=100),
            "expected_min": (math.ceil(10 / POST_BATCH) * 1) + (10 * expected_reaction_cost(100)),
            "expected_max": (math.ceil(10 / POST_BATCH) * 1) + (10 * expected_reaction_cost(100))
        },
        {
            "name": "Fetch User Likes (10 likes with comments and reactions, limit 50)",
            "job_type": JobType.FETCH_USER_LIKES,
            "request": PostsRequest(username="testuser", post_limit=10, post_comments="yes", post_reactions="yes", reaction_limit=50),
            "expected_min": (math.ceil(10 / POST_BATCH) * 1) + (10 * (1 + expected_reaction_cost(50))), # Base + 10 posts * (comment cost + reaction cost)
            "expected_max": (math.ceil(10 / POST_BATCH) * 1) + (10 * (1 + expected_reaction_cost(50)))
        },
        {
            "name": "Fetch User Posts (150 posts, no extras)",
            "job_type": JobType.FETCH_USER_POSTS,
            "request": PostsRequest(username="testuser", post_limit=150, post_comments="no", post_reactions="no"),
            "expected_min": math.ceil(150 / POST_BATCH) * 1,
            "expected_max": math.ceil(150 / POST_BATCH) * 1
        },

        # --- User Activity: Comments Made ---
        {
            "name": "Fetch User Comments Activity",
            "job_type": JobType.FETCH_USER_COMMENTS_ACTIVITY,
            "request": ProfileRequest(username="testuser"),
            "expected_min": 1,
            "expected_max": 1
        },

        # --- Single Post Details ---
        {
            "name": "Fetch Post Reactions (Estimate with default limit)",
            "job_type": JobType.FETCH_POST_REACTIONS,
            "request": PostReactionsRequest(post_url="http://some.url"),
            # Calculation assumes default reaction limit defined in settings for estimation
            "expected_min": expected_reaction_cost(rapid_api_settings.DEFAULT_REACTION_LIMIT),
            "expected_max": expected_reaction_cost(rapid_api_settings.DEFAULT_REACTION_LIMIT)
        },
        # Note: To test FETCH_POST_REACTIONS with a specific limit, the calculator
        # would need modification or the test would need to simulate passing the limit.
        {
            "name": "Fetch Post Comments (Profile)",
            "job_type": JobType.FETCH_POST_COMMENTS,
            "request": ProfilePostCommentsRequest(post_urn="urn:li:activity:123"),
            "expected_min": 1,
            "expected_max": 1
        },
        {
            "name": "Fetch Post Comments (Company)",
            "job_type": JobType.FETCH_POST_COMMENTS,
            "request": CompanyPostCommentsRequest(post_urn="urn:li:share:456"),
            "expected_min": 1,
            "expected_max": 1
        },
    ]

    passed_count = 0
    failed_count = 0

    for i, test_case in enumerate(test_cases):
        print(f"\n--- Test Case {i+1}: {test_case['name']} ---")
        print(f"Job Type: {test_case['job_type']}")
        print(f"Request Data: {test_case['request']}")

        try:
            min_credits, max_credits = calculate_credits(
                job_type=test_case['job_type'],
                request_data=test_case['request']
            )

            print(f"Expected: Min={test_case['expected_min']}, Max={test_case['expected_max']}")
            print(f"Actual:   Min={min_credits}, Max={max_credits}")

            if min_credits == test_case['expected_min'] and max_credits == test_case['expected_max']:
                print("✓ PASSED")
                passed_count += 1
            else:
                print("✗ FAILED")
                failed_count += 1
        except TypeError as e:
            print(f"✗ FAILED with TypeError: {e}")
            failed_count += 1
        except Exception as e:
             print(f"✗ FAILED with unexpected error: {e}")
             failed_count += 1


    print(f"\nCredit calculator tests summary: {passed_count} passed, {failed_count} failed")
    return passed_count, failed_count

# Uncomment the test and part you want to run
async def main():
    """Run all tests."""
    print("=== Starting Comprehensive LinkedIn API Client Tests ===")
    print(f"Using API Key: {API_KEY[:5]}...{API_KEY[-5:]}")
    print(f"API Host: {API_HOST}")
    
    # Test core client , has profile , company and post data
    # client = await test_core_client()
    
  
    
    # # Test posts client has profile posts with comments and reactions , company posts with comments and reactions , user likes with details
    # post_urn = await test_posts_client()

      # Test credit calculator
    await test_credit_calculator()
    
    print("\n=== Comprehensive Tests Completed ===")


if __name__ == "__main__":
    asyncio.run(main()) 