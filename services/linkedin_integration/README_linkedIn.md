# Oauth 

flows are not setup but can be easily setup via: https://github.com/linkedin-developers/linkedin-api-python-client/blob/main/examples/oauth_member_auth_redirect.py

# Access Code without app's Oauth flow

1. Generate access code for a user via: https://www.linkedin.com/developers/tools/oauth/token-generator
2. put access code in .env and import via `libs.global_config.settings` as shown in `linkedin_client_test.py` and use with linkedin_client

# .env structure

```bash
DATABASE_URL=""
PYTHONPATH=./libs:./services
LINKEDIN_CLIENT_ID=""
LINKEDIN_CLIENT_SECRET=""
LINKEDIN_ACCESS_TOKEN_XXXX=
```


# API TESTING OUTPUT: `linkedin_client_test_demo_2.py`
## PUT DATA CACHE in `.../kiwiq-backend/data/` directory for linked client to pick it up

```bash
=== LinkedIn Organization API Testing ===


================================================================================
CALLING: get_member_organization_roles()
ARGS: {}
KWARGS: {}
================================================================================

================================================================================
CALLING: get_member_profile()
ARGS: {}
KWARGS: {}
================================================================================

Authenticated Member Profile:
ID: NxwL-IvR2n
Name: Founder A
Headline: Startup, Ex-ML Lead at Google (Search Ranking, Gemini, Knowledge Graphs)

Organizations and Roles for Authenticated Member:

================================================================================
CALLING: get_organization_details()
ARGS: ["urn:li:organization:105029503"]
KWARGS: {}
================================================================================
urn:li:organization:105029503
1. Organization:  KiwiQ AI 
(urn:li:organization:105029503) | Role: ADMINISTRATOR | State: APPROVED | User URN: urn:li:person:NxwL-IvR2n

================================================================================
CALLING: get_organization_details()
ARGS: ["urn:li:organization:102995539"]
KWARGS: {}
================================================================================
urn:li:organization:102995539
2. Organization:  Stealth Mode AI Startup 
(urn:li:organization:102995539) | Role: ADMINISTRATOR | State: APPROVED | User URN: urn:li:person:NxwL-IvR2n

Selected Organization URN: urn:li:organization:105029503
User URN (from role): urn:li:person:NxwL-IvR2n

Fetching Organization Posts...

================================================================================
CALLING: get_posts()
ARGS: {}
KWARGS: {
  "account_id": "urn:li:organization:105029503",
  "limit": 50
}
================================================================================
Found 21 organization posts:
  1. Post ID: urn:li:ugcPost:7304968765245411329
     Created: 2025-03-11 02:27:53.818000
     Content: 𝐊𝐞𝐞𝐩𝐢𝐧𝐠 𝐔𝐩 𝐖𝐢𝐭𝐡 𝐀𝐈: 𝐌𝐚𝐫𝐤𝐞𝐭𝐢𝐧𝐠 𝐄𝐝𝐢𝐭𝐢𝐨𝐧 \(𝐰𝐞𝐞𝐤 𝐨𝐟 𝐌𝐚𝐫 𝟑\)

 Quick snapshot of seven of the top AI news...
     Media URLs: {"title": "Keeping Up With AI: Marketing Edition (Week of March 3)", "id": "urn:li:document:D4E1FAQFgEjynYlolKw"}

  2. Post ID: urn:li:ugcPost:7302440618364915712
     Created: 2025-03-04 03:01:56.384000
     Content: 𝐊𝐞𝐞𝐩𝐢𝐧𝐠 𝐔𝐩 𝐖𝐢𝐭𝐡 𝐀𝐈: 𝐌𝐚𝐫𝐤𝐞𝐭𝐢𝐧𝐠 𝐄𝐝𝐢𝐭𝐢𝐨𝐧 \(𝐰𝐞𝐞𝐤 𝐨𝐟 𝐅𝐞𝐛 24\)
Quick snapshot of seven of the top AI news ...
     Media URLs: {"title": "Keeping Up With AI: Marketing Edition (Week of Feb 24)", "id": "urn:li:document:D561FAQF9MphPfNppXg"}

  3. Post ID: urn:li:share:7300938514823618560
     Created: 2025-02-27 23:33:06.940000
     Content: A great shot of Friday marketer brain juice by @[Alex Lieberman](urn:li:person:35919zhXDb).
     Media URLs: []

  4. Post ID: urn:li:ugcPost:7299881440480022528
     Created: 2025-02-25 01:32:41.004000
     Content: 𝐊𝐞𝐞𝐩𝐢𝐧𝐠 𝐔𝐩 𝐖𝐢𝐭𝐡 𝐀𝐈: 𝐌𝐚𝐫𝐤𝐞𝐭𝐢𝐧𝐠 𝐄𝐝𝐢𝐭𝐢𝐨𝐧 \(𝐰𝐞𝐞𝐤 𝐨𝐟 𝐅𝐞𝐛 𝟏𝟕\)
Quick snapshot of seven of the top AI news ...
     Media URLs: {"title": "Keeping Up With AI: Marketing Edition (Week of Feb 17)", "id": "urn:li:document:D4E1FAQGjR-JvrbtUtQ"}

  5. Post ID: urn:li:share:7298782983010889729
     Created: 2025-02-22 00:47:48.104000
     Content: Looks like something is cooking 🥘
     Media URLs: []

  6. Post ID: urn:li:share:7295545337803354112
     Created: 2025-02-13 02:22:33.442000
     Content: Interesting take on Super Bowl marketing from a FinTech perspective by one of our Experts in Residen...
     Media URLs: []

  7. Post ID: urn:li:share:7294797456192520192
     Created: 2025-02-11 00:50:44.536000
     Content: 💡 {hashtag|\#|AI} companies and products were all over the {hashtag|\#|Superbowl} yesterday.  Sponso...
     Media URLs: []

  8. Post ID: urn:li:share:7289735722838700032
     Created: 2025-01-28 01:37:13.390000
     Content: 🪩  @[DeepSeek AI](urn:li:organization:106112505) Just Made AI Way More Interesting for Marketers

Yo...
     Media URLs: []

  9. Post ID: urn:li:ugcPost:7287556299427393536
     Created: 2025-01-22 01:16:58.319000
     Content: It’s 2027. Picture this vision for your day as a Marketer:

- Cross-channel data analyzed before you...
     Media URLs: {"id": "urn:li:video:D5605AQEQGCXb973O1w"}

  10. Post ID: urn:li:share:7285727238841409540
     Created: 2025-01-17 00:08:56.131000
     Content: ✨ 2025: The Year of Truly Personal Marketing? ✨

The world of marketing is evolving, and your custom...
     Media URLs: []

  11. Post ID: urn:li:ugcPost:7284625189345075200
     Created: 2025-01-13 23:09:47.678000
     Content: Google's latest white paper on AI Agents provides a glimpse into how marketing teams will work in th...
     Media URLs: {"title": "Google_Agents", "id": "urn:li:document:D4D1FAQEJnjjvcnFnqQ"}

  12. Post ID: urn:li:ugcPost:7283559591445983232
     Created: 2025-01-11 00:35:28.818000
     Content: Every marketing leader knows the pain of disconnected data and delayed insights.
That's why we're re...
     Media URLs: {"title": "Building Smarter Marketing Tools", "id": "urn:li:document:D561FAQF0ln_e02Kv_g"}

  13. Post ID: urn:li:share:7282819272135876608
     Created: 2025-01-08 23:33:43.136000
     Content: Excited to welcome another founding Expert in Residence to KiwiQ AI! 🎉

@[Khyati Srivastava ✨](urn:l...
     Media URLs: {"altText": "", "id": "urn:li:image:D5622AQHYjgX353Wr7w"}

  14. Post ID: urn:li:ugcPost:7281070837758140418
     Created: 2025-01-04 03:46:03.780000
     Content: 🔍 Are static customer journey maps holding you back?

@[Samuel Awezec](urn:li:person:CmTAhf0ujs), on...
     Media URLs: {"id": "urn:li:video:D5605AQETEuVSQF1Tlg"}

  15. Post ID: urn:li:ugcPost:7278175484159434752
     Created: 2024-12-27 04:00:57.779000
     Content: As 2024 draws to a close, we’ve been reflecting at @[KiwiQ AI](urn:li:organization:105029503) on wha...
     Media URLs: {"title": "Sam talking about what's holding back AI for marketers", "id": "urn:li:video:D5605AQH2QBSuN9OMAA"}

  16. Post ID: urn:li:share:7276930818634104832
     Created: 2024-12-23 17:35:06.279000
     Content: We are pumped to share that the amazing @[Samuel Awezec](urn:li:person:CmTAhf0ujs) is joining KiwiQ ...
     Media URLs: {"altText": "", "id": "urn:li:image:D5622AQFEwwOET57ItA"}

  17. Post ID: urn:li:share:7275323692954361858
     Created: 2024-12-19 07:08:57.538000
     Content: Fantastic perspectives from @[Andy Sack](urn:li:person:NkekylVsjb) and @[Adam Brotman](urn:li:person...
     Media URLs: []

  18. Post ID: urn:li:ugcPost:7273399602572070914
     Created: 2024-12-13 23:43:18.753000
     Content: 🎯 "Get AI to Work With You, Not Just For You"

@[Ryan Oistacher](urn:li:person:Ww-h\_\_kIES) \(one o...
     Media URLs: {"id": "urn:li:video:D5605AQHfjVBehzRjSg"}

  19. Post ID: urn:li:ugcPost:7271991110535667712
     Created: 2024-12-10 02:26:28.144000
     Content: 🎯 "I need middle managers for my AI army"

A fascinating observation from @[Katie Perry](urn:li:pers...
     Media URLs: {"id": "urn:li:video:D5605AQFq-lzifLSblg"}

  20. Post ID: urn:li:share:7270867137626288130
     Created: 2024-12-07 00:00:12.033000
     Content: Excited to announce another founding Expert in Residence with KiwiQ AI. 

Ryan Oistacher is a true A...
     Media URLs: {"altText": "", "id": "urn:li:image:D5622AQEa30SpEtMgmA"}

  21. Post ID: urn:li:share:7267601367039373313
     Created: 2024-11-27 23:43:11.748000
     Content: 🚀  Excited to launch our Founding Experts in Residence at KiwiQ AI! 

We know Marketers \(like every...
     Media URLs: {"altText": "", "id": "urn:li:image:D5622AQHQerMDxI9bdw"}

> /path/to/project/services/linkedin_integration/linkedin_client_test_demo_2.py(340)test_org_selection()
    339         # 5. Fetch posts for the user
--> 340         print("\nFetching User Posts...")
    341         try:

ipdb> c

Fetching User Posts...

================================================================================
CALLING: get_posts()
ARGS: {}
KWARGS: {
  "account_id": "urn:li:person:NxwL-IvR2n",
  "limit": 50
}
================================================================================
{'elements': None}
Found 0 user posts:
> /path/to/project/services/linkedin_integration/linkedin_client_test_demo_2.py(378)test_org_selection()
    377         # 6. Fetch social actions for user posts
--> 378         print("\nFetching Social Actions for User Posts...")
    379         try:

ipdb> c

Fetching Social Actions for User Posts...
No user posts available to fetch social actions.
> /path/to/project/services/linkedin_integration/linkedin_client_test_demo_2.py(422)test_org_selection()
    421         # 7. Fetch social actions for organization posts
--> 422         print("\nFetching Social Actions for Organization Posts...")
    423         try:

ipdb> c


Testing get_post_social_actions for single organization post...

================================================================================
CALLING: get_post_social_actions()
ARGS: ["urn:li:ugcPost:7304968765245411329"]
KWARGS: {}
================================================================================
{
    "likesSummary": {
        "selectedLikes": [
            "urn:li:like:(urn:li:person:dCgSj6leY8,urn:li:ugcPost:7304968765245411329)",
            "urn:li:like:(urn:li:person:WLj-GBAcUB,urn:li:ugcPost:7304968765245411329)",
            "urn:li:like:(urn:li:person:qUvas1UvE2,urn:li:ugcPost:7304968765245411329)",
            "urn:li:like:(urn:li:company:105029503,urn:li:ugcPost:7304968765245411329)"
        ],
        "aggregatedTotalLikes": 4,
        "likedByCurrentUser": false,
        "totalLikes": 4
    },
    "commentsSummary": {
        "selectedComments": [],
        "totalFirstLevelComments": 0,
        "commentsState": "OPEN",
        "aggregatedTotalComments": 0
    },
    "target": "urn:li:ugcPost:7304968765245411329"
}

Social actions for organization post:
  Post: 𝐊𝐞𝐞𝐩𝐢𝐧𝐠 𝐔𝐩 𝐖𝐢𝐭𝐡 𝐀𝐈: 𝐌𝐚𝐫𝐤𝐞𝐭𝐢𝐧𝐠 𝐄𝐝𝐢𝐭𝐢𝐨𝐧 \(𝐰𝐞𝐞𝐤 𝐨𝐟 𝐌𝐚...
    ID: urn:li:ugcPost:7304968765245411329
    Likes: 4
    Comments: 0


================================================================================

Fetching Social Actions for Organization Posts...

================================================================================
CALLING: batch_get_post_social_actions()
ARGS: ["urn:li:ugcPost:7304968765245411329", "urn:li:ugcPost:7302440618364915712", "urn:li:share:7300938514823618560", "urn:li:ugcPost:7299881440480022528", "urn:li:share:7298782983010889729", "urn:li:share:7295545337803354112", "urn:li:share:7294797456192520192", "urn:li:share:7289735722838700032", "urn:li:ugcPost:7287556299427393536", "urn:li:share:7285727238841409540", "urn:li:ugcPost:7284625189345075200", "urn:li:ugcPost:7283559591445983232", "urn:li:share:7282819272135876608", "urn:li:ugcPost:7281070837758140418", "urn:li:ugcPost:7278175484159434752", "urn:li:share:7276930818634104832", "urn:li:share:7275323692954361858", "urn:li:ugcPost:7273399602572070914", "urn:li:ugcPost:7271991110535667712", "urn:li:share:7270867137626288130", "urn:li:share:7267601367039373313"]
KWARGS: {}
================================================================================
Retrieved social actions for 21 organization posts:
  Post: 🎯 "I need middle managers for my AI army"

A fasci...
    ID: urn:li:ugcPost:7271991110535667712
    Likes: 52
    Comments: 7

  Post: 💡 {hashtag|\#|AI} companies and products were all ...
    ID: urn:li:share:7294797456192520192
    Likes: 3
    Comments: 0

  Post: Google's latest white paper on AI Agents provides ...
    ID: urn:li:ugcPost:7284625189345075200
    Likes: 27
    Comments: 4

  Post: ✨ 2025: The Year of Truly Personal Marketing? ✨

T...
    ID: urn:li:share:7285727238841409540
    Likes: 16
    Comments: 2

  Post: Excited to announce another founding Expert in Res...
    ID: urn:li:share:7270867137626288130
    Likes: 4
    Comments: 0

  Post: N/A
    ID: urn:li:share:7298782983010889729
    Likes: 4
    Comments: 0

  Post: 🚀  Excited to launch our Founding Experts in Resid...
    ID: urn:li:share:7267601367039373313
    Likes: 5
    Comments: 1

  Post: A great shot of Friday marketer brain juice by @[A...
    ID: urn:li:share:7300938514823618560
    Likes: 3
    Comments: 0

  Post: 🪩  @[DeepSeek AI](urn:li:organization:106112505) J...
    ID: urn:li:share:7289735722838700032
    Likes: 17
    Comments: 0

  Post: 🎯 "Get AI to Work With You, Not Just For You"

@[R...
    ID: urn:li:ugcPost:7273399602572070914
    Likes: 19
    Comments: 2

  Post: 𝐊𝐞𝐞𝐩𝐢𝐧𝐠 𝐔𝐩 𝐖𝐢𝐭𝐡 𝐀𝐈: 𝐌𝐚𝐫𝐤𝐞𝐭𝐢𝐧𝐠 𝐄𝐝𝐢𝐭𝐢𝐨𝐧 \(𝐰𝐞𝐞𝐤 𝐨𝐟 𝐅𝐞...
    ID: urn:li:ugcPost:7302440618364915712
    Likes: 10
    Comments: 1

  Post: Excited to welcome another founding Expert in Resi...
    ID: urn:li:share:7282819272135876608
    Likes: 40
    Comments: 3

  Post: It’s 2027. Picture this vision for your day as a M...
    ID: urn:li:ugcPost:7287556299427393536
    Likes: 30
    Comments: 2

  Post: As 2024 draws to a close, we’ve been reflecting at...
    ID: urn:li:ugcPost:7278175484159434752
    Likes: 23
    Comments: 2

  Post: We are pumped to share that the amazing @[Samuel A...
    ID: urn:li:share:7276930818634104832
    Likes: 66
    Comments: 0

  Post: 𝐊𝐞𝐞𝐩𝐢𝐧𝐠 𝐔𝐩 𝐖𝐢𝐭𝐡 𝐀𝐈: 𝐌𝐚𝐫𝐤𝐞𝐭𝐢𝐧𝐠 𝐄𝐝𝐢𝐭𝐢𝐨𝐧 \(𝐰𝐞𝐞𝐤 𝐨𝐟 𝐌𝐚...
    ID: urn:li:ugcPost:7304968765245411329
    Likes: 4
    Comments: 0

  Post: Every marketing leader knows the pain of disconnec...
    ID: urn:li:ugcPost:7283559591445983232
    Likes: 15
    Comments: 0

  Post: 🔍 Are static customer journey maps holding you bac...
    ID: urn:li:ugcPost:7281070837758140418
    Likes: 18
    Comments: 1

  Post: 𝐊𝐞𝐞𝐩𝐢𝐧𝐠 𝐔𝐩 𝐖𝐢𝐭𝐡 𝐀𝐈: 𝐌𝐚𝐫𝐤𝐞𝐭𝐢𝐧𝐠 𝐄𝐝𝐢𝐭𝐢𝐨𝐧 \(𝐰𝐞𝐞𝐤 𝐨𝐟 𝐅𝐞...
    ID: urn:li:ugcPost:7299881440480022528
    Likes: 15
    Comments: 1

  Post: Interesting take on Super Bowl marketing from a Fi...
    ID: urn:li:share:7295545337803354112
    Likes: 6
    Comments: 0

  Post: Fantastic perspectives from @[Andy Sack](urn:li:pe...
    ID: urn:li:share:7275323692954361858
    Likes: 6
    Comments: 0

> /path/to/project/services/linkedin_integration/linkedin_client_test_demo_2.py(468)test_org_selection()
    467         # a. Test lifetime share statistics.
--> 468         print("\nFetching Lifetime Share Statistics...")
    469         try:

ipdb> c

Fetching Lifetime Share Statistics...

================================================================================
CALLING: get_organization_lifetime_share_statistics()
ARGS: ["urn:li:organization:105029503"]
KWARGS: {}
================================================================================
Lifetime Share Statistics:
elements=[ShareStatistics(organizational_entity='urn:li:organization:105029503', share=None, ugc_post=None, time_range=None, total_share_statistics=ShareStatisticsData(click_count=2534, comment_count=28, engagement=0.14953176411035182, impression_count=19755, like_count=383, share_count=9, unique_impressions_count=5734, comment_mentions_count=None, share_mentions_count=None))]
> /path/to/project/services/linkedin_integration/linkedin_client_test_demo_2.py(493)test_org_selection()
    492         # b. Test current follower count.
--> 493         print("\nFetching Current Follower Count...")
    494         try:

ipdb> c

Fetching Current Follower Count...

================================================================================
CALLING: get_organization_follower_count()
ARGS: ["urn:li:organization:105029503"]
KWARGS: {}
================================================================================
{
  "organizational_entity": "urn:li:organization:105029503",
  "association_totals": {
    "organic": 6,
    "paid": 0,
    "total": 6
  },
  "seniority_totals": {
    "organic": 131,
    "paid": 0,
    "total": 131
  },
  "industry_totals": {
    "organic": 143,
    "paid": 0,
    "total": 143
  },
  "function_totals": {
    "organic": 125,
    "paid": 0,
    "total": 125
  },
  "staff_count_range_totals": {
    "organic": 121,
    "paid": 0,
    "total": 121
  },
  "geo_country_totals": {
    "organic": 143,
    "paid": 0,
    "total": 143
  },
  "geo_totals": {
    "organic": 134,
    "paid": 0,
    "total": 134
  }
}
Current Follower Count:
None
> /path/to/project/services/linkedin_integration/linkedin_client_test_demo_2.py(517)test_org_selection()
    516         # c. Test time-bound share statistics (using last 7 days as an example).
--> 517         print("\nFetching Time-bound Share Statistics (Last 7 Days)...")
    518         end_date = datetime.now(timezone.utc)

ipdb> c

Fetching Time-bound Share Statistics (Last 7 Days)...

================================================================================
CALLING: get_organization_timebound_share_statistics()
ARGS: ["urn:li:organization:105029503"]
KWARGS: {
  "start_date": "2025-03-09T12:49:25.846558+00:00",
  "end_date": "2025-03-16T12:49:25.846558+00:00",
  "granularity": "DAY"
}
================================================================================
Time-bound Share Statistics (Last 7 Days):
elements=[ShareStatistics(organizational_entity='urn:li:organization:105029503', share=None, ugc_post=None, time_range={'start': 1741478400000, 'end': 1741564800000}, total_share_statistics=ShareStatisticsData(click_count=3, comment_count=0, engagement=0.09090909090909091, impression_count=33, like_count=0, share_count=0, unique_impressions_count=12, comment_mentions_count=None, share_mentions_count=None)), ShareStatistics(organizational_entity='urn:li:organization:105029503', share=None, ugc_post=None, time_range={'start': 1741564800000, 'end': 1741651200000}, total_share_statistics=ShareStatisticsData(click_count=9, comment_count=0, engagement=0.16901408450704225, impression_count=71, like_count=2, share_count=1, unique_impressions_count=24, comment_mentions_count=None, share_mentions_count=None)), ShareStatistics(organizational_entity='urn:li:organization:105029503', share=None, ugc_post=None, time_range={'start': 1741651200000, 'end': 1741737600000}, total_share_statistics=ShareStatisticsData(click_count=21, comment_count=0, engagement=0.6216216216216216, impression_count=37, like_count=2, share_count=0, unique_impressions_count=19, comment_mentions_count=None, share_mentions_count=None)), ShareStatistics(organizational_entity='urn:li:organization:105029503', share=None, ugc_post=None, time_range={'start': 1741737600000, 'end': 1741824000000}, total_share_statistics=ShareStatisticsData(click_count=0, comment_count=0, engagement=0.0, impression_count=41, like_count=0, share_count=0, unique_impressions_count=12, comment_mentions_count=None, share_mentions_count=None)), ShareStatistics(organizational_entity='urn:li:organization:105029503', share=None, ugc_post=None, time_range={'start': 1741824000000, 'end': 1741910400000}, total_share_statistics=ShareStatisticsData(click_count=0, comment_count=0, engagement=0.0, impression_count=19, like_count=0, share_count=0, unique_impressions_count=10, comment_mentions_count=None, share_mentions_count=None)), ShareStatistics(organizational_entity='urn:li:organization:105029503', share=None, ugc_post=None, time_range={'start': 1741910400000, 'end': 1741996800000}, total_share_statistics=ShareStatisticsData(click_count=1, comment_count=0, engagement=0.02, impression_count=100, like_count=1, share_count=0, unique_impressions_count=16, comment_mentions_count=None, share_mentions_count=None)), ShareStatistics(organizational_entity='urn:li:organization:105029503', share=None, ugc_post=None, time_range={'start': 1741996800000, 'end': 1742083200000}, total_share_statistics=ShareStatisticsData(click_count=0, comment_count=0, engagement=0.0, impression_count=28, like_count=0, share_count=0, unique_impressions_count=7, comment_mentions_count=None, share_mentions_count=None))]
```
