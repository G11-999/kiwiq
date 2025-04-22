from enum import Enum
class JobType(Enum):
    FETCH_USER_PROFILE = "fetch_user_profile"
    FETCH_COMPANY_PROFILE = "fetch_company_profile"
    FETCH_USER_POSTS = "fetch_user_posts"
    FETCH_COMPANY_POSTS = "fetch_company_posts"
    FETCH_USER_LIKES = "fetch_user_likes" 
    FETCH_USER_COMMENTS_ACTIVITY = "fetch_user_comments_activity" 
    FETCH_POST_REACTIONS = "fetch_post_reactions" 
    FETCH_POST_COMMENTS = "fetch_post_comments" 