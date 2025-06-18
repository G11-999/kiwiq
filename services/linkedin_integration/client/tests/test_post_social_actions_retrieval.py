#!/usr/bin/env python3
"""
Interactive test for LinkedInClient organization selection and subsequent testing.

This script performs the following:
1. Fetches all organization roles assigned to the authenticated member using 
   the get_member_organization_roles() method. The response is of type OrganizationRolesResponse
   and includes a list of OrganizationRole objects.
2. Prints the list of organizations along with the assigned role details (role, state) and the user URN.
3. Prompts the user to choose an organization (by its number).
4. Extracts the selected organization URN and the user's URN (roleAssignee) to be used in all subsequent API calls.
5. Uses the selected URN values to call methods such as:
   - get_organization_lifetime_share_statistics
   - get_organization_follower_count
   - get_organization_timebound_share_statistics (using last 7 days as an example)
6. Prints the responses to the console.

STREAMLINED VERSION - Consolidated repetitive code and optimized ipdb breakpoint placement:
- Moved ipdb breakpoints to after function responses and print statements for better verification
- Created helper function test_post_retrieval_and_metrics() to reduce code duplication
- Consolidated organization post metrics testing
- Removed redundant social actions testing code
- Maintained comprehensive test coverage while improving readability

Usage:
    $ python tests/test_linkedin_client_org_selection.py
"""

import asyncio
from datetime import datetime, timedelta, timezone
import json
from typing import Any
from urllib.parse import quote

# Import our LinkedInClient and required models
from linkedin_integration.client.linkedin_client import LinkedInClient
from kiwi_app.settings import settings

async def test_post_retrieval_and_metrics(linkedin_client: LinkedInClient, post_id: str) -> None:
    """Helper function to test post retrieval and metrics for a given post."""
    try:
        # Test getting post by URN with author view context
        ########################################################################
        print("\n" + "="*80)
        print("CALLING: get_post_by_urn()")
        print(f"ARGS: {json.dumps([post_id])}")
        print(f"KWARGS: {json.dumps({'view_context': 'AUTHOR'}, indent=2)}")
        print("="*80)
        post_by_urn = await linkedin_client.get_post_by_urn(
            post_urn=post_id,
            view_context="AUTHOR"
        )
        if post_by_urn:
            print(f"Retrieved post by URN: {json.dumps(post_by_urn, indent=2)}")
        else:
            print("No post found by URN")
        
        import ipdb; ipdb.set_trace()
        
        # Test getting social metadata (reaction and comment summaries)
        ########################################################################
        print("\n" + "="*80)
        print("CALLING: batch_get_social_metadata()")
        print(f"ARGS: {json.dumps([post_id])}")
        print("KWARGS: {}")
        print("="*80)
        social_metadatas = await linkedin_client.batch_get_social_metadata(
            entity_urns=[post_id],
            # sort="REVERSE_CHRONOLOGICAL"
        )
        print(f"Reactions: {json.dumps({k: v.model_dump() for k, v in social_metadatas.items()}, indent=2)}")

        import ipdb; ipdb.set_trace()
        
        # Test getting social actions for the post
        ########################################################################
        print("\n" + "="*80)
        print("CALLING: get_post_social_actions()")
        print(f"ARGS: {json.dumps([post_id])}")
        print("KWARGS: {}")
        print("="*80)
        social_actions = await linkedin_client.get_post_social_actions(
            post_id=post_id
        )
        print(f"Retrieved social actions: {json.dumps(social_actions.model_dump() if social_actions else None, indent=2)}")

        import ipdb; ipdb.set_trace()

        # Test getting comments for the post
        ########################################################################
        print("\n" + "="*80)
        print("CALLING: get_post_comments()")
        print(f"ARGS: {json.dumps([post_id])}")
        print("KWARGS: {}")
        print("="*80)
        comments = await linkedin_client.get_post_comments(
            post_urn=post_id
        )
        print(f"Retrieved {len(comments)} comments:")
        print(json.dumps([comment.model_dump() for comment in comments], indent=2))

        import ipdb; ipdb.set_trace()

        # Test getting likes for the post
        ########################################################################
        print("\n" + "="*80)
        print("CALLING: get_post_likes()")
        print(f"ARGS: {json.dumps([post_id])}")
        print("KWARGS: {}")
        print("="*80)
        likes = await linkedin_client.get_post_likes(
            post_urn=post_id
        )
        print(f"Retrieved {len(likes)} likes:")
        print(json.dumps([like.model_dump() for like in likes], indent=2))

        import ipdb; ipdb.set_trace()

        # Test getting reactions via fetched likes for the post
        ########################################################################
        reactions = await linkedin_client.batch_get_reactions(
            actor_entity_pairs=[(like.actor, like.object) for like in likes]
        )
        print(f"Retrieved {len(reactions)} reactions:")

        print(json.dumps([reaction.model_dump() for reaction in reactions], indent=2))
        
        
    except Exception as e:
        print(f"Error in post retrieval and metrics test: {str(e)}")
        import traceback
        traceback.print_exc()

async def test_getting_post_reactions(linkedin_client: LinkedInClient) -> None:
    """
    Fetches all organization roles for the authenticated member, prompts the user to select one,
    and then tests several organization-level API methods using the selected organization URN.

    Args:
        linkedin_client: An instance of LinkedInClient properly configured with credentials.
    """

    # post_id = "urn:li:activity:7288408229108203520"
    # print(quote(post_id, safe=""))
    # return

    try:
        # 1. Fetch organization roles for the authenticated member.
        ########################################################################
        ######################### GET MEMBER ORGANIZATIONS AND ROLES ###########
        print("\n" + "="*80)
        print("CALLING: get_member_organization_roles()")
        print("ARGS: {}")
        print("KWARGS: {}")
        print("="*80)
        roles_response = await linkedin_client.get_member_organization_roles()
        ########################################################################
        roles = roles_response.elements


        success, member_profile = await linkedin_client.get_member_info_including_email()
        print(f"Member profile: {member_profile.model_dump_json(indent=2)}")

        if not roles:
            print("No organization roles found for the authenticated member.")
            return
            
        # Fetch member profile details
        ########################################################################
        ######################### GET MEMBER PROFILE #########################
        print("\n" + "="*80)
        print("CALLING: get_member_profile()")
        print("ARGS: {}")
        print("KWARGS: {}")
        print("="*80)
        member_profile = await linkedin_client.get_member_profile()
        ########################################################################

        print(f"\nAuthenticated Member Profile:")
        print(f"ID: {member_profile.id}")
        print(f"Name: {member_profile.localized_first_name} {member_profile.localized_last_name}")
        print(f"Headline: {member_profile.localized_headline}")

        # 2. Print out the details of each organization role.
        print("\nOrganizations and Roles for Authenticated Member:")
        for idx, role in enumerate(roles, start=1):
            # Each role contains the user URN in role_assignee and the org URN in organization.
            # Fetch organization details
            ########################################################################
            ######################### FOR EACH ORG, GET ORG DETAILS ###########
            print("\n" + "="*80)
            print("CALLING: get_organization_details()")
            print(f"ARGS: {json.dumps([role.organization])}")
            print("KWARGS: {}")
            print("="*80)
            print(role.organization)
            org_details = await linkedin_client.get_organization_details(role.organization)
            ########################################################################
            org_name = org_details.display_name
            
            print(f"{idx}. Organization:  {org_name} \n({role.organization}) | "
                  f"Role: {role.role} | State: {role.state} | "
                  f"User URN: {role.role_assignee}")
        # 3. Prompt user to choose one organization by number.
        selection = "1"  # input("\nEnter the number of the organization you want to test: ").strip()
        import time
        time.sleep(5)
        try:
            selection_int = int(selection)
            if selection_int < 1 or selection_int > len(roles):
                raise ValueError("Selection out of range.")
        except ValueError as ve:
            print(f"Invalid selection: {ve}. Exiting organization tests.")
            return

        selected_role = roles[selection_int - 1]
        organization_urn = selected_role.organization
        user_urn = selected_role.role_assignee

        # urn:li:organization:105029503  (KIWIQ AI)
        # urn:li:organization:102995539  (Stealth AI)
        organization_urn = "urn:li:organization:102995539"  # overwrite with stealth AI startup URN!  

        print(f"\nSelected Organization URN: {organization_urn}")
        print(f"User URN (from role): {user_urn}")

        import ipdb; ipdb.set_trace()

        """
        https://learn.microsoft.com/en-us/linkedin/marketing/community-management/members/post-statistics?view=li-lms-2025-06&tabs=curl

        
        # REACTIONS (Works with Curl! --> but doesn't work with REst Li client)
        curl -X GET 'https://api.linkedin.com/rest/reactions/(entity:urn%3Ali%3Aactivity%3A7313213674821730304)?q=entity&sort=(value:REVERSE_CHRONOLOGICAL)' \
        -H 'X-Restli-Protocol-Version: 2.0.0' \
        -H 'LinkedIn-Version: 202505' \
        -H 'Authorization: XXXXXXXX'
        
        
        # POST ANALYTICS (Doesn't work!)
        curl -X GET 'https://api.linkedin.com/rest/memberCreatorPostAnalytics?q=me&queryType=IMPRESSION' \
        -H 'X-Restli-Protocol-Version: 2.0.0' \
        -H 'LinkedIn-Version: 202505' \
        -H 'Authorization: Bearer XXXXXXXX'
        
        
        curl -X GET 'https://api.linkedin.com/rest/memberCreatorPostAnalytics?q=me&dateRange=(start:(year:2024,month:5,day:4),end:(year:2024,month:5,day:6))&queryType=IMPRESSION' \
        -H 'X-Restli-Protocol-Version: 2.0.0' \
        -H 'LinkedIn-Version: 202506' \
        -H 'Authorization: Bearer XXXXXXX'
        
        curl -X GET 'https://api.linkedin.com/rest/memberCreatorPostAnalytics?q=me&dateRange=(start:(year:2024,month:5,day:4),end:(year:2024,month:5,day:6))&aggregation=DAILY&queryType=IMPRESSION' \
        -H 'X-Restli-Protocol-Version: 2.0.0' \
        -H 'LinkedIn-Version: 202506' \
        -H 'Authorization: Bearer XXXXXXX'
        
        
        curl -X GET 'https://api.linkedin.com/rest/memberCreatorPostAnalytics?q=me&aggregation=DAILY&queryType=IMPRESSION' \
        -H 'X-Restli-Protocol-Version: 2.0.0' \
        -H 'LinkedIn-Version: 202506' \
        -H 'Authorization: Bearer XXXXXXX'
        

        
        



        curl -X GET 'https://api.linkedin.com/rest/memberCreatorPostAnalytics?q=entity&entity=(share:urn%3Ali%3Ashare%3A7340981576178024448)&dateRange=(start:(year:2024,month:5,day:4),end:(year:2024,month:5,day:6))&queryType=IMPRESSION' \
        -H 'X-Restli-Protocol-Version: 2.0.0' \
        -H 'LinkedIn-Version: 202506' \
        -H 'Authorization: Bearer XXXXXXX'
        
        curl -X GET 'https://api.linkedin.com/rest/memberCreatorPostAnalytics?q=entity&entity=(share:urn%3Ali%3Ashare%3A7340981576178024448)&dateRange=(start:(year:2024,month:5,day:4),end:(year:2024,month:5,day:6))&aggregation=DAILY&queryType=IMPRESSION' \
        -H 'X-Restli-Protocol-Version: 2.0.0' \
        -H 'LinkedIn-Version: 202506' \
        -H 'Authorization: Bearer XXXXXXX'
        
        
        curl -X GET 'https://api.linkedin.com/rest/memberCreatorPostAnalytics?q=entity&entity=(share:urn%3Ali%3Ashare%3A7340981576178024448)&aggregation=DAILY&queryType=IMPRESSION' \
        -H 'X-Restli-Protocol-Version: 2.0.0' \
        -H 'LinkedIn-Version: 202506' \
        -H 'Authorization: Bearer XXXXXXX'
        

        curl -X GET 'https://api.linkedin.com/rest/memberCreatorPostAnalytics?q=entity&entity=(share:urn%3Ali%3Ashare%3A7340981576178024448)&queryType=REACTION' \
        -H 'X-Restli-Protocol-Version: 2.0.0' \
        -H 'LinkedIn-Version: 202506' \
        -H 'Authorization: Bearer XXXXXXX'
        

        curl -X GET 'https://api.linkedin.com/rest/memberCreatorPostAnalytics?q=entity&entity=(share:urn%3Ali%3Ashare%3A7340981576178024448)&queryType=REACTION&aggregation=DAILY&dateRange=(start:(day:4,month:5,year:2024),end:(day:6,month:5,year:2024))' \
        -H 'X-Restli-Protocol-Version: 2.0.0' \
        -H 'Authorization: Bearer XXXXXXX'\
        -H 'Linkedin-Version: 202506'



        curl -X GET 'https://api.linkedin.com/rest/memberCreatorPostAnalytics?q=entity&entity=(share:urn%3Ali%3Ashare%3A7288408228378427392)&queryType=MEMBERS_REACHED' \
        -H 'X-Restli-Protocol-Version: 2.0.0' \
        -H 'LinkedIn-Version: 202506' \
        -H 'Authorization: Bearer XXXXXXX'
        
        
        Error containing internal details when using entity=(ugcPost:urn%3Ali%3Aactivity%3A7288408229108203520): {"message":"Input field validation failure, reason: ERROR ::  :: \"ugcPost\" is not a member type of union [ { \"alias\" : \"share\", \"type\" : { \"type\" : \"typeref\", \"name\" : \"ShareUrn\", \"namespace\" : \"com.linkedin.common\", \"ref\" : \"string\", \"java\" : { \"class\" : \"com.linkedin.common.urn.ShareUrn\" }, \"resourceKey\" : [ { \"entity\" : \"com.linkedin.ugc.UgcPostV2\", \"keyConfig\" : { \"keys\" : { \"shareUrn\" : { \"simpleKey\" : \"$URN\" } }, \"queryParameters\" : { \"$actor\" : \"VIEWER_URN\" } }, \"resourcePath\" : \"/ugcPostsV2/{shareUrn}\" } ], \"validate\" : { \"com.linkedin.common.validator.TypedUrnValidator\" : { \"doc\" : \"\", \"entityType\" : \"share\", \"fields\" : [ { \"doc\" : \"Generated torrent style id with 's' prefix. Maxlength is transposed from db column.\", \"javaType\" : \"String\", \"maxLength\" : 36, \"name\" : \"shareId\", \"type\" : \"string\" } ], \"maxLength\" : 49, \"name\" : \"Share\", \"namespace\" : \"li\", \"owners\" : [ \"urn:li:corpuser:aolin\", \"urn:li:corpuser:azhengxie\", \"urn:li:corpuser:caoconnor\", \"urn:li:corpuser:jko\", \"urn:li:corpuser:jnlau\", \"urn:li:corpuser:jusong\", \"urn:li:corpuser:mgoyal\", \"urn:li:corpuser:sabrooks\", \"urn:li:corpuser:sgwak\", \"urn:li:corpuser:wchen\", \"urn:li:corpuser:yepark\" ], \"owningTeam\" : \"urn:li:internalTeam:ugc\", \"resourceKey\" : [ { \"entity\" : \"com.linkedin.ugc.UgcPostV2\", \"keyConfig\" : { \"keys\" : { \"shareUrn\" : { \"simpleKey\" : \"$URN\" } }, \"queryParameters\" : { \"$actor\" : \"VIEWER_URN\" } }, \"resourcePath\" : \"/ugcPostsV2/{shareUrn}\" } ] } } } }, { \"alias\" : \"ugc\", \"type\" : { \"type\" : \"typeref\", \"name\" : \"UserGeneratedContentPostUrn\", \"namespace\" : \"com.linkedin.common\", \"doc\" : \"Uniquely identifies a LinkedIn user-generated content post.  Posts are content shared on LinkedIn that can encapsulate types such as text, articles, images, etc.\", \"ref\" : \"string\", \"java\" : { \"class\" : \"com.linkedin.common.urn.UserGeneratedContentPostUrn\" }, \"resourceKey\" : [ { \"entity\" : \"com.linkedin.ugc.UgcPostV2\", \"keyConfig\" : { \"keys\" : { \"id\" : { \"simpleKey\" : \"$URN\" } }, \"queryParameters\" : { \"$actor\" : \"VIEWER_URN\" } }, \"resourcePath\" : \"/ugcPostsV2/{id}\" } ], \"validate\" : { \"com.linkedin.common.validator.TypedUrnValidator\" : { \"doc\" : \"Uniquely identifies a LinkedIn user-generated content post.  Posts are content shared on LinkedIn that can encapsulate types such as text, articles, images, etc.\", \"entityType\" : \"ugcPost\", \"fields\" : [ { \"doc\" : \"The unique id for a UserGeneratedContentPost stored in UGC (User Generated Content) backend.\", \"javaType\" : \"Long\", \"name\" : \"userGeneratedContentId\", \"type\" : \"long\" } ], \"maxLength\" : 35, \"name\" : \"UserGeneratedContentPost\", \"namespace\" : \"li\", \"owners\" : [ \"urn:li:corpuser:aolin\", \"urn:li:corpuser:azhengxie\", \"urn:li:corpuser:caoconnor\", \"urn:li:corpuser:jko\", \"urn:li:corpuser:jnlau\", \"urn:li:corpuser:jusong\", \"urn:li:corpuser:mgoyal\", \"urn:li:corpuser:sabrooks\", \"urn:li:corpuser:sgwak\", \"urn:li:corpuser:wchen\", \"urn:li:corpuser:yepark\" ], \"owningTeam\" : \"urn:li:internalTeam:ugc\", \"resourceKey\" : [ { \"entity\" : \"com.linkedin.ugc.UgcPostV2\", \"keyConfig\" : { \"keys\" : { \"id\" : { \"simpleKey\" : \"$URN\" } }, \"queryParameters\" : { \"$actor\" : \"VIEWER_URN\" } }, \"resourcePath\" : \"/ugcPostsV2/{id}\" } ] } } } } ]\n","status":400}%



        ###############################################################################
        # CRITICAL: convert UGC activity URN to share URN for use in analytics APIs!
        ###############################################################################

        curl -X GET 'https://api.linkedin.com/v2/activities?ids=urn:li:activity:7288408229108203520' \
        -H 'Authorization: Bearer XXXXXXX'

        curl -X GET 'https://api.linkedin.com/v2/activities?ids=urn:li:activity:7288408229108203520&ids=urn:li:activity:7311079094459252736' \
        -H 'Authorization: Bearer XXXXXXX'

        """

        org_post_id = "urn:li:activity:7313213674821730304"  # KIWIQ Post
        other_user_post_id = "urn:li:activity:7311079094459252736"  # (test post)
        other_post_id_share_urn = "urn:li:share:7311079092169187328"  # (test post)      urn%3Ali%3Ashare%3A7311079092169187328
        user_post_id = "urn:li:activity:7288408229108203520"  # (test post with reshare)     urn%3Ali%3Aactivity%3A7288408229108203520
        user_post_id_share_urn = "urn:li:share:7288408228378427392"  # (test post with reshare)      urn%3Ali%3Ashare%3A7288408228378427392
        org_share_post_id = "urn:li:share:7328113604275142657"  # KIWIQ Post      urn%3Ali%3Ashare%3A7328113604275142657

        print(quote(user_post_id_share_urn, safe=""))
        return


        ###############################################################################
        ################################# DEBUG #######################################
        ###############################################################################

        # posts = await linkedin_client.get_posts(
        #     account_id=organization_urn,
        #     limit=100,
        #     # days=100
        # )
        # print(f"Retrieved {len(posts)} posts:")
        # print(json.dumps([post for post in posts], indent=2))
        # return

        # import ipdb; ipdb.set_trace()

        # for view_context in ["AUTHOR", "READER"]:
        #     for post_id in [org_post_id, other_user_post_id, user_post_id, org_share_post_id]:
        #         post_by_urn = await linkedin_client.get_post_by_urn(
        #             post_urn=post_id,
        #             view_context=view_context
        #         )
        #         print(f"\n\nView context: {view_context}")
        #         print(f"Post ID: {post_id}")
        #         print(f"Post: {json.dumps(post_by_urn, indent=2)}\n\n")
        #         import ipdb; ipdb.set_trace()
        #         print(f"Retrieved post by URN: {json.dumps(post_by_urn, indent=2)}")

        # print(f"Retrieved {len(posts)} posts:")
        # print(json.dumps([post.model_dump() for post in posts], indent=2))

        
        # TODO: also test for org and user!
        # actor_urn = organization_urn

        # success, post_id, post_entity = await linkedin_client.create_post(
        #     account_urn=actor_urn,
        #     content="Writing test post, ignore 2.",
        #     feed_distribution="MAIN_FEED"
        # )

        # print(f"Created post: {success}")
        # print(f"Post ID: {post_id}")
        # print(f"Post entity: {json.dumps(post_entity, indent=2)}")

        # import ipdb; ipdb.set_trace()

        # success, post_entity = await linkedin_client.update_post(
        #     post_urn=post_id,
        #     commentary="Writing test update, ignore."
        # )

        # print(f"Updated post: {success}")
        # print(f"Post entity: {json.dumps(post_entity, indent=2)}")

        # import ipdb; ipdb.set_trace()

        # success, post_id, post_entity = await linkedin_client.create_reshare(
        #     account_urn=actor_urn,
        #     reshare_commentary="Writing test reshare, ignore 1.",
        #     post_urn=post_id,
        #     feed_distribution="MAIN_FEED"
        # )

        # print(f"Created post: {success}")
        # print(f"Post ID: {post_id}")
        # print(f"Post entity: {json.dumps(post_entity, indent=2)}")

        # import ipdb; ipdb.set_trace()


        # success, comment = await linkedin_client.create_comment(
        #     target_urn=post_id,
        #     actor_urn=actor_urn,
        #     message_text="Writing test comment, ignore."
        # )

        # import ipdb; ipdb.set_trace()



        # success, updated_comment = await linkedin_client.update_comment(
        #     target_urn=post_id,
        #     comment_id=comment.id,
        #     message_text="Writing test update on comment, ignore.",
        #     actor_urn=actor_urn,
        # )

        # print(f"Updated comment: {success}")
        # print(f"Comment ID: {post_id}")
        # print(f"Comment entity: {json.dumps(post_entity, indent=2)}")

        # import ipdb; ipdb.set_trace()


        # return



        ###############################################################################
        ###############################################################################


        # for post_id in [org_post_id, other_user_post_id, user_post_id, org_share_post_id]:
        #     await test_post_retrieval_and_metrics(linkedin_client, post_id)
        #     print("\n\n\n\n\n\n" + "=END="*80 + "\n\n\n\n\n\n")
        #     import ipdb; ipdb.set_trace()

        # import ipdb; ipdb.set_trace()

        
        user_post_content = "Planning for a productive day? Follow along on the comment thread"
        comment_text = "Ever heard about Dopamine loading? Skewing your dopamine hits to gradually increase throughout the day and not engaging in high dopamine activities before late evening."

        success, user_post_id, post_entity = await linkedin_client.create_post(
            account_urn=user_urn,
            content=user_post_content,
            feed_distribution="MAIN_FEED"
        )

        comment_success, comment_data = await linkedin_client.create_comment(
            target_urn=user_post_id,
            actor_urn=user_urn,
            message_text=comment_text
        )

        like_success, like_data = await linkedin_client.create_like(
            target_urn=user_post_id,
            actor_urn=user_urn,
            object_urn=user_post_id
        )

        like_success, like_data = await linkedin_client.create_like(
            target_urn=comment_data.comment_urn,
            actor_urn=user_urn,
            object_urn=user_post_id,
        )

        print(f"\n\nUser post LINK: https://www.linkedin.com/feed/update/{user_post_id}/\n\n")

        print(quote(user_post_id, safe=""))

        # await test_post_retrieval_and_metrics(linkedin_client, user_post_id)

        import ipdb; ipdb.set_trace()

        success, post_entity = await linkedin_client.delete_post(
            post_urn=user_post_id
        )
        print(f"Deleted post: {success}")



    except Exception as e:
        print(f"Error in post retrieval and metrics test: {str(e)}")
        import traceback
        traceback.print_exc()
        return

async def main() -> None:
    """
    Main entry point for the interactive organization test.

    Prompts the user for API credentials and creates a LinkedInClient instance.
    Then, it calls the test_getting_post_reactions() function.
    """
    print("=== LinkedIn Organization API Testing ===\n")
    
    # Prompt user for necessary credentials.
    client_id = settings.LINKEDIN_CLIENT_ID
    client_secret = settings.LINKEDIN_CLIENT_SECRET
    access_token = settings.LINKEDIN_ACCESS_TOKEN  # LINKEDIN_ACCESS_TOKEN  LINKEDIN_ACCESS_TOKEN
    # urn:li:person:NxwL-IvR2n
    # urn:li:person:qUvas1UvE2
    version_input = settings.LINKEDIN_API_VERSION

    # Instantiate the LinkedInClient with caching disabled for testing.
    linkedin_client = LinkedInClient(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        version=version_input,
        enable_caching=False  # Disable caching to force live API calls for testing
    )

    # Run the organization selection and subsequent tests.
    await test_getting_post_reactions(linkedin_client)

if __name__ == "__main__":
    asyncio.run(main())
