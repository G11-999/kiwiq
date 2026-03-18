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
        success, post_by_urn = await linkedin_client.get_post_by_urn(
            post_urn=post_id,
            view_context="AUTHOR"
        )
        if success and post_by_urn:
            print(f"Retrieved post by URN: {json.dumps(post_by_urn, indent=2)}")
        else:
            print("No post found by URN")
        
        # Test getting social actions for the post
        ########################################################################
        print("\n" + "="*80)
        print("CALLING: get_post_social_actions()")
        print(f"ARGS: {json.dumps([post_id])}")
        print("KWARGS: {}")
        print("="*80)
        success, social_actions = await linkedin_client.get_post_social_actions(
            post_id=post_id
        )
        print(f"Retrieved social actions: {json.dumps(social_actions.model_dump() if success and social_actions else None, indent=2)}")

        # Test getting comments for the post
        ########################################################################
        print("\n" + "="*80)
        print("CALLING: get_post_comments()")
        print(f"ARGS: {json.dumps([post_id])}")
        print("KWARGS: {}")
        print("="*80)
        success, comments = await linkedin_client.get_post_comments(
            post_urn=post_id
        )
        if success and comments:
            print(f"Retrieved {len(comments)} comments:")
            print([comment.model_dump() for comment in comments])
        else:
            print("No comments retrieved")

        # Test getting likes for the post
        ########################################################################
        print("\n" + "="*80)
        print("CALLING: get_post_likes()")
        print(f"ARGS: {json.dumps([post_id])}")
        print("KWARGS: {}")
        print("="*80)
        success, likes = await linkedin_client.get_post_likes(
            post_urn=post_id
        )
        if success and likes:
            print(f"Retrieved {len(likes)} likes:")
            print([like.model_dump() for like in likes])
        else:
            print("No likes retrieved")
        
        import ipdb; ipdb.set_trace()
        
    except Exception as e:
        print(f"Error in post retrieval and metrics test: {str(e)}")
        import traceback
        traceback.print_exc()

async def test_org_selection(linkedin_client: LinkedInClient) -> None:
    """
    Fetches all organization roles for the authenticated member, prompts the user to select one,
    and then tests several organization-level API methods using the selected organization URN.

    Args:
        linkedin_client: An instance of LinkedInClient properly configured with credentials.
    """

    print("\n" + "="*80)
    print("STARTING COMPREHENSIVE LINKEDIN API TESTS")
    print("="*80)

    user_urn = "urn:li:person:UPV9MhVHZy"  # Raina / Khyati probably!
    success, person_profile = await linkedin_client.get_person_profile(user_urn)
    if success:
        print(f"\n\n\n\nPerson profile: {person_profile.model_dump_json(indent=2)}\n\n\n\n")


    success, member_followers_count_lifetime = await linkedin_client.get_member_followers_count_lifetime()
    if success:
        print(f"\n\n\n\nMember followers count lifetime: {member_followers_count_lifetime}\n\n\n\n")
    
    start_date = datetime(2025, 4, 4)
    end_date = datetime(2025, 5, 3)
    success, member_followers_count_by_date_range = await linkedin_client.get_member_followers_count_by_date_range(start_date, end_date)
    if success:
        print(f"\n\n\n\nMember followers count by date range: {member_followers_count_by_date_range}\n\n\n\n")

    # ########################################################################
    # ########################################################################

    # comment_urn = "urn:li:comment:(activity:7298782266392989697,7298792284500746240)"
    # user_urn = "urn:li:person:UPV9MhVHZy"  # Raina / Khyati probably!
    # user_urn = "urn:li:person:NxwL-IvR2n"
    # target_urn = "urn:li:activity:7298782266392989697"
    # comment_urn = "urn:li:activity:7298782266392989697"

    # # Test creating a like on a comment
    # ########################################################################
    # print("\n" + "="*80)
    # print("CALLING: create_like()")
    # print(f"ARGS: {json.dumps([comment_urn, user_urn, target_urn])}")
    # print("KWARGS: {}")
    # print("="*80)

    # like_success, like_data = await linkedin_client.create_like(
    #     target_urn=comment_urn,
    #     actor_urn=user_urn,
    #     object_urn=target_urn
    # )

    # print(f"Like success: {like_success}")
    # print(f"Like data: {like_data}")

    # import ipdb; ipdb.set_trace()

    # delete_like_success, delete_like_data = await linkedin_client.delete_like(
    #     target_urn=comment_urn,
    #     actor_urn=user_urn
    # )

    # print(f"Delete like success: {delete_like_success}")
    # print(f"Delete like data: {delete_like_data}")

    # return
    # ########################################################################
    # ########################################################################


    # ######################################################################## 
    # # organization_urn = "urn:li:organization:102995539"  # overwrite with stealth AI startup URN!
    # organization_urn = "urn:li:person:NxwL-IvR2n"
    # user_post_id = "urn:li:activity:7298782266392989697"


    # # Test organization commenting on user post
    # org_on_user_comment_text = "Great post! - Organization engaging with user content"
    # ########################################################################  
    # ######################### ORG COMMENT ON USER POST #########################
    # print("\n" + "="*80)
    # print("CALLING: create_comment() - Org on User Post")
    # print(f"ARGS: {json.dumps([user_post_id, organization_urn, org_on_user_comment_text])}")
    # print("KWARGS: {}")
    # print("="*80)
    # org_on_user_comment_success, org_on_user_comment_data = await linkedin_client.create_comment(
    #     target_urn=user_post_id,
    #     actor_urn=organization_urn,
    #     message_text=org_on_user_comment_text
    # )
    # ########################################################################
    
    # if org_on_user_comment_success and org_on_user_comment_data:
    #     org_on_user_comment_id = org_on_user_comment_data.id
    #     print(f"Successfully created organization comment on user post with ID: {org_on_user_comment_id}")
    #     print(f"Organization comment data: {json.dumps(org_on_user_comment_data.model_dump(), indent=2)}") 
    #     import ipdb; ipdb.set_trace()
        
    #     # Test updating organization comment on user post
    #     updated_org_on_user_comment = "Updated organization comment on user post!"
    #     ########################################################################
    #     ######################### UPDATE ORG COMMENT ON USER POST #########################
    #     print("\n" + "="*80)
    #     print("CALLING: update_comment() - Org Comment on User Post")
    #     print(f"ARGS: {json.dumps([user_post_id, org_on_user_comment_id, updated_org_on_user_comment])}")
    #     print(f"KWARGS: {json.dumps({'actor_urn': organization_urn}, indent=2)}")
    #     print("="*80)
    #     org_on_user_update_success, org_on_user_updated_comment = await linkedin_client.update_comment(
    #         target_urn=user_post_id,
    #         comment_id=org_on_user_comment_id,
    #         message_text=updated_org_on_user_comment,
    #         actor_urn=organization_urn
    #     )
    #     ########################################################################
        
    #     if org_on_user_update_success:
    #         print(f"Successfully updated organization comment on user post {org_on_user_comment_id}")
    #         print(f"Updated org comment: {json.dumps(org_on_user_updated_comment, indent=2) if org_on_user_updated_comment else 'None'}")
    #     import ipdb; ipdb.set_trace()
        
    #     # Test deleting organization comment on user post
    #     ########################################################################
    #     ######################### DELETE ORG COMMENT ON USER POST #########################
    #     print("\n" + "="*80)
    #     print("CALLING: delete_comment() - Org Comment on User Post")
    #     print(f"ARGS: {json.dumps([user_post_id, org_on_user_comment_id])}")
    #     print(f"KWARGS: {json.dumps({'actor_urn': organization_urn}, indent=2)}")
    #     print("="*80)
    #     org_on_user_delete_success, org_on_user_delete_data = await linkedin_client.delete_comment(
    #         target_urn=user_post_id,
    #         comment_id=org_on_user_comment_id,
    #         actor_urn=organization_urn
    #     )
    # ######################################################################## 

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
        success, roles_response = await linkedin_client.get_member_organization_roles()
        if not success or not roles_response:
            print("Failed to fetch organization roles.")
            return
        ########################################################################
        roles = roles_response.elements

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
        success, member_profile = await linkedin_client.get_member_profile()
        if not success or not member_profile:
            print("Failed to fetch member profile.")
            return
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
            success, org_details = await linkedin_client.get_organization_details(role.organization)
            if not success or not org_details:
                print("Failed to fetch organization details.")
                return
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
        organization_urn = "urn:li:organization:105029503"  # overwrite with stealth AI startup URN!  

        print(f"\nSelected Organization URN: {organization_urn}")
        print(f"User URN (from role): {user_urn}")

        import ipdb; ipdb.set_trace()

        # Extract organization ID from URN
        organization_id = organization_urn.split(":")[-1]
        
        # Extract user ID from URN
        user_id = user_urn.split(":")[-1]

        ########################################################################
        # Test creating a post for the organization
        print("\nTesting Organization Post Creation...")
        try:
            # Create a test post for the organization
            org_post_content = f"This is a test post created now 5."
            ########################################################################
            ######################### CREATE POST FOR ORG #########################
            print("\n" + "="*80)
            print("CALLING: create_post()")
            print("ARGS: {}")
            print(f"KWARGS: {json.dumps({
                'account_urn': organization_urn,
                'content': org_post_content,
                'feed_distribution': 'MAIN_FEED'
            }, indent=2)}")
            print("="*80)
            org_success, org_post_id, org_post_entity = await linkedin_client.create_post(
                account_urn=organization_urn,
                content=org_post_content,
                feed_distribution="MAIN_FEED"
            )

            ########################################################################
            if org_success:
                print(f"Successfully created organization post with ID: {org_post_id}")
                print(f"Organization post entity: {json.dumps(org_post_entity, indent=2) if org_post_entity else 'None'}")
            else:
                print("Failed to create organization post")
                return

            import ipdb; ipdb.set_trace()
            
            # Test updating organization post
            print("\nTesting Organization Post Update...")
            updated_org_content = "This post was updated wrt to the content from previous post -- check it out!"
            ########################################################################
            ######################### UPDATE ORG POST #########################
            print("\n" + "="*80)
            print("CALLING: update_post()")
            print(f"ARGS: {json.dumps([org_post_id])}")
            print(f"KWARGS: {json.dumps({'commentary': updated_org_content}, indent=2)}")
            print("="*80)
            org_update_success, org_updated_entity = await linkedin_client.update_post(
                post_urn=org_post_id,
                commentary=updated_org_content
            )

            ########################################################################
            
            if org_update_success:
                print(f"Successfully updated organization post {org_post_id}")
                print(f"Updated org post data: {json.dumps(org_updated_entity, indent=2) if org_updated_entity else 'None'}")
            else:
                print(f"Failed to update organization post {org_post_id}")
            
            import ipdb; ipdb.set_trace()


            # Test creating a like on a comment
            ########################################################################
            print("\n" + "="*80)
            print("CALLING: create_like()")
            print(f"ARGS: {json.dumps([org_post_id, user_urn, org_post_id])}")
            print("KWARGS: {}")
            print("="*80)

            like_success, like_data = await linkedin_client.create_like(
                target_urn=org_post_id,
                actor_urn=user_urn,
                object_urn=org_post_id
            )

            print(f"Like success: {like_success}")
            print(f"Like data: {like_data}")

            import ipdb; ipdb.set_trace()

            delete_like_success, delete_like_data = await linkedin_client.delete_like(
                target_urn=org_post_id,
                actor_urn=user_urn
            )

            print(f"Delete like success: {delete_like_success}")
            print(f"Delete like data: {delete_like_data}")



            # Debug point after organization post creation
            # import ipdb; ipdb.set_trace()
            
            # Test comment operations on organization post
            print("\nTesting Comment Operations on Organization Post...")
            
            # Test user commenting on organization post
            user_comment_text = "Great update to the post!"
            ########################################################################
            ######################### USER COMMENT ON ORG POST #########################
            print("\n" + "="*80)
            print("CALLING: create_comment() - User on Org Post")
            print(f"ARGS: {json.dumps([org_post_id, user_urn, user_comment_text])}")
            print("KWARGS: {}")
            print("="*80)
            user_comment_success, user_comment_data = await linkedin_client.create_comment(
                target_urn=org_post_id,
                actor_urn=user_urn,
                message_text=user_comment_text
            )
            ########################################################################
            
            if user_comment_success and user_comment_data:
                user_comment_id = user_comment_data.id
                print(f"Successfully created user comment on org post with ID: {user_comment_id}")
                print(f"User comment data: {json.dumps(user_comment_data.model_dump(), indent=2)}")
                import ipdb; ipdb.set_trace()
                
                # Test updating user comment
                updated_user_comment = "Updated my comment on post!"
                ########################################################################
                ######################### UPDATE USER COMMENT #########################
                print("\n" + "="*80)
                print("CALLING: update_comment() - User Comment")
                print(f"ARGS: {json.dumps([org_post_id, user_comment_id, updated_user_comment])}")
                print("KWARGS: {}")
                print("="*80)
                user_comment_update_success, user_updated_comment = await linkedin_client.update_comment(
                    target_urn=org_post_id,
                    comment_id=user_comment_id,
                    message_text=updated_user_comment,
                    actor_urn=user_urn,
                )
                ########################################################################
                
                if user_comment_update_success:
                    print(f"Successfully updated user comment {user_comment_id}")
                    print(f"Updated user comment: {json.dumps(user_updated_comment, indent=2) if user_updated_comment else 'None'}")
                import ipdb; ipdb.set_trace()
                
                # Test organization commenting on its own post
                org_comment_text = "Thank you for engaging! - Org response"
                ########################################################################
                ######################### ORG COMMENT ON OWN POST #########################
                print("\n" + "="*80)
                print("CALLING: create_comment() - Org on Own Post")
                print(f"ARGS: {json.dumps([org_post_id, organization_urn, org_comment_text])}")
                print("KWARGS: {}")
                print("="*80)
                org_comment_success, org_comment_data = await linkedin_client.create_comment(
                    target_urn=org_post_id,
                    actor_urn=organization_urn,
                    message_text=org_comment_text
                )
                ########################################################################
                
                if org_comment_success and org_comment_data:
                    org_comment_id = org_comment_data.id
                    print(f"Successfully created organization comment with ID: {org_comment_id}")
                    print(f"Organization comment data: {json.dumps(org_comment_data.model_dump(), indent=2)}")
                    import ipdb; ipdb.set_trace()
                    
                    # Test updating organization comment
                    updated_org_comment = "Updated response comment!"
                    ########################################################################
                    ######################### UPDATE ORG COMMENT #########################
                    print("\n" + "="*80)
                    print("CALLING: update_comment() - Org Comment")
                    print(f"ARGS: {json.dumps([org_post_id, org_comment_id, updated_org_comment])}")
                    print(f"KWARGS: {json.dumps({'actor_urn': organization_urn}, indent=2)}")
                    print("="*80)
                    org_comment_update_success, org_updated_comment = await linkedin_client.update_comment(
                        target_urn=org_post_id,
                        comment_id=org_comment_id,
                        message_text=updated_org_comment,
                        actor_urn=organization_urn
                    )
                    ########################################################################
                    
                    if org_comment_update_success:
                        print(f"Successfully updated organization comment {org_comment_id}")
                        print(f"Updated org comment: {json.dumps(org_updated_comment, indent=2) if org_updated_comment else 'None'}")
                    import ipdb; ipdb.set_trace()
                    
                    # Test deleting organization comment
                    ########################################################################
                    ######################### DELETE ORG COMMENT #########################
                    print("\n" + "="*80)
                    print("CALLING: delete_comment() - Org Comment")
                    print(f"ARGS: {json.dumps([org_post_id, org_comment_id])}")
                    print(f"KWARGS: {json.dumps({'actor_urn': organization_urn}, indent=2)}")
                    print("="*80)
                    org_delete_comment_success, org_delete_comment_data = await linkedin_client.delete_comment(
                        target_urn=org_post_id,
                        comment_id=org_comment_id,
                        actor_urn=organization_urn
                    )
                    ########################################################################
                    
                    print(f"Organization comment deletion {'successful' if org_delete_comment_success else 'failed'}")
                    if org_delete_comment_data:
                        print(f"Delete org comment response: {json.dumps(org_delete_comment_data, indent=2)}")
                    import ipdb; ipdb.set_trace()
                
                # Test deleting user comment
                ########################################################################
                ######################### DELETE USER COMMENT #########################
                print("\n" + "="*80)
                print("CALLING: delete_comment() - User Comment")
                print(f"ARGS: {json.dumps([org_post_id, user_comment_id])}")
                print("KWARGS: {}")
                print("="*80)
                user_delete_comment_success, user_delete_comment_data = await linkedin_client.delete_comment(
                    target_urn=org_post_id,
                    comment_id=user_comment_id,
                    actor_urn=user_urn,
                )
                ########################################################################
                
                print(f"User comment deletion {'successful' if user_delete_comment_success else 'failed'}")
                if user_delete_comment_data:
                    print(f"Delete user comment response: {json.dumps(user_delete_comment_data, indent=2)}")
                import ipdb; ipdb.set_trace()
            


            # Test resharing organization post by user
            print("\nTesting User Resharing Organization Post...")
            user_reshare_content = "Resharing this post wrt!"
            ########################################################################
            ######################### CREATE RESHARE FOR USER #########################
            print("\n" + "="*80)
            print("CALLING: create_reshare()")
            print("ARGS: {}")
            print(f"KWARGS: {json.dumps({
                'account_urn': user_urn,
                'reshare_commentary': user_reshare_content,
                'post_urn': org_post_id,
                'feed_distribution': 'MAIN_FEED'
            }, indent=2)}")
            print("="*80)
            user_reshare_success, user_reshare_id, user_reshare_entity = await linkedin_client.create_reshare(
                account_urn=user_urn,
                reshare_commentary=user_reshare_content,
                post_urn=org_post_id,
                feed_distribution="MAIN_FEED"
            )
            ########################################################################
            if user_reshare_success:
                print(f"Successfully reshared organization post as user with ID: {user_reshare_id}")
                print(f"User reshare entity: {json.dumps(user_reshare_entity, indent=2) if user_reshare_entity else 'None'}")
            else:
                print("Failed to create user reshare")

            ###################################
            # Debug point
            import ipdb; ipdb.set_trace()
            ###################################

            # Delete the user's reshare first, then the org post
            ########################################################################
            ######################### DELETE RESHARE FOR USER #########################
            print("\nDeleting user's reshare...")
            print("\n" + "="*80)
            print("CALLING: delete_post()")
            print(f"ARGS: {json.dumps([user_reshare_id])}")
            print("KWARGS: {}")
            print("="*80)
            delete_reshare_success, delete_reshare_entity = await linkedin_client.delete_post(user_reshare_id)
            ########################################################################
            print(f"User reshare deletion {'successful' if delete_reshare_success else 'failed'}")
            if delete_reshare_entity:
                print(f"Delete reshare response: {json.dumps(delete_reshare_entity, indent=2)}")
            
            import ipdb; ipdb.set_trace()
            
            
            # Delete the test organization post
            ########################################################################
            ######################### DELETE TEST ORG POST #########################
            print("\nDeleting test organization post...")
            print("\n" + "="*80)
            print("CALLING: delete_post()")
            print(f"ARGS: {json.dumps([org_post_id])}")
            print("KWARGS: {}")
            print("="*80)
            delete_success, delete_entity = await linkedin_client.delete_post(org_post_id)
            ########################################################################
            print(f"Organization post deletion {'successful' if delete_success else 'failed'}")
            if delete_entity:
                print(f"Delete org post response: {json.dumps(delete_entity, indent=2)}")
        except Exception as e:
            print(f"Error in organization post creation/reshare/deletion test: {str(e)}")
            import traceback
            traceback.print_exc()
            return
        ########################################################################
        ###################################
        # Debug point
        # import ipdb; ipdb.set_trace()
        ###################################
        
        # Test creating a post for the user
        print("\nTesting User Post Creation...")
        try:
            # Create a test post for the user
            user_post_content = f"This is a test post created now."
            ########################################################################
            ######################### CREATE POST FOR USER #########################
            print("\n" + "="*80)
            print("CALLING: create_post()")
            print("ARGS: {}")
            print(f"KWARGS: {json.dumps({
                'account_urn': user_urn,
                'content': user_post_content,
                'feed_distribution': 'MAIN_FEED'
            }, indent=2)}")
            print("="*80)
            success, user_post_id, post_entity = await linkedin_client.create_post(
                account_urn=user_urn,
                content=user_post_content,
                feed_distribution="MAIN_FEED"
            )
            ########################################################################
            if success:
                print(f"Successfully created user post with ID: {user_post_id}")
                print(f"Post entity: {json.dumps(post_entity, indent=2) if post_entity else 'None'}")
            else:
                print("Failed to create user post")
                return

            # Test getting post data and metrics
            print("\nTesting Post Retrieval and Metrics...")
            await test_post_retrieval_and_metrics(linkedin_client, user_post_id)

            # Test comment operations on the created post
            print("\nTesting Comment Operations on Created Post...")
            try:
                # Test comment creation
                comment_text = "This is a test comment created now!"
                ########################################################################
                ######################### CREATE COMMENT ON POST #########################
                print("\n" + "="*80)
                print("CALLING: create_comment()")
                print(f"ARGS: {json.dumps([user_post_id, user_urn, comment_text])}")
                print("KWARGS: {}")
                print("="*80)
                comment_success, comment_data = await linkedin_client.create_comment(
                    target_urn=user_post_id,
                    actor_urn=user_urn,
                    message_text=comment_text
                )
                ########################################################################
                
                if comment_success and comment_data:
                    comment_id = comment_data.id
                    print(f"Successfully created comment with ID: {comment_id}")
                    print(f"Comment data: {json.dumps(comment_data.model_dump(), indent=2)}")
                    import ipdb; ipdb.set_trace()
                    
                    # Test comment update
                    updated_comment_text = "This is an updated test comment!"
                    ########################################################################
                    ######################### UPDATE COMMENT #########################
                    print("\n" + "="*80)
                    print("CALLING: update_comment()")
                    print(f"ARGS: {json.dumps([user_post_id, comment_id, updated_comment_text])}")
                    print("KWARGS: {}")
                    print("="*80)
                    update_success, updated_comment_data = await linkedin_client.update_comment(
                        target_urn=user_post_id,
                        comment_id=comment_id,
                        message_text=updated_comment_text,
                        actor_urn=user_urn,
                    )
                    ########################################################################
                    
                    if update_success:
                        print(f"Successfully updated comment {comment_id}")
                        print(f"Updated comment data: {json.dumps(updated_comment_data, indent=2) if updated_comment_data else 'None'}")
                    else:
                        print(f"Failed to update comment {comment_id}")
                    
                    # Test comment deletion
                    ########################################################################
                    ######################### DELETE COMMENT #########################
                    print("\n" + "="*80)
                    print("CALLING: delete_comment()")
                    print(f"ARGS: {json.dumps([user_post_id, comment_id])}")
                    print("KWARGS: {}")
                    print("="*80)
                    delete_comment_success, delete_comment_data = await linkedin_client.delete_comment(
                        target_urn=user_post_id,
                        comment_id=comment_id,
                        actor_urn=user_urn,
                    )
                    ########################################################################
                    
                    print(f"Comment deletion {'successful' if delete_comment_success else 'failed'}")
                    if delete_comment_data:
                        print(f"Delete comment response: {json.dumps(delete_comment_data, indent=2)}")
                    import ipdb; ipdb.set_trace()
                        
                else:
                    print("Failed to create comment, skipping update and delete tests")
                    
            except Exception as e:
                print(f"Error in comment operations test: {str(e)}")
                import traceback
                traceback.print_exc()
            
            # Test post update
            print("\nTesting Post Update...")
            try:
                updated_post_content = "This is an updated test post content!"
                ########################################################################
                ######################### UPDATE POST #########################
                print("\n" + "="*80)
                print("CALLING: update_post()")
                print(f"ARGS: {json.dumps([user_post_id])}")
                print(f"KWARGS: {json.dumps({'commentary': updated_post_content}, indent=2)}")
                print("="*80)
                update_post_success, updated_post_data = await linkedin_client.update_post(
                    post_urn=user_post_id,
                    commentary=updated_post_content
                )
                ########################################################################
                
                if update_post_success:
                    print(f"Successfully updated post {user_post_id}")
                    print(f"Updated post data: {json.dumps(updated_post_data, indent=2) if updated_post_data else 'None'}")
                else:
                    print(f"Failed to update post {user_post_id}")
                import ipdb; ipdb.set_trace()
                    
            except Exception as e:
                print(f"Error in post update test: {str(e)}")
                import traceback
                traceback.print_exc()


            
            # Debug point after user post creation
            # import ipdb; ipdb.set_trace()
            
            # Test resharing user post by organization
            print("\nTesting Organization Resharing User Post...")
            org_reshare_content = "Resharing this user post as an organization!"
            ########################################################################
            ######################### CREATE RESHARE FOR ORG #########################
            print("\n" + "="*80)
            print("CALLING: create_reshare()")
            print("ARGS: {}")
            print(f"KWARGS: {json.dumps({
                'account_urn': organization_urn,
                'reshare_commentary': org_reshare_content,
                'post_urn': user_post_id,
                'feed_distribution': 'MAIN_FEED'
            }, indent=2)}")
            print("="*80)
            org_reshare_success, org_reshare_id, org_reshare_entity = await linkedin_client.create_reshare(
                account_urn=organization_urn,
                reshare_commentary=org_reshare_content,
                post_urn=user_post_id,
                feed_distribution="MAIN_FEED"
            )
            ########################################################################
            if org_reshare_success:
                print(f"Successfully reshared user post as organization with ID: {org_reshare_id}")
                print(f"Organization reshare entity: {json.dumps(org_reshare_entity, indent=2) if org_reshare_entity else 'None'}")
            else:
                print("Failed to create organization reshare")

            ###################################
            # Debug point
            # import ipdb; ipdb.set_trace()
            ###################################
            
            # Test comprehensive comment operations on user post
            print("\nTesting Comprehensive Comment Operations on User Post...")
            
            # Test user commenting on their own post
            user_self_comment_text = "Commenting on my own post as the author!"
            ########################################################################
            ######################### USER COMMENT ON OWN POST #########################
            print("\n" + "="*80)
            print("CALLING: create_comment() - User on Own Post")
            print(f"ARGS: {json.dumps([user_post_id, user_urn, user_self_comment_text])}")
            print("KWARGS: {}")
            print("="*80)
            user_self_comment_success, user_self_comment_data = await linkedin_client.create_comment(
                target_urn=user_post_id,
                actor_urn=user_urn,
                message_text=user_self_comment_text
            )
            ########################################################################
            
            if user_self_comment_success and user_self_comment_data:
                user_self_comment_id = user_self_comment_data.id
                print(f"Successfully created user self-comment with ID: {user_self_comment_id}")
                print(f"User self-comment data: {json.dumps(user_self_comment_data.model_dump(), indent=2)}")
                import ipdb; ipdb.set_trace()
                
                # Test organization commenting on user post
                org_on_user_comment_text = "Great post! - Organization engaging with user content"
                ########################################################################  
                ######################### ORG COMMENT ON USER POST #########################
                print("\n" + "="*80)
                print("CALLING: create_comment() - Org on User Post")
                print(f"ARGS: {json.dumps([user_post_id, organization_urn, org_on_user_comment_text])}")
                print("KWARGS: {}")
                print("="*80)
                org_on_user_comment_success, org_on_user_comment_data = await linkedin_client.create_comment(
                    target_urn=user_post_id,
                    actor_urn=organization_urn,
                    message_text=org_on_user_comment_text
                )
                ########################################################################
                
                if org_on_user_comment_success and org_on_user_comment_data:
                    org_on_user_comment_id = org_on_user_comment_data.id
                    print(f"Successfully created organization comment on user post with ID: {org_on_user_comment_id}")
                    print(f"Organization comment data: {json.dumps(org_on_user_comment_data.model_dump(), indent=2)}") 
                    import ipdb; ipdb.set_trace()
                    
                    # Test updating organization comment on user post
                    updated_org_on_user_comment = "Updated organization comment on user post!"
                    ########################################################################
                    ######################### UPDATE ORG COMMENT ON USER POST #########################
                    print("\n" + "="*80)
                    print("CALLING: update_comment() - Org Comment on User Post")
                    print(f"ARGS: {json.dumps([user_post_id, org_on_user_comment_id, updated_org_on_user_comment])}")
                    print(f"KWARGS: {json.dumps({'actor_urn': organization_urn}, indent=2)}")
                    print("="*80)
                    org_on_user_update_success, org_on_user_updated_comment = await linkedin_client.update_comment(
                        target_urn=user_post_id,
                        comment_id=org_on_user_comment_id,
                        message_text=updated_org_on_user_comment,
                        actor_urn=organization_urn
                    )
                    ########################################################################
                    
                    if org_on_user_update_success:
                        print(f"Successfully updated organization comment on user post {org_on_user_comment_id}")
                        print(f"Updated org comment: {json.dumps(org_on_user_updated_comment, indent=2) if org_on_user_updated_comment else 'None'}")
                    import ipdb; ipdb.set_trace()
                    
                    # Test deleting organization comment on user post
                    ########################################################################
                    ######################### DELETE ORG COMMENT ON USER POST #########################
                    print("\n" + "="*80)
                    print("CALLING: delete_comment() - Org Comment on User Post")
                    print(f"ARGS: {json.dumps([user_post_id, org_on_user_comment_id])}")
                    print(f"KWARGS: {json.dumps({'actor_urn': organization_urn}, indent=2)}")
                    print("="*80)
                    org_on_user_delete_success, org_on_user_delete_data = await linkedin_client.delete_comment(
                        target_urn=user_post_id,
                        comment_id=org_on_user_comment_id,
                        actor_urn=organization_urn
                    )
                    ########################################################################
                    
                    print(f"Organization comment on user post deletion {'successful' if org_on_user_delete_success else 'failed'}")
                    if org_on_user_delete_data:
                        print(f"Delete org comment response: {json.dumps(org_on_user_delete_data, indent=2)}")
                    import ipdb; ipdb.set_trace()
                
                # Test updating user's own comment
                updated_user_self_comment = "Updated my own comment on my post!"
                ########################################################################
                ######################### UPDATE USER SELF COMMENT #########################
                print("\n" + "="*80)
                print("CALLING: update_comment() - User Self Comment")
                print(f"ARGS: {json.dumps([user_post_id, user_self_comment_id, updated_user_self_comment])}")
                print("KWARGS: {}")
                print("="*80)
                user_self_update_success, user_self_updated_comment = await linkedin_client.update_comment(
                    target_urn=user_post_id,
                    comment_id=user_self_comment_id,
                    message_text=updated_user_self_comment,
                    actor_urn=user_urn,
                )
                ########################################################################
                
                if user_self_update_success:
                    print(f"Successfully updated user self-comment {user_self_comment_id}")
                    print(f"Updated user self-comment: {json.dumps(user_self_updated_comment, indent=2) if user_self_updated_comment else 'None'}")
                import ipdb; ipdb.set_trace()
                
                # Test deleting user's own comment
                ########################################################################
                ######################### DELETE USER SELF COMMENT #########################
                print("\n" + "="*80)
                print("CALLING: delete_comment() - User Self Comment")
                print(f"ARGS: {json.dumps([user_post_id, user_self_comment_id])}")
                print("KWARGS: {}")
                print("="*80)
                user_self_delete_success, user_self_delete_data = await linkedin_client.delete_comment(
                    target_urn=user_post_id,
                    comment_id=user_self_comment_id,
                    actor_urn=user_urn,
                )
                ########################################################################
                
                print(f"User self-comment deletion {'successful' if user_self_delete_success else 'failed'}")
                if user_self_delete_data:
                    print(f"Delete user self-comment response: {json.dumps(user_self_delete_data, indent=2)}")
                import ipdb; ipdb.set_trace()

            # Delete the organization's reshare
            print("\nDeleting organization's reshare...")
            ########################################################################
            ######################### DELETE TEST ORG REPOST #########################
            print("\n" + "="*80)
            print("CALLING: delete_post()")
            print(f"ARGS: {json.dumps([org_reshare_id])}")
            print("KWARGS: {}")
            print("="*80)
            delete_org_reshare_success, delete_org_reshare_entity = await linkedin_client.delete_post(org_reshare_id)
            ########################################################################
            print(f"Organization reshare deletion {'successful' if delete_org_reshare_success else 'failed'}")
            if delete_org_reshare_entity:
                print(f"Delete org reshare response: {json.dumps(delete_org_reshare_entity, indent=2)}")
            
            # Delete the test user post
            print("\nDeleting test user post...")
            ########################################################################
            ######################### DELETE TEST USER POST #########################
            print("\n" + "="*80)
            print("CALLING: delete_post()")
            print(f"ARGS: {json.dumps([user_post_id])}")
            print("KWARGS: {}")
            print("="*80)
            delete_success, delete_entity = await linkedin_client.delete_post(user_post_id)
            ########################################################################
            print(f"User post deletion {'successful' if delete_success else 'failed'}")
            if delete_entity:
                print(f"Delete user post response: {json.dumps(delete_entity, indent=2)}")
        except Exception as e:
            print(f"Error in user post creation/reshare/deletion test: {str(e)}")
            import traceback
            traceback.print_exc()
            return
        ########################################################################
        
        # Final debug point before continuing to post fetching
        import ipdb; ipdb.set_trace()
        #######################################################################
        
        # 4. Fetch posts for the organization
        print("\nFetching Organization Posts...")
        try:
            # Fetch the last 5 posts from the organization
            ########################################################################
            ######################### FETCH ORG POSTS #########################
            print("\n" + "="*80)
            print("CALLING: get_posts()")
            print("ARGS: {}")
            print(f"KWARGS: {json.dumps({
                'account_id': organization_urn,
                'limit': 50
            }, indent=2)}")
            print("="*80)
            success, org_posts = await linkedin_client.get_posts(
                account_id=organization_urn,
                limit=50
            )
            if not success or not org_posts:
                org_posts = []
            ########################################################################
            print(f"Found {len(org_posts)} organization posts:")
            for i, post in enumerate(org_posts, 1):
                print(f"  {i}. Post ID: {post.id}")
                print(f"     Created: {post.created_at}")
                if post.content_text:
                    print(f"     Content: {post.content_text[:100]}..." if len(post.content_text) > 100 else f"     Content: {post.content_text}")
                if post.media_urls:
                    print(f"     Media URLs: {', '.join(post.media_urls) if post.media_urls else 'None'}")
                print()
        except Exception as e:
            print(f"Error fetching organization posts: {str(e)}")
            import traceback
            traceback.print_exc()
        

        ########################################################################
        # import ipdb; ipdb.set_trace()
        ########################################################################
        
        # 5. Fetch posts for the user
        print("\nFetching User Posts...")
        try:
            # Fetch the last 5 posts from the user
            ########################################################################
            ######################### FETCH USER POSTS #########################
            print("\n" + "="*80)
            print("CALLING: get_posts()")
            print("ARGS: {}")
            print(f"KWARGS: {json.dumps({
                'account_id': user_urn,
                'limit': 50
            }, indent=2)}")
            print("="*80)
            success, user_posts = await linkedin_client.get_posts(
                account_id=user_urn,
                limit=50
            )
            if not success or not user_posts:
                user_posts = []
            ########################################################################
            
            print(f"Found {len(user_posts)} user posts:")
            for i, post in enumerate(user_posts, 1):
                print(f"  {i}. Post ID: {post.id}")
                print(f"     Created: {post.created_at}")
                print(f"     Content: {post.content_text[:100]}..." if len(post.content_text) > 100 else f"     Content: {post.content_text}")
                print(f"     Media URLs: {', '.join(post.media_urls) if post.media_urls else 'None'}")
                print()
        except Exception as e:
            print(f"Error fetching user posts: {str(e)}")
            import traceback
            traceback.print_exc()
        

        ########################################################################
        # import ipdb; ipdb.set_trace()
        ########################################################################

        # 6. Fetch social actions for user posts
        print("\nFetching Social Actions for User Posts...")
        try:
            if user_posts:
                # Extract post IDs for batch fetching
                user_post_ids = [post.id for post in user_posts]
                
                # Batch fetch social actions for user posts
                ########################################################################
                ######################### BATCH FETCH SOCIAL ACTIONS FOR USER POSTS #########################
                print("\n" + "="*80)
                print("CALLING: batch_get_post_social_actions()")
                print(f"ARGS: {json.dumps(user_post_ids)}")
                print("KWARGS: {}")
                print("="*80)
                # linkedin_client.enable_caching = False
                success, user_social_actions = await linkedin_client.batch_get_post_social_actions(user_post_ids)
                if not success or not user_social_actions:
                    user_social_actions = {}
                ########################################################################
                print(f"Retrieved social actions for {len(user_social_actions)} user posts:")
                for post_id, actions in user_social_actions.items():
                    # Find the corresponding post to display content context
                    post = next((p for p in user_posts if p.id == post_id), None)
                    post_content = post.content_text[:50] + "..." if post and len(post.content_text) > 50 else "N/A"
                    
                    # Extract and display social action metrics
                    likes = actions.likes_summary.total_likes if actions.likes_summary else 0
                    comments = actions.comments_summary.total_first_level_comments if actions.comments_summary else 0
                    
                    print(f"  Post: {post_content}")
                    print(f"    ID: {post_id}")
                    print(f"    Likes: {likes}")
                    print(f"    Comments: {comments}")
                    print()
            else:
                print("No user posts available to fetch social actions.")
        except Exception as e:
            print(f"Error fetching social actions for user posts: {str(e)}")
            import traceback
            traceback.print_exc()

        ########################################################################
        # import ipdb; ipdb.set_trace()
        ########################################################################

        # Test individual organization post metrics
        print("\nTesting Individual Organization Post Metrics...")
        if org_posts:
            # Test with first organization post only
            test_post = org_posts[0]
            test_post_id = test_post.id
            print(f"\n ---> Testing org post: {test_post_id} ---> ")
            await test_post_retrieval_and_metrics(linkedin_client, test_post_id)
        else:
            print("No organization posts available to test individual metrics.")
            
        ########################################################################
        # import ipdb; ipdb.set_trace()
        ########################################################################

        # 7. Fetch social actions for organization posts
        print("\nFetching Social Actions for Organization Posts...")
        try:
            if org_posts:
                # Extract post IDs for batch fetching
                org_post_ids = [post.id for post in org_posts]
                
                # Batch fetch social actions for organization posts
                ########################################################################
                ######################### BATCH FETCH SOCIAL ACTIONS FOR ORG POSTS #########################
                print("\n" + "="*80)
                print("CALLING: batch_get_post_social_actions()")
                print(f"ARGS: {json.dumps(org_post_ids)}")
                print("KWARGS: {}")
                print("="*80)
                # linkedin_client.enable_caching = False
                success, org_social_actions = await linkedin_client.batch_get_post_social_actions(org_post_ids)
                if not success or not org_social_actions:
                    org_social_actions = {}
                ########################################################################
                print(f"Retrieved social actions for {len(org_social_actions)} organization posts:")
                for post_id, actions in org_social_actions.items():
                    # Find the corresponding post to display content context
                    post = next((p for p in org_posts if p.id == post_id), None)
                    post_content = post.content_text[:50] + "..." if post and len(post.content_text) > 50 else "N/A"
                    
                    # Extract and display social action metrics
                    likes = actions.likes_summary.total_likes if actions.likes_summary else 0
                    comments = actions.comments_summary.total_first_level_comments if actions.comments_summary else 0
                    
                    print(f"  Post: {post_content}")
                    print(f"    ID: {post_id}")
                    print(f"    Likes: {likes}")
                    print(f"    Comments: {comments}")
                    print()
            else:
                print("No organization posts available to fetch social actions.")
        except Exception as e:
            print(f"Error fetching social actions for organization posts: {str(e)}")
            import traceback
            traceback.print_exc()


        ########################################################################
        # import ipdb; ipdb.set_trace()
        ########################################################################

        # 4. Proceed with further testing using the selected URNs.
        # a. Test lifetime share statistics.
        print("\nFetching Lifetime Share Statistics...")
        try:
            ########################################################################
            ######################### FETCH LIFETIME SHARE STATISTICS FOR ORG #########################
            print("\n" + "="*80)
            print("CALLING: get_organization_lifetime_share_statistics()")
            print(f"ARGS: {json.dumps([organization_urn])}")
            print("KWARGS: {}")
            print("="*80)
            # linkedin_client.enable_caching = False
            success, lifetime_stats = await linkedin_client.get_organization_lifetime_share_statistics(organization_urn)
            if not success:
                lifetime_stats = None
            ########################################################################
            print("Lifetime Share Statistics:")
            print(lifetime_stats)
        except Exception as e:
            print(f"Error fetching lifetime share statistics: {str(e)}")
            import traceback
            traceback.print_exc()


        ########################################################################
        # import ipdb; ipdb.set_trace()
        ########################################################################

        # b. Test current follower count.
        print("\nFetching Current Follower Count...")
        try:
            ########################################################################
            ######################### FETCH CURRENT FOLLOWER COUNT FOR ORG #########################
            print("\n" + "="*80)
            print("CALLING: get_organization_follower_count()")
            print(f"ARGS: {json.dumps([organization_urn])}")
            print("KWARGS: {}")
            print("="*80)
            # linkedin_client.enable_caching = False
            success, follower_count = await linkedin_client.get_organization_follower_count(organization_urn)
            if not success:
                follower_count = None
            ########################################################################
            print("Current Follower Count:")
            print(follower_count)
        except Exception as e:
            print(f"Error fetching current follower count: {str(e)}")
            import traceback
            traceback.print_exc()

        ########################################################################
        # import ipdb; ipdb.set_trace()
        ########################################################################

        # c. Test time-bound share statistics (using last 7 days as an example).
        print("\nFetching Time-bound Share Statistics (Last 7 Days)...")
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=7)
        try:
            ########################################################################
            ######################### FETCH TIME-BOUND SHARE STATISTICS FOR ORG #########################
            print("\n" + "="*80)
            print("CALLING: get_organization_timebound_share_statistics()")
            print(f"ARGS: {json.dumps([organization_urn])}")
            print(f"KWARGS: {json.dumps({
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'granularity': 'DAY'
            }, indent=2)}")
            print("="*80)
            success, timebound_stats = await linkedin_client.get_organization_timebound_share_statistics(
                organization_urn, start_date, end_date, granularity="DAY"
            )
            if not success:
                timebound_stats = None
            ########################################################################
            print("Time-bound Share Statistics (Last 7 Days):")
            print(timebound_stats)
        except Exception as e:
            print(f"Error fetching time-bound share statistics: {str(e)}")
            import traceback
            traceback.print_exc()

        ########################################################################
        # import ipdb; ipdb.set_trace()
        ########################################################################
        
    except Exception as e:
        print(f"Error during organization testing: {e}")

async def main() -> None:
    """
    Main entry point for the interactive organization test.

    Prompts the user for API credentials and creates a LinkedInClient instance.
    Then, it calls the test_org_selection() function.
    """
    print("=== LinkedIn Organization API Testing ===\n")
    
    # Prompt user for necessary credentials.
    client_id = settings.LINKEDIN_CLIENT_ID
    client_secret = settings.LINKEDIN_CLIENT_SECRET
    access_token = settings.LINKEDIN_ACCESS_TOKEN
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
    await test_org_selection(linkedin_client)

if __name__ == "__main__":
    asyncio.run(main())
