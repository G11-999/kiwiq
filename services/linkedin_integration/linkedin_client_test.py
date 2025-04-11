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

Usage:
    $ python tests/test_linkedin_client_org_selection.py
"""

import asyncio
from datetime import datetime, timedelta, timezone
import json
from typing import Any

# Import our LinkedInClient and required models
from linkedin_integration.linkedin_client import LinkedInClient
from global_config.settings import global_settings

async def test_org_selection(linkedin_client: LinkedInClient) -> None:
    """
    Fetches all organization roles for the authenticated member, prompts the user to select one,
    and then tests several organization-level API methods using the selected organization URN.

    Args:
        linkedin_client: An instance of LinkedInClient properly configured with credentials.
    """
    try:
        # 1. Fetch organization roles for the authenticated member.
        roles_response = await linkedin_client.get_member_organization_roles()
        roles = roles_response.elements

        if not roles:
            print("No organization roles found for the authenticated member.")
            return
            
        # Fetch member profile details
        member_profile = await linkedin_client.get_member_profile()
        print(f"\nAuthenticated Member Profile:")
        print(f"ID: {member_profile.get('id', 'N/A')}")
        print(f"Name: {member_profile.get('firstName', {}).get('localized', {}).get('en_US', 'N/A')} {member_profile.get('lastName', {}).get('localized', {}).get('en_US', 'N/A')}")
        print(f"Headline: {member_profile.get('headline', {}).get('localized', {}).get('en_US', 'N/A')}")

        # 2. Print out the details of each organization role.
        print("\nOrganizations and Roles for Authenticated Member:")
        for idx, role in enumerate(roles, start=1):
            # Each role contains the user URN in role_assignee and the org URN in organization.
            # Fetch organization details
            org_details = await linkedin_client.get_organization_details(role.organization)
            org_name = org_details.get('localizedName', 'Unknown Organization')
            
            print(f"{idx}. Organization:  {org_name} \n({role.organization}) | "
                  f"Role: {role.role} | State: {role.state} | "
                  f"User URN: {role.role_assignee}")

        # 3. Prompt user to choose one organization by number.
        selection = input("\nEnter the number of the organization you want to test: ").strip()
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

        print(f"\nSelected Organization URN: {organization_urn}")
        print(f"User URN (from role): {user_urn}")

        # Extract organization ID from URN
        organization_id = organization_urn.split(":")[-1]
        
        # Extract user ID from URN
        user_id = user_urn.split(":")[-1]

        ########################################################################
        # Test creating a post for the organization
        print("\nTesting Organization Post Creation...")
        try:
            # Create a test post for the organization
            org_post_content = f"This is a test post for organization created now."
            org_post_id = await linkedin_client.create_post(
                account_urn=organization_urn,
                content=org_post_content,
                feed_distribution="MAIN_FEED"
            )
            print(f"Successfully created organization post with ID: {org_post_id}")
            
            # Debug point after organization post creation
            import ipdb; ipdb.set_trace()
            
            # Test resharing organization post by user
            print("\nTesting User Resharing Organization Post...")
            user_reshare_content = "Resharing this organization post as a user!"
            user_reshare_id = await linkedin_client.create_reshare(
                account_urn=user_urn,
                reshare_commentary=user_reshare_content,
                post_urn=org_post_id,
                feed_distribution="MAIN_FEED"
            )
            print(f"Successfully reshared organization post as user with ID: {user_reshare_id}")

            ###################################
            # Debug point
            import ipdb; ipdb.set_trace()
            ###################################
            
            # Delete the user's reshare
            print("\nDeleting user's reshare...")
            delete_reshare_success = await linkedin_client.delete_post(user_reshare_id)
            print(f"User reshare deletion {'successful' if delete_reshare_success else 'failed'}")
            
            # Delete the test organization post
            print("\nDeleting test organization post...")
            delete_success = await linkedin_client.delete_post(org_post_id)
            print(f"Organization post deletion {'successful' if delete_success else 'failed'}")
        except Exception as e:
            print(f"Error in organization post creation/reshare/deletion test: {str(e)}")
            import traceback
            traceback.print_exc()
        ########################################################################
        ###################################
        # Debug point
        import ipdb; ipdb.set_trace()
        ###################################
        
        # Test creating a post for the user
        print("\nTesting User Post Creation...")
        try:
            # Create a test post for the user
            user_post_content = f"This is a test post for user created now."
            user_post_id = await linkedin_client.create_post(
                account_urn=user_urn,
                content=user_post_content,
                feed_distribution="MAIN_FEED"
            )
            print(f"Successfully created user post with ID: {user_post_id}")
            
            # Debug point after user post creation
            import ipdb; ipdb.set_trace()
            
            # Test resharing user post by organization
            print("\nTesting Organization Resharing User Post...")
            org_reshare_content = "Resharing this user post as an organization!"
            org_reshare_id = await linkedin_client.create_reshare(
                account_urn=organization_urn,
                reshare_commentary=org_reshare_content,
                post_urn=user_post_id,
                feed_distribution="MAIN_FEED"
            )
            print(f"Successfully reshared user post as organization with ID: {org_reshare_id}")

            ###################################
            # Debug point
            import ipdb; ipdb.set_trace()
            ###################################
            
            # Delete the organization's reshare
            print("\nDeleting organization's reshare...")
            delete_org_reshare_success = await linkedin_client.delete_post(org_reshare_id)
            print(f"Organization reshare deletion {'successful' if delete_org_reshare_success else 'failed'}")
            
            # Delete the test user post
            print("\nDeleting test user post...")
            delete_success = await linkedin_client.delete_post(user_post_id)
            print(f"User post deletion {'successful' if delete_success else 'failed'}")
        except Exception as e:
            print(f"Error in user post creation/reshare/deletion test: {str(e)}")
            import traceback
            traceback.print_exc()
        ########################################################################
        
        # Final debug point before continuing to post fetching
        import ipdb; ipdb.set_trace()
        ########################################################################
        
        # 4. Fetch posts for the organization
        print("\nFetching Organization Posts...")
        try:
            # Fetch the last 5 posts from the organization
            org_posts = await linkedin_client.get_posts(
                account_id=organization_urn,
                limit=50
            )
            
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
        import ipdb; ipdb.set_trace()
        ########################################################################
        
        # 5. Fetch posts for the user
        print("\nFetching User Posts...")
        try:
            # Fetch the last 5 posts from the user
            user_posts = await linkedin_client.get_posts(
                account_id=user_urn,
                limit=50
            )
            
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
        import ipdb; ipdb.set_trace()
        ########################################################################
        

        # 6. Fetch social actions for user posts
        print("\nFetching Social Actions for User Posts...")
        try:
            if user_posts:
                # Extract post IDs for batch fetching
                user_post_ids = [post.id for post in user_posts]
                
                # Batch fetch social actions for user posts
                user_social_actions = await linkedin_client.batch_get_post_social_actions(user_post_ids)
                
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
        import ipdb; ipdb.set_trace()
        ########################################################################
        
        # 7. Fetch social actions for organization posts
        print("\nFetching Social Actions for Organization Posts...")
        try:
            if org_posts:
                # Extract post IDs for batch fetching
                org_post_ids = [post.id for post in org_posts]
                
                # Batch fetch social actions for organization posts
                org_social_actions = await linkedin_client.batch_get_post_social_actions(org_post_ids)
                
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
        import ipdb; ipdb.set_trace()
        ########################################################################

        # 4. Proceed with further testing using the selected URNs.
        # a. Test lifetime share statistics.
        print("\nFetching Lifetime Share Statistics...")
        try:
            lifetime_stats = await linkedin_client.get_organization_lifetime_share_statistics(organization_urn)
            print("Lifetime Share Statistics:")
            print(lifetime_stats)
        except Exception as e:
            print(f"Error fetching lifetime share statistics: {str(e)}")
            import traceback
            traceback.print_exc()


        ########################################################################
        import ipdb; ipdb.set_trace()
        ########################################################################

        # b. Test current follower count.
        print("\nFetching Current Follower Count...")
        try:
            follower_count = await linkedin_client.get_organization_follower_count(organization_urn)
            print("Current Follower Count:")
            print(follower_count)
        except Exception as e:
            print(f"Error fetching current follower count: {str(e)}")
            import traceback
            traceback.print_exc()

        ########################################################################
        import ipdb; ipdb.set_trace()
        ########################################################################

        # c. Test time-bound share statistics (using last 7 days as an example).
        print("\nFetching Time-bound Share Statistics (Last 7 Days)...")
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=7)
        try:
            timebound_stats = await linkedin_client.get_organization_timebound_share_statistics(
                organization_urn, start_date, end_date, granularity="DAY"
            )
            print("Time-bound Share Statistics (Last 7 Days):")
            print(timebound_stats)
        except Exception as e:
            print(f"Error fetching time-bound share statistics: {str(e)}")
            import traceback
            traceback.print_exc()

        ########################################################################
        import ipdb; ipdb.set_trace()
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
    client_id = global_settings.LINKEDIN_CLIENT_ID
    client_secret = global_settings.LINKEDIN_CLIENT_SECRET
    access_token = global_settings.LINKEDIN_ACCESS_TOKEN  # LINKEDIN_ACCESS_TOKEN  LINKEDIN_ACCESS_TOKEN
    # urn:li:person:NxwL-IvR2n
    # urn:li:person:qUvas1UvE2
    version_input = global_settings.LINKEDIN_API_VERSION

    # Instantiate the LinkedInClient with caching disabled for testing.
    linkedin_client = LinkedInClient(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        version=version_input,
        enable_caching=True  # Disable caching to force live API calls for testing
    )

    # Run the organization selection and subsequent tests.
    await test_org_selection(linkedin_client)




if __name__ == "__main__":
    asyncio.run(main())

