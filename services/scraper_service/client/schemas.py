from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Any
from typing import Union


# === 1. Person Profile ===

class ProfileRequest(BaseModel):
    username: str

class Image(BaseModel):
    url: str
    width: int
    height: int

class Date(BaseModel):
    year: int
    month: int
    day: int

class Education(BaseModel):
    start: Date
    end: Date
    fieldOfStudy: str
    degree: str
    grade: str
    schoolName: str
    description: str
    activities: str
    url: str
    schoolId: str
    logo: List[Image]

class Position(BaseModel):
    companyId: int
    companyName: str
    companyUsername: str
    companyURL: str
    companyLogo: Optional[str]
    companyIndustry: str
    companyStaffCountRange: str
    title: str
    multiLocaleTitle: Optional[Dict[str, str]]
    multiLocaleCompanyName: Optional[Dict[str, str]]
    location: str
    description: str
    employmentType: str
    start: Date
    end: Date

class Skill(BaseModel):
    name: str
    passedSkillAssessment: bool
    endorsementsCount: Optional[int] = 0 

class Geo(BaseModel):
    country: str
    city: str
    full: str
    countryCode: str

class Locale(BaseModel):
    country: str
    language: str

class ProfileResponse(BaseModel):
    id: int
    urn: str
    username: str
    firstName: str
    lastName: str
    isTopVoice: Optional[bool] = False  # <-- fix here
    isCreator: Optional[bool] = False 
    isPremium: bool
    profilePicture: Optional[str]
    backgroundImage: Optional[List[Image]]
    summary: str
    headline: str
    geo: Geo
    educations: List[Education]
    position: List[Position]
    fullPositions: Optional[List[Position]]
    skills: List[Skill]
    projects: Dict[str, Any]
    supportedLocales: List[Locale]
    multiLocaleFirstName: Dict[str, str]
    multiLocaleLastName: Dict[str, str]
    multiLocaleHeadline: Dict[str, str]




# === 2. Company Profile ===


class CompanyRequest(BaseModel):
    username: str

class Location(BaseModel):
    geographicArea: str
    country: str
    city: str
    line1: str
    postalCode: str | None = None
    headquarter: bool | None = None

class CallToActionMessage(BaseModel):
    textDirection: Optional[str] = ""
    text: Optional[str] = ""
    
class CallToAction(BaseModel):
    type: Optional[str] = None  # instead of callToActionType
    visible: Optional[bool] = None
    callToActionMessage: Optional[CallToActionMessage] = None
    url: Optional[str] = None

class MoneyRaised(BaseModel):
    currencyCode: str
    amount: str

class LeadInvestor(BaseModel):
    name: str
    investorCrunchbaseUrl: str


class AnnouncedOn(BaseModel):
    month: int
    day: int
    year: int


class LastFundingRound(BaseModel):
    investorsCrunchbaseUrl: str
    leadInvestors: list[LeadInvestor]
    fundingRoundCrunchbaseUrl: str
    fundingType: str
    moneyRaised: MoneyRaised
    numOtherInvestors: int
    announcedOn: AnnouncedOn

class FundingData(BaseModel):
    updatedAt: str
    updatedDate: str
    numFundingRounds: int
    lastFundingRound: LastFundingRound

class CompanyData(BaseModel):
    id: str
    name: str
    universalName: str
    linkedinUrl: str
    tagline: str
    description: str
    type: str
    phone: str
    Images: dict[str, str]
    isClaimable: bool
    backgroundCoverImages: list[Image]
    logos: list[Image]
    staffCount: int
    headquarter: Optional[Location] = None
    locations: Optional[list[Location]] = None
    industries: list[str]
    specialities: list[str]
    website: str
    founded: Union[str, Dict[str, Any], None] = None
    callToAction: CallToAction
    followerCount: int
    staffCountRange: str
    crunchbaseUrl: str
    fundingData: Optional[FundingData] = None


class CompanyResponse(BaseModel):
    success: bool
    message: str
    data: CompanyData



# === 3. Post Created by User ===


class PostAuthor(BaseModel):
    id: int
    firstName: str
    lastName: str
    headline: str
    username: str
    url: str
    profilePictures: Optional[dict]  # Contains `urn` and maybe more nested image objects in future


class PostArticle(BaseModel):
    title: str
    subtitle: str
    link: str


class Mention(BaseModel):
    firstName: str
    lastName: str
    urn: str
    publicIdentifier: str

class CompanyMention(BaseModel):
    id: int
    name: str
    publicIdentifier: str
    url: str

class PostDetailsRequest(BaseModel):
    post_url: str   

class PostDetailsResponse(BaseModel):
    isBrandPartnership: bool
    text: str
    totalReactionCount: int
    likeCount: int
    appreciationCount: int
    empathyCount: int
    InterestCount: int
    praiseCount: int
    commentsCount: int
    repostsCount: int
    postUrl: str
    shareUrl: str
    postedAt: str
    postedDate: str
    postedDateTimestamp: int
    urn: str
    author: PostAuthor
    article: Optional[PostArticle] = None
    mentions: Optional[List[Mention]] = []
    companyMentions: Optional[List[CompanyMention]] = []

class PostReaction(BaseModel):
    fullName: Optional[str] = ""
    headline: Optional[str] = ""
    reactionType: Optional[str] = ""  # e.g., "LIKE", "PRAISE", etc.
    profileUrl: Optional[str] = "" 

class Company(BaseModel):
    name: str
    url: str
    urn: str
class CompanyPostAuthor(BaseModel):
    name: str
    url: str
    urn: str

class CompanyPostArticle(BaseModel):
    title: Optional[str] = ""

class CompanyPostComment(BaseModel):
    name: str
    linkedinUrl: str
    title: str
    text: str
class CompanyPostVideo(BaseModel):
    url: str
    poster: Optional[str]
    duration: Optional[int]


class CompanyPost(BaseModel):
    text: str
    totalReactionCount: int
    likeCount: int
    appreciationCount: int
    empathyCount: int
    InterestCount: int
    praiseCount: int
    commentsCount: int
    repostsCount: int
    postUrl: str
    postedAt: str
    urn: str
    author: Optional[CompanyPostAuthor]
    article: Optional[CompanyPostArticle] = None
    video: Optional[List[CompanyPostVideo]] = None
    company: Optional[Company] = None

class CompanyPostResponse(BaseModel):
    text: str
    totalReactionCount: int
    likeCount: int
    appreciationCount: int
    empathyCount: int
    InterestCount: int
    praiseCount: int
    commentsCount: int
    repostsCount: int
    postUrl: str
    postedAt: str
    urn: str
    author: Optional[CompanyPostAuthor]
    article: Optional[CompanyPostArticle] = None
    video: Optional[List[CompanyPostVideo]] = None
    company: Optional[Company] = None
    comments: Optional[List[CompanyPostComment]] = []
    reactions: Optional[List[PostReaction]] = [] 


class Comment(BaseModel):
    id: Optional[str]
    text: Optional[str]
    author: Optional[str]
    timestamp: Optional[int]

class Reaction(BaseModel):
    type: str
    count: int

class PostsRequest(BaseModel):
    username: str
    post_reactions: str = "no"  # "yes"/"no"
    post_comments: str = "no"   # "yes"/"no"
    post_limit: Optional[int] = None
    comment_limit: Optional[int] = None
    reaction_limit: Optional[int] = None
    media_flag: str = "no"

class CompanyPostCommentsRequest(BaseModel):
    post_urn: str


class PostReactionsRequest(BaseModel):
    post_url: str

class ProfilePostCommentsRequest(BaseModel):
    post_urn: str



class PostCommentAuthor(BaseModel):
    name: str
    urn: str
    id: str
    username: str
    linkedinUrl: str
    title: str

class PostComment(BaseModel):
    isPinned: bool
    isEdited: bool
    threadUrn: str
    createdAt: int
    createdAtString: str
    permalink: str
    text: str
    author: PostCommentAuthor

class ProfilePost(BaseModel):
    text: Optional[str]
    shareUrl: Optional[str]
    postUrl: Optional[str]
    totalreactions: Optional[int]
    totalcomments: Optional[int]
    media: Optional[Union[str, dict, list]]  # can be image URL, dict of images, or list of videos
    original_post_text: Optional[str]
    video: Optional[List[dict]]
    comments: Optional[List[Union[Comment, PostComment]]] = []
    reactions: Optional[List[PostReaction]] = []

class ProfilePostsResponse(BaseModel):
    posts: List[ProfilePost]
    paginationToken: Optional[str] = None


class ProfilePicture(BaseModel):
    width: int
    height: int
    url: str


class PostReaction(BaseModel):
    fullName: str
    headline: str
    reactionType: str
    profileUrl: str



# class PostReactionsData(BaseModel):
#     currentPage: int
#     items: List[PostReactionItem]
#     total: int
#     totalPages: int


# class ProfilePostReactionsResponse(BaseModel):
#     success: bool
#     message: str
#     data: PostReactionsData


class LinkedInPostComment(BaseModel):
    name: Optional[str]
    linkedin_url: Optional[str]
    title: Optional[str]
    text: Optional[str]


class LinkedInPostReaction(BaseModel):
    full_name: Optional[str]
    profile_url: Optional[str]
    headline: Optional[str]
    reaction_type: Optional[str]


class LinkedInPostMedia(BaseModel):
    url: str
    width: Optional[int]
    height: Optional[int]


class LinkedInPostVideo(BaseModel):
    url: str
    poster: Optional[str]
    duration: Optional[int]


class LinkedInPost(BaseModel):
    post_id: int
    text: str
    original_post_text: Optional[str]
    post_url: str
    share_url: Optional[str]
    total_reactions: Optional[int]
    total_comments: Optional[int]
    comments: List[LinkedInPostComment] = []
    media: List[LinkedInPostMedia] = []
    video: List[LinkedInPostVideo] = []
    reactions: List[LinkedInPostReaction] = []


# === 4. Post on which user commented ===

class ActivityCommentor(BaseModel):
    name: Optional[str]
    linkedin_url: Optional[str]
    title: Optional[str]
    text: Optional[str]


class ActivityReactor(BaseModel):
    full_name: Optional[str]
    profile_url: Optional[str]
    headline: Optional[str]
    reaction_type: Optional[str]


class ActivityMedia(BaseModel):
    url: Optional[str]
    width: Optional[int]
    height: Optional[int]


class ActivityVideo(BaseModel):
    url: Optional[str]
    poster: Optional[str]
    duration: Optional[int]


class ActivityCommentedPost(BaseModel):
    id: int
    username: str
    first_name: Optional[str]
    last_name: Optional[str]
    headline: Optional[str]
    profile_url: Optional[str]
    post_text: str
    highlighted_comment: Optional[str]
    post_url: str
    total_reactions: Optional[int]
    like_count: Optional[int]
    appreciation_count: Optional[int]
    empathy_count: Optional[int]
    praise_count: Optional[int]
    funny_count: Optional[int]
    comments_count: Optional[int]
    reposts_count: Optional[int]
    created_at: Optional[datetime]
    commentors: List[ActivityCommentor] = []
    reactors: List[ActivityReactor] = []
    media: List[ActivityMedia] = []
    videos: List[ActivityVideo] = []


# === 5. Post on which user reacted ===

class ActivityReactedPost(BaseModel):
    id: int
    job_id: Optional[int]
    username: str
    action: Optional[str]
    post_text: str
    post_url: str
    first_name: Optional[str]
    last_name: Optional[str]
    profile_url: Optional[str]
    headline: Optional[str]
    like_count: Optional[int]
    comments_count: Optional[int]
    total_reactions: Optional[int]
    empathy_count: Optional[int]
    created_at: Optional[datetime]
    commentors: List[ActivityCommentor] = []
    reactors: List[ActivityReactor] = []

# === 6. Likes on User Posts ===

class LikeActivity(BaseModel):
    urn: Optional[str]
    activityType: Optional[str] = None
    id: Optional[int] = None

class LikeOwner(BaseModel):
    urn: Optional[str]
    username: Optional[str] = None
    firstName: Optional[str]
    lastName: Optional[str]
    profileUrl: Optional[str] = None
    fullName: Optional[str]
    headline: Optional[str] = None
    profilePicture: Optional[Union[str, List[Image]]] = None
    linkedinUrl: Optional[str] = None

class LikeItem(BaseModel):
    activity: Optional[LikeActivity] = None
    likedAt: Optional[str] = None
    text: Optional[str] = ""
    owner: Optional[LikeOwner] = None
    postUrl: Optional[str] = None
    reactions: Optional[List[PostReaction]] = []
    comments: Optional[List[Union[Comment, PostComment]]] = []

class LikesResponse(BaseModel):
    items: List[LikeItem]
    paginationToken: Optional[str] = None


class HighlightedComment(BaseModel):
    text: str
    totalReactionCount: Optional[int] = 0
    likeCount: Optional[int] = 0
    empathyCount: Optional[int] = 0

class HighlightedCommentActivityCount(BaseModel):
    text: Optional[str]
    totalReactionCount: Optional[int]
    likeCount: Optional[int]
    empathyCount: Optional[int]
    appreciationCount: Optional[int]
    InterestCount: Optional[int]
    praiseCount: Optional[int]
    funnyCount: Optional[int]
    commentsCount: Optional[int]
    repostsCount: Optional[int]
    postUrl: Optional[str]
    postedAt: Optional[str]
    postedDate: Optional[str]
    commentedDate: Optional[str]
    urn: Optional[str]
    commentUrl: Optional[str]
    author: Optional[Dict[str, Any]]  # You can replace this with a model later
    image: Optional[List[Dict[str, Any]]]
    company: Optional[Dict[str, Any]] = {}
    article: Optional[Dict[str, Any]] = {}

# CommentImages


class CommentImage(BaseModel):
    url: str


class CommentAuthorCompany(BaseModel):
    name: str
    url: str
    urn: str


class GetProfileCommentResponse(BaseModel):
    highlightedComments: Optional[List[HighlightedComment]] = []
    highlightedCommentsActivityCounts: Optional[List[HighlightedCommentActivityCount]] = []

    text: Optional[str]
    totalReactionCount: Optional[int]
    likeCount: Optional[int]
    appreciationCount: Optional[int] = 0
    empathyCount: Optional[int] = 0
    InterestCount: Optional[int] = 0
    praiseCount: Optional[int] = 0
    funnyCount: Optional[int] = 0
    commentsCount: Optional[int]
    repostsCount: Optional[int]

    postUrl: Optional[str] #identifier for the post
    commentUrl: Optional[str]

    postedAt: Optional[str]
    postedDate: Optional[str]
    commentedDate: Optional[str]

    urn: Optional[str]

    image: Optional[List[CommentImage]] = []
    company: Optional[CommentAuthorCompany] = None

# === 7. Activity & Credit Estimation Request ===

class ActivityRequest(BaseModel):
    """
    Configuration schema for a scraping job, used for credit estimation.
    """
    type: str  # "company" or "person"
    username: str 
    profile_info: str = "no" # "yes" or "no"
    post_scrap: str = "no"   # "yes" or "no"
    activity_comments: str = "no" # "yes" or "no" - Scrape posts user commented on?
    activity_reactions: str = "no" # "yes" or "no" - Scrape posts user reacted to?

    # Limits applicable when post_scrap, activity_comments, or activity_reactions is "yes"
    post_limit: Optional[int] = 10 # Default limit if scraping posts/activity
    post_comments: str = "no" # "yes" or "no" - Fetch comments for scraped posts?
    comment_limit: Optional[int] = 10 
    post_reactions: str = "no" # "yes" or "no" - Fetch reactions for scraped posts?
    reaction_limit: Optional[int] = 10