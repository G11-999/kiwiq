"""
LinkedIn post fetcher client for RapidAPI.

This module provides a client for fetching LinkedIn posts, comments, and reactions 
using the RapidAPI LinkedIn scraper endpoint.
"""
import asyncio
from typing import Dict, List, Any, Optional

from scraper_service.client.core_api_client import RapidAPIClient
from scraper_service.settings import rapid_api_settings
from scraper_service.client.utils.url_helper import extract_urn_from_url
from global_config.logger import get_logger
from scraper_service.client.schemas import PostReactionsRequest , ProfilePostCommentsRequest, PostComment, PostsRequest, ProfilePost, PostReaction , PostDetailsRequest , PostDetailsResponse, CompanyPostCommentsRequest, CompanyPostResponse , CompanyPost , CompanyPostAuthor , CompanyPostArticle , CompanyPostComment , CompanyPostAuthor, LikeItem , LikeActivity , LikeOwner
from scraper_service.client.utils.url_helper import extract_urn_from_url
# Configure logging
logger = get_logger(__name__)

class LinkedinPostFetcher:
    """
    Client for fetching LinkedIn posts, comments, and reactions.
    
    This client provides methods for fetching LinkedIn posts for a user or company,
    as well as comments and reactions on those posts. It uses the RapidAPI
    LinkedIn scraper endpoint.
    """
    
    def __init__(self, api_key=None, base_url=None):
        """
        Initialize the LinkedIn Post Fetcher.
        
        Args:
            api_key (Optional[str]): API key for RapidAPI. Defaults to settings value.
            base_url (Optional[str]): Host URL for RapidAPI. Defaults to settings value.
        """
        self.rapidapi_key = api_key or rapid_api_settings.RAPID_API_KEY
        self.rapidapi_host = base_url or rapid_api_settings.RAPID_API_BASE_URL
        self.api_client = RapidAPIClient(self.rapidapi_key, self.rapidapi_host)

    async def get_company_posts(self, request: PostsRequest) -> List[CompanyPostResponse]:
        """
        Fetch posts for a LinkedIn company page.
        
        Args:
            request (PostsRequest): Request object containing:
                - username (str): LinkedIn company username
                - post_limit (Optional[int]): Maximum number of posts to fetch
                - post_comments (str): "yes" or "no" to include comments
                - post_reactions (str): "yes" or "no" to include reactions
                - comment_limit (Optional[int]): Maximum number of comments per post
                - reaction_limit (Optional[int]): Maximum number of reactions per post
        
        Returns:
            List[CompanyPostResponse]: List of company posts with their details, comments, and reactions if requested.
            
        Raises:
            ValueError: If username is not provided.
            
        Example:
            >>> request = PostsRequest(username="microsoft", post_limit=5, post_comments="yes", post_reactions="yes")
            >>> posts = await fetcher.get_company_posts(request)
            >>> print(f"Retrieved {len(posts)} posts")
        """
        if not request.username:
            raise ValueError("Username is required")

        post_limit = request.post_limit or rapid_api_settings.DEFAULT_POST_LIMIT
        comment_limit = request.comment_limit or rapid_api_settings.DEFAULT_COMMENT_LIMIT
        reaction_limit = request.reaction_limit or rapid_api_settings.DEFAULT_REACTION_LIMIT

        all_posts = []
        start = 0
        pagination_token = None

        while len(all_posts) < post_limit:
            endpoint = f"/get-company-posts?username={request.username}&start={start}"
            if pagination_token:
                endpoint += f"&paginationToken={pagination_token}"

            response = await self.api_client.make_get_request(endpoint)

            if not response.get("success", False):
                logger.error(f"Error fetching company posts: {response.get('message')}")
                return CompanyPostResponse(posts=[])

            posts_batch = response.get("data", [])
            all_posts.extend(posts_batch)

            if len(all_posts) >= post_limit:
                break

            pagination_token = response.get("paginationToken")
            if not pagination_token:
                break

            start += rapid_api_settings.BATCH_SIZE

        posts: List[CompanyPost] = []

        for raw_post in all_posts[:post_limit]:
            if not isinstance(raw_post, dict):
                continue

            post_url = raw_post.get("postUrl")
            share_url = raw_post.get("shareUrl") or await self.fetch_share_url(post_url)
            urn =  extract_urn_from_url(post_url)

            # Prepare nested fields
            author_data = raw_post.get("author", {}).get("company")
            author = CompanyPostAuthor(**author_data) if author_data else None

            # I have added this to handle the case where the article is not present in the response , it was giving unbound Local error
            article = None
            article_data = raw_post.get("article")
            if isinstance(article_data, dict) and "title" in article_data:
                try:
                    article = CompanyPostArticle(**article_data)
                except Exception as e:
                    logger.warning(f"Invalid article data: {article_data}, error: {e}")

            comments: List[CompanyPostComment] = []
            if request.post_comments == "yes" and urn:
                comments = await self.get_company_post_comments(
                    CompanyPostCommentsRequest(post_urn=urn),
                    comment_limit
                )
            reactions = []
            if request.post_reactions.lower() == "yes" and post_url:
                try:
                    reaction_objs = await self.get_post_reactions(
                        PostReactionsRequest(post_url=share_url),
                        reaction_limit
                    )
                    reactions = [r.model_dump() for r in reaction_objs]  
                except Exception as e:
                    logger.error(f"Error in get_profile_post_reactions: {e}")
                    reactions = []

            post = CompanyPostResponse(
                text=raw_post.get("text", ""),
                totalReactionCount=raw_post.get("totalReactionCount", 0),
                likeCount=raw_post.get("likeCount", 0),
                appreciationCount=raw_post.get("appreciationCount", 0),
                empathyCount=raw_post.get("empathyCount", 0),
                InterestCount=raw_post.get("InterestCount", 0),
                praiseCount=raw_post.get("praiseCount", 0),
                commentsCount=raw_post.get("commentsCount", 0),
                repostsCount=raw_post.get("repostsCount", 0),
                postUrl=post_url,
                postedAt=raw_post.get("postedAt", ""),
                urn=raw_post.get("urn", ""),
                author=author,
                article=article,
                video=raw_post.get("video", []),
                comments=comments,
                reactions=reactions  
            )

            posts.append(post)

        return posts

    async def get_company_post_comments(
        self, 
        request: CompanyPostCommentsRequest, 
        comment_limit: int
    ) -> List[CompanyPostComment]:
        """
        Fetch comments for a company LinkedIn post.
        
        Args:
            request (CompanyPostCommentsRequest): Request object containing:
                - post_urn (str): The URN identifier of the LinkedIn post
            comment_limit (int): Maximum number of comments to fetch
            
        Returns:
            List[CompanyPostComment]: List of parsed comment models
            
        Example:
            >>> request = CompanyPostCommentsRequest(post_urn="urn:li:activity:1234567890")
            >>> comments = await fetcher.get_company_post_comments(request, 10)
            >>> print(f"Retrieved {len(comments)} comments")
        """
        if not request.post_urn:
            return []

        endpoint = f"/get-company-post-comments?urn={request.post_urn}"
        response = await self.api_client.make_get_request(endpoint)

        raw_comments = []
        if isinstance(response, list):
            raw_comments = response
        elif isinstance(response, dict):
            if not response.get("success", False):
                logger.error(f"Error fetching comments: {response.get('message')}")
                return []
            data = response.get("data") 
            if isinstance(data, list): 
                raw_comments = data
            elif isinstance(data, dict):  
                raw_comments = data.get("comments", [])
        else:
            logger.error(f"Unexpected response type: {type(response)}")
            return []

        comments: List[CompanyPostComment] = []
        for c in raw_comments[:comment_limit]:
            author = c.get("author", {}) if isinstance(c, dict) else {}
            full_name = f"{author.get('firstName', '')} {author.get('lastName', '')}".strip()
            comments.append(CompanyPostComment(
                name=full_name,
                linkedinUrl=author.get("linkedinUrl", ""),
                title=author.get("title", ""),
                text=c.get("text", "")
            ))

        return comments



    async def get_post_reactions(self, request: PostReactionsRequest, reaction_limit: int) -> List[PostReaction]:
        """
        Fetch reactions for a LinkedIn post.
        
        Args:
            request (PostReactionsRequest): Request object containing:
                - post_url (str): LinkedIn post URL
            reaction_limit (int): Maximum number of reactions to fetch
            
        Returns:
            List[PostReaction]: List of formatted reactions
            
        Example:
            >>> request = PostReactionsRequest(post_url="https://www.linkedin.com/posts/some-post-url")
            >>> reactions = await fetcher.get_post_reactions(request, 20)
            >>> print(f"Retrieved {len(reactions)} reactions")
        """
        if not request.post_url:
            return []

        all_reactions: List[PostReaction] = []
        page = 1

        while len(all_reactions) < reaction_limit:
            payload = {"url": request.post_url, "page": page}
            response = await self.api_client.make_post_request("/get-post-reactions", payload)

            if not response.get("success", False):
                logger.error(f"Error fetching reactions: {response.get('message')}")
                return []

            raw_items = response.get("data", {}).get("items", [])
            if not raw_items:
                break

            for item in raw_items:
                try:
                    reaction = PostReaction(
                        fullName=item.get("fullName", ""),
                        headline=item.get("headline", ""),
                        reactionType=item.get("reactionType", ""),
                        profileUrl=item.get("profileUrl", "")
                    )
                    all_reactions.append(reaction)
                except Exception as e:
                    logger.warning(f"Skipping invalid reaction: {e}")

            if len(all_reactions) >= reaction_limit:
                break

            page += 1
            await asyncio.sleep(1.5)

        return [PostReaction(**reaction.model_dump()) for reaction in all_reactions[:reaction_limit]]

    async def get_profile_posts(
        self,
        request: PostsRequest
    ) -> List[ProfilePost]:
        """
        Fetch posts for a LinkedIn user profile.
        
        Args:
            request (PostsRequest): Request object containing:
                - username (str): LinkedIn profile username
                - post_limit (Optional[int]): Maximum number of posts to fetch
                - post_comments (str): "yes" or "no" to include comments
                - post_reactions (str): "yes" or "no" to include reactions
                - comment_limit (Optional[int]): Maximum number of comments per post
                - reaction_limit (Optional[int]): Maximum number of reactions per post
        
        Returns:
            List[ProfilePost]: List of profile posts with their details, comments, and reactions if requested
            
        Raises:
            ValueError: If username is not provided or response format is unexpected
            
        Example:
            >>> request = PostsRequest(username="john-doe", post_limit=5, post_comments="yes", post_reactions="yes")
            >>> posts = await fetcher.get_profile_posts(request)
            >>> print(f"Retrieved {len(posts)} posts")
        """
        if not request.username:
            return {"error": "Username is required"}

        post_limit = request.post_limit or rapid_api_settings.DEFAULT_POST_LIMIT
        comment_limit = request.comment_limit or rapid_api_settings.DEFAULT_COMMENT_LIMIT
        reaction_limit = request.reaction_limit or rapid_api_settings.DEFAULT_REACTION_LIMIT

        all_posts = []
        start = 0
        pagination_token = None

        while len(all_posts) < post_limit:
            endpoint = f"/get-profile-posts?username={request.username}&start={start}"
            if pagination_token:
                endpoint += f"&paginationToken={pagination_token}"

            response = await self.api_client.make_get_request(endpoint)

            if "message" in response and not response.get("success", False):
                logger.error(f"Error fetching posts: {response.get('message')}")
                return {"error": response["message"]}

            posts = response.get("data", [])
            all_posts.extend(posts)

            if len(all_posts) >= post_limit:
                break

            pagination_token = response.get("paginationToken")
            if not pagination_token:
                break

            start += rapid_api_settings.BATCH_SIZE

        structured_posts: List[ProfilePost] = []

        for post in all_posts[:post_limit]:
            if not isinstance(post, dict):
                continue

            post_url = post.get("postUrl")
            share_url = post.get("shareUrl")
            urn =  extract_urn_from_url(post_url)

            # Fetch comments
            comments = []
            if request.post_comments.lower() == "yes" and urn:
                try:
                    comment_response = await self.get_profile_post_comments(
                        ProfilePostCommentsRequest(post_urn=urn),
                        comment_limit
                    )
                    comments = comment_response or []
                except Exception as e:
                    logger.error(f"Unexpected error in get_profile_post_comments: {e}")
                    comments = []

            # Fetch reactions
            reactions = []
            if request.post_reactions.lower() == "yes" and post_url:
                try:
                    reaction_objs = await self.get_post_reactions(
                        PostReactionsRequest(post_url=share_url),
                        reaction_limit
                    )
                    reactions = [r.model_dump() for r in reaction_objs]  
                except Exception as e:
                    logger.error(f"Error in get_profile_post_reactions: {e}")
                    reactions = []

            structured_post = ProfilePost(
                text=post.get("text"),
                shareUrl=share_url,
                postUrl=post_url,
                totalreactions=post.get("totalReactionCount"),
                totalcomments=post.get("commentsCount"),
                media=post.get("image") or post.get("resharedPost", {}).get("image"),
                original_post_text=post.get("resharedPost", {}).get("text", "No original post text available"),
                video=post.get("video") or [],
                comments=comments,
                reactions=reactions
            )

            structured_posts.append(structured_post)

        return structured_posts


    async def extract_post_details_from_url(self, request: PostDetailsRequest) -> List[PostDetailsResponse]:
        """
        Extract detailed information for a LinkedIn post from its URL.
        
        Args:
            request (PostDetailsRequest): Request object containing:
                - post_url (str): LinkedIn post URL
                
        Returns:
            List[PostDetailsResponse]: List of post detail objects
            
        Example:
            >>> request = PostDetailsRequest(post_url="https://www.linkedin.com/posts/some-post-url")
            >>> details = await fetcher.extract_post_details_from_url(request)
            >>> print(f"Retrieved details for {len(details)} posts")
        """
        # Format endpoint
        endpoint = f"/get-post?url={request.post_url}"
        try:
            response = await self.api_client.make_get_request(endpoint)

            if not response.get("success", False) or "data" not in response:
                logger.error(f"API error: {response.get('message', 'Unknown error')}")
                return []

            raw_data = response["data"]
            posts: List[PostDetailsResponse] = []

            for item in raw_data:
                try:
                    posts.append(PostDetailsResponse(**item))
                except Exception as e:
                    logger.warning(f"Failed to parse post data: {e}")

            return posts

        except Exception as e:
            logger.error(f"Error in extract_post_details_from_url: {str(e)}")
            return []

    async def get_profile_post_comments(
        self,
        request: ProfilePostCommentsRequest,
        limit: Optional[int] = None
    ) -> List[PostComment]:
        """
        Get comments for a LinkedIn profile post.
        
        Args:
            request (ProfilePostCommentsRequest): Request object containing:
                - post_urn (str): The URN identifier of the LinkedIn post
            limit (Optional[int]): Maximum number of comments to fetch
            
        Returns:
            List[PostComment]: List of parsed comment models
            
        Example:
            >>> request = ProfilePostCommentsRequest(post_urn="urn:li:activity:1234567890")
            >>> comments = await fetcher.get_profile_post_comments(request, 10)
            >>> print(f"Retrieved {len(comments)} comments")
        """
        limit = limit or rapid_api_settings.DEFAULT_COMMENT_LIMIT
        endpoint = f"/get-profile-posts-comments?urn={request.post_urn}"

        try:
            response = await self.api_client.make_get_request(endpoint)

            if isinstance(response, dict) and "error" in response:
                logger.error(f"Error fetching post comments: {response['error']}")
                return []

            raw_comments = []
            data = response.get("data")

            #  Handle both dict and list responses
            if isinstance(data, dict):
                raw_comments = data.get("comments", [])
            elif isinstance(data, list):
                raw_comments = data
            else:
                logger.warning("Unexpected data format in comment response")
                return []

            parsed_comments: List[PostComment] = []
            for comment_item in raw_comments[:limit]:
                try:
                    parsed_comments.append(PostComment(**comment_item))
                except Exception as e:
                    logger.warning(f"Comment parse error: {e}")

            return parsed_comments

        except Exception as e:
            logger.error(f"Unexpected error in get_profile_post_comments: {e}")
            return []
        
    async def get_user_likes_with_details(
        self, 
        request: PostsRequest
    ) -> List[LikeItem]:
        """
        Fetch posts that a LinkedIn user has liked, with detailed information.
        
        Args:
            request (PostsRequest): Request object containing:
                - username (str): LinkedIn profile username
                - post_limit (Optional[int]): Maximum number of liked posts to fetch
                - post_comments (str): "yes" or "no" to include comments for each liked post
                - post_reactions (str): "yes" or "no" to include reactions for each liked post
                - comment_limit (Optional[int]): Maximum number of comments per post
                - reaction_limit (Optional[int]): Maximum number of reactions per post
        
        Returns:
            List[LikeItem]: List of liked posts with detailed information
            
        Example:
            >>> request = PostsRequest(username="john-doe", post_limit=5, post_comments="yes", post_reactions="yes")
            >>> likes = await fetcher.get_user_likes_with_details(request)
            >>> print(f"Retrieved {len(likes)} liked posts")
        """
        post_limit = request.post_limit or rapid_api_settings.DEFAULT_POST_LIMIT
        comment_limit = request.comment_limit or rapid_api_settings.DEFAULT_COMMENT_LIMIT
        reaction_limit = request.reaction_limit or rapid_api_settings.DEFAULT_REACTION_LIMIT

        all_likes = []
        start = 0
        pagination_token = None

        while len(all_likes) < post_limit:
            endpoint = f"/get-profile-likes?username={request.username}&start={start}"
            if pagination_token:
                endpoint += f"&paginationToken={pagination_token}"

            response = await self.api_client.make_get_request(endpoint)

            likes_data = response.get("data", {})
            items = likes_data.get("items", [])
            if not items:
                break

            for like in items:
                activity = LikeActivity(
                    urn=like.get("activity", {}).get("urn"),
                    username=like.get("activity", {}).get("username"),
                    postUrl=like.get("postUrl")
                )
                owner_data = like.get("owner", {}) or {}
                owner = LikeOwner(
                     urn=owner_data.get("urn"),
                    username=owner_data.get("username"),
                    firstName=owner_data.get("firstName"),
                    lastName=owner_data.get("lastName"),
                    profileUrl=owner_data.get("profileUrl"),
                    fullName=owner_data.get("fullName"),
                    headline=owner_data.get("headline"),
                    profilePicture=owner_data.get("profilePicture"),
                    linkedinUrl=owner_data.get("linkedinUrl"),
                )

                reactions = []
                if request.post_reactions == "yes":
                    reactions = await self.get_post_reactions(
                        PostReactionsRequest(post_url=like.get("postUrl", "")),
                        reaction_limit
                    )
                    reactions = [PostReaction(**r.model_dump()) for r in reactions]

                comments = []
                if request.post_comments == "yes":
                    urn = extract_urn_from_url(like.get("postUrl", ""))
                    if urn:
                        comments = await self.get_profile_post_comments(
                            ProfilePostCommentsRequest(post_urn=urn),
                            comment_limit
                        )

                like_item = LikeItem(
                    activity=activity,
                    likedAt=like.get("likedAt"),
                    text=like.get("text", ""),
                    owner=owner,
                    postUrl=like.get("postUrl", ""),
                    reactions=reactions,
                    comments=comments
                )
                all_likes.append(like_item)

            if len(all_likes) >= post_limit:
                break

            pagination_token = likes_data.get("paginationToken")
            if not pagination_token:
                break

            start += rapid_api_settings.BATCH_SIZE

        return all_likes[:post_limit]



