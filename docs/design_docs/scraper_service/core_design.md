# Scraper Service - Core Job Design

This document outlines the design for triggering various LinkedIn data scraping jobs using the `scraper_service` client components.

## Core Components

*   **`RapidAPIClient` (`core_api_client.py`):** Base client for handling direct requests to the RapidAPI endpoints (e.g., fetching profiles, specific comments).
*   **`LinkedinPostFetcher` (`post_manager.py`):** Specialized client built on `RapidAPIClient` for fetching posts, reactions, and comments associated with profiles or companies, handling pagination and aggregation logic.
*   **`schemas.py`:** Defines Pydantic models for request parameters and response structures for all API interactions.

## Job Definitions

Below are the definitions for triggering specific scraping tasks:

### 1. Fetch User Posted Posts

*   **Purpose:** Retrieve posts made by a specific LinkedIn user profile.
*   **Triggering Mechanism:**
    *   **Client Class:** `LinkedinPostFetcher`
    *   **Method:** `get_profile_posts`
    *   **Request Schema:** `PostsRequest`
    *   **Key Parameters:**
        *   `username`: LinkedIn profile username (required).
        *   `post_limit`: Maximum number of posts to fetch (optional, defaults apply).
        *   `post_comments`: Set to `"no"` (default).
        *   `post_reactions`: Set to `"no"` (default).
*   **Response Schema:** `List[ProfilePost]`
*   **Notes:** Pagination is handled internally by the client based on `post_limit`. Reactions and comments are *not* fetched by default for this job type, you will have to specify in the config.

### 2. Fetch Company Posted Posts

*   **Purpose:** Retrieve posts made by a specific LinkedIn company page.
*   **Triggering Mechanism:**
    *   **Client Class:** `LinkedinPostFetcher`
    *   **Method:** `get_company_posts`
    *   **Request Schema:** `PostsRequest`
    *   **Key Parameters:**
        *   `username`: LinkedIn company username (required).
        *   `post_limit`: Maximum number of posts to fetch (optional, defaults apply).
        *   `post_comments`: Set to `"no"` (default).
        *   `post_reactions`: Set to `"no"` (default).
*   **Response Schema:** `List[CompanyPostResponse]`
*   **Notes:** Pagination is handled internally. Reactions and comments are *not* fetched by default.Same as above you will have to mention in the request config.

### 3. Fetch User/Company Posts with Reactions/Comments

*   **Purpose:** Retrieve posts made by a user or company, including associated reactions and comments for each post.
*   **Triggering Mechanism:**
    *   **Client Class:** `LinkedinPostFetcher`
    *   **Method:** `get_profile_posts` (for users) or `get_company_posts` (for companies).
    *   **Request Schema:** `PostsRequest`
    *   **Key Parameters:**
        *   `username`: Profile or company username (required).
        *   `post_limit`: Max posts (optional).
        *   `post_comments`: Set to `"yes"` (required to fetch comments).
        *   `comment_limit`: Max comments per post (optional, defaults apply).
        *   `post_reactions`: Set to `"yes"` (required to fetch reactions).
        *   `reaction_limit`: Max reactions per post (optional, defaults apply).
*   **Response Schema:** `List[ProfilePost]` or `List[CompanyPostResponse]`, where the `comments` and `reactions` fields within each post object are populated.
*   **Notes:** This combines post fetching with subsequent calls to fetch comments and reactions for each retrieved post, up to the specified limits.

### 4. Fetch User Activity: Reactions (Liked Posts)

*   **Purpose:** Retrieve posts that a specific LinkedIn user has *liked*.
*   **Triggering Mechanism:**
    *   **Client Class:** `LinkedinPostFetcher`
    *   **Method:** `get_user_likes_with_details`
    *   **Request Schema:** `PostsRequest`
    *   **Key Parameters:**
        *   `username`: LinkedIn profile username (required).
        *   `post_limit`: Maximum number of *liked* posts to fetch (optional, defaults apply).
        *   `post_comments`: Set to `"yes"`/`"no"` to fetch comments on the *liked* posts (optional).
        *   `comment_limit`: Max comments per liked post (optional).
        *   `post_reactions`: Set to `"yes"`/`"no"` to fetch reactions on the *liked* posts (optional).
        *   `reaction_limit`: Max reactions per liked post (optional).
*   **Response Schema:** `List[LikeItem]`
*   **Notes:** This job specifically targets posts the user has *liked*. It uses the `/get-profile-likes` endpoint. It can optionally retrieve the comments and reactions *on those liked posts*.

### 5. Fetch User Activity: Comments (Comments Made by User)

*   **Purpose:** Retrieve comments made by a specific LinkedIn user on various posts across LinkedIn.
*   **Triggering Mechanism:**
    *   **Client Class:** `RapidAPIClient`
    *   **Method:** `get_profile_post_comments`
    *   **Request Schema:** `ProfileRequest`
    *   **Key Parameters:**
        *   `username`: LinkedIn profile username (required).
*   **Response Schema:** `List[GetProfileCommentResponse]`
*   **Notes:** This job uses the `/get-profile-comments` endpoint. The response structure (`GetProfileCommentResponse` with `highlightedComments`, `highlightedCommentsActivityCounts`, `author`) suggests it retrieves comments *made by* the specified user on other posts.

### 6. Fetch Reactions/Comments for a Specific Post

*   **Purpose:** Retrieve reactions or comments for a single, specific LinkedIn post identified by its URL or URN.
*   **Triggering Mechanism:**
    *   **Reactions:**
        *   **Client Class:** `LinkedinPostFetcher`
        *   **Method:** `get_post_reactions`
        *   **Request Schema:** `PostReactionsRequest`
        *   **Key Parameters:**
            *   `post_url`: Full URL of the LinkedIn post (required).
            *   `reaction_limit` (passed as argument to method): Max reactions (optional).
        *   **Response Schema:** `List[PostReaction]`
    *   **Comments (Profile Post):**
        *   **Client Class:** `LinkedinPostFetcher`
        *   **Method:** `get_profile_post_comments`
        *   **Request Schema:** `ProfilePostCommentsRequest`
        *   **Key Parameters:**
            *   `post_urn`: URN of the LinkedIn post (required).
            *   `limit` (passed as argument to method): Max comments (optional).
        *   **Response Schema:** `List[PostComment]`
    *   **Comments (Company Post):**
        *   **Client Class:** `LinkedinPostFetcher`
        *   **Method:** `get_company_post_comments`
        *   **Request Schema:** `CompanyPostCommentsRequest`
        *   **Key Parameters:**
            *   `post_urn`: URN of the LinkedIn post (required).
            *   `comment_limit` (passed as argument to method): Max comments (optional).
        *   **Response Schema:** `List[CompanyPostComment]`
*   **Notes:** Requires the unique identifier (URL or URN) of the post, for reactions it is the URL for comments it is the URN. I have made a util function also that extract URN from a URL aswell.

### 7. Batch Fetch User Profiles

*   **Purpose:** Retrieve profile details for multiple LinkedIn users.
*   **Triggering Mechanism:**
    *   **Client Class:** `RapidAPIClient`
    *   **Method:** `get_profile_data`
    *   **Request Schema:** `ProfileRequest`
    *   **Key Parameters:** `username` (required).
    *   **Response Schema:** `ProfileResponse`
*   **Notes:** There is no dedicated batch endpoint. To fetch multiple profiles, iterate through the list of usernames and call `get_profile_data` for each one individually. We can add appropriate delays in between.

### 8. Batch Fetch Company Profiles

*   **Purpose:** Retrieve profile details for multiple LinkedIn company pages.
*   **Triggering Mechanism:**
    *   **Client Class:** `RapidAPIClient`
    *   **Method:** `get_company_data`
    *   **Request Schema:** `CompanyRequest`
    *   **Key Parameters:** `username` (required).
    *   **Response Schema:** `CompanyResponse`
*   **Notes:** Similar to user profiles, there is no dedicated batch endpoint. Iterate through company usernames and call `get_company_data` individually for each, adding delays as necessary. 