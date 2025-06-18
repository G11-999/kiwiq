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
from typing import Any, List, Optional

# Import our LinkedInClient and required models
from linkedin_integration.client.linkedin_client import (
    LinkedInClient, 
    ShareStatisticsRequest,
    ShareStatisticsResponse
)
from kiwi_app.settings import settings


async def test_share_statistics_comprehensive(
    linkedin_client: LinkedInClient, 
    organization_urn: str
) -> None:
    """
    Comprehensive testing of the new unified get_org_share_statistics method.
    
    This function tests all scenarios supported by the ShareStatisticsRequest:
    1. Lifetime statistics (no time restrictions)
    2. Time-bound statistics (last 30 days, last 7 days)
    3. Statistics for specific posts (if posts are available)
    4. Combined time-bound and specific posts statistics
    
    Args:
        linkedin_client: Configured LinkedInClient instance
        organization_urn: Organization URN to test with
    """
    print(f"\n{'='*80}")
    print("🔍 COMPREHENSIVE SHARE STATISTICS TESTING")
    print(f"{'='*80}")
    print(f"Testing organization: {organization_urn}")
    
    # First, let's get some posts to use for specific post testing
    print(f"\n📋 Step 1: Fetching recent posts for specific post testing...")
    try:
        posts = await linkedin_client.get_posts(
            account_id=organization_urn,
            limit=5  # Get last 5 posts for testing
        )

        print(f"✅ Found {len(posts)} posts for testing")
        
        # Extract post URNs for testing (convert to the right format)
        post_urns = []
        ugc_post_urns = []
        share_urns = []
        
        for post in posts[:3]:  # Use max 3 posts for testing
            # Determine if it's a UGC post or share based on the post structure
            # For now, assume all are UGC posts (most common case)
            post_urn = f"urn:li:ugcPost:{post.id}" if not post.id.startswith("urn:") else post.id
            if "ugcPost" in post_urn:
                ugc_post_urns.append(post_urn)
            else:
                share_urns.append(post_urn)
            post_urns.append(post_urn)
            
        print(f"📌 UGC Post URNs for testing: {ugc_post_urns}")
        print(f"📌 Share URNs for testing: {share_urns}")

        import ipdb; ipdb.set_trace()
        
    except Exception as e:
        print(f"⚠️  Could not fetch posts: {str(e)}")
        post_urns = []
        ugc_post_urns = []
        share_urns = []
    
    # import ipdb; ipdb.set_trace()
    
    # Test 1: Lifetime Statistics
    print(f"\n{'='*60}")
    print("📊 TEST 1: LIFETIME SHARE STATISTICS")
    print(f"{'='*60}")
    
    try:
        request = ShareStatisticsRequest.create_lifetime_request(
            organizational_entity=organization_urn
        )
        print(f"🔍 Request parameters: {request.model_dump(by_alias=True)}")
        
        success, stats_response = await linkedin_client.get_org_share_statistics(request)
        
        print(f"✅ API Success: {success}")
        if success and stats_response:
            print(f"📈 Lifetime statistics retrieved: {len(stats_response.elements)} elements")
            
            # Print detailed statistics
            for i, stat in enumerate(stats_response.elements):
                print(f"\n📊 Element {i+1}:")
                print(f"   Organization: {stat.organizational_entity}")
                print(f"   Impressions: {stat.total_share_statistics.impression_count:,}")
                print(f"   Clicks: {stat.total_share_statistics.click_count:,}")
                print(f"   Likes: {stat.total_share_statistics.like_count:,}")
                print(f"   Comments: {stat.total_share_statistics.comment_count:,}")
                print(f"   Shares: {stat.total_share_statistics.share_count:,}")
                print(f"   Engagement: {stat.total_share_statistics.engagement:.4f}")
                if stat.time_range:
                    print(f"   Time Range: {stat.time_range}")
        else:
            print(f"❌ Failed to retrieve lifetime statistics")
            
    except Exception as e:
        print(f"❌ Error in lifetime statistics test: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # Test 2: Time-bound Statistics (Last 30 days)
    print(f"\n{'='*60}")
    print("📊 TEST 2: TIME-BOUND SHARE STATISTICS (Last 30 Days)")
    print(f"{'='*60}")
    
    try:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30)
        
        request = ShareStatisticsRequest.create_timebound_request(
            organizational_entity=organization_urn,
            start_date=start_date,
            end_date=end_date,
            granularity="DAY"
        )
        print(f"🔍 Request parameters: {request.model_dump(by_alias=True)}")
        print(f"📅 Date range: {start_date.date()} to {end_date.date()}")
        
        success, stats_response = await linkedin_client.get_org_share_statistics(request)
        
        print(f"✅ API Success: {success}")
        if success and stats_response:
            print(f"📈 Time-bound statistics retrieved: {len(stats_response.elements)} elements")
            
            # Print summary statistics
            total_impressions = sum(stat.total_share_statistics.impression_count for stat in stats_response.elements)
            total_engagement = sum(stat.total_share_statistics.engagement for stat in stats_response.elements)
            
            print(f"\n📊 30-Day Summary:")
            print(f"   Total Impressions: {total_impressions:,}")
            print(f"   Total Engagement: {total_engagement:.4f}")
            print(f"   Days with data: {len(stats_response.elements)}")
            
            # Show first few daily breakdowns
            for i, stat in enumerate(stats_response.elements[:5]):
                print(f"\n📅 Day {i+1}:")
                if stat.time_range:
                    start_ts = stat.time_range.get('start', 0)
                    end_ts = stat.time_range.get('end', 0)
                    start_dt = datetime.fromtimestamp(start_ts/1000) if start_ts else "N/A"
                    end_dt = datetime.fromtimestamp(end_ts/1000) if end_ts else "N/A"
                    print(f"   Date: {start_dt.date() if start_dt != 'N/A' else 'N/A'}")
                print(f"   Impressions: {stat.total_share_statistics.impression_count:,}")
                print(f"   Engagement: {stat.total_share_statistics.engagement:.4f}")
                
        else:
            print(f"❌ Failed to retrieve time-bound statistics")
            
    except Exception as e:
        print(f"❌ Error in time-bound statistics test: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # Test 3: Time-bound Statistics (Last 7 days with MONTH granularity)
    print(f"\n{'='*60}")
    print("📊 TEST 3: TIME-BOUND SHARE STATISTICS (Last 7 Days - MONTH granularity)")
    print(f"{'='*60}")
    
    try:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=61)
        
        request = ShareStatisticsRequest.create_timebound_request(
            organizational_entity=organization_urn,
            start_date=start_date,
            end_date=end_date,
            granularity="MONTH"
        )
        print(f"🔍 Request parameters: {request.model_dump(by_alias=True)}")
        print(f"📅 Date range: {start_date.date()} to {end_date.date()}")
        
        success, stats_response = await linkedin_client.get_org_share_statistics(request)
        
        print(f"✅ API Success: {success}")
        if success and stats_response:
            print(f"📈 Monthly statistics retrieved: {len(stats_response.elements)} elements")
            for stat in stats_response.elements:
                print(f"\n📊 Monthly data:")
                print(f"   Impressions: {stat.total_share_statistics.impression_count:,}")
                print(f"   Clicks: {stat.total_share_statistics.click_count:,}")
                print(f"   Engagement: {stat.total_share_statistics.engagement:.4f}")
        else:
            print(f"❌ Failed to retrieve monthly statistics")
            
    except Exception as e:
        print(f"❌ Error in monthly statistics test: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # Test 4: Statistics for Specific Posts
    if post_urns:
        print(f"\n{'='*60}")
        print("📊 TEST 4: STATISTICS FOR SPECIFIC POSTS")
        print(f"{'='*60}")
        
        try:
            request = ShareStatisticsRequest.create_posts_request(
                organizational_entity=organization_urn,
                share_urns=share_urns if share_urns else None,
                ugc_post_urns=ugc_post_urns if ugc_post_urns else None
            )
            print(f"🔍 Request parameters: {request.model_dump(by_alias=True)}")
            print(f"📋 Testing {len(post_urns)} posts")
            
            success, stats_response = await linkedin_client.get_org_share_statistics(request)
            
            print(f"✅ API Success: {success}")
            if success and stats_response:
                print(f"📈 Post-specific statistics retrieved: {len(stats_response.elements)} elements")
                
                for i, stat in enumerate(stats_response.elements):
                    post_id = stat.ugc_post or stat.share or "Unknown"
                    print(f"\n📊 Post {i+1} ({post_id}):")
                    print(f"   Impressions: {stat.total_share_statistics.impression_count:,}")
                    print(f"   Clicks: {stat.total_share_statistics.click_count:,}")
                    print(f"   Likes: {stat.total_share_statistics.like_count:,}")
                    print(f"   Comments: {stat.total_share_statistics.comment_count:,}")
                    print(f"   Shares: {stat.total_share_statistics.share_count:,}")
                    print(f"   Engagement: {stat.total_share_statistics.engagement:.4f}")
            else:
                print(f"❌ Failed to retrieve post-specific statistics")
                
        except Exception as e:
            print(f"❌ Error in post-specific statistics test: {str(e)}")
            import traceback
            traceback.print_exc()
        

        # import ipdb; ipdb.set_trace()
    
        # Test 5: Combined Time-bound and Specific Posts
        print(f"\n{'='*60}")
        print("📊 TEST 5: COMBINED TIME-BOUND + SPECIFIC POSTS STATISTICS")
        print(f"{'='*60}")
        
        try:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=14)  # Last 2 weeks
            
            # Use only first 2 posts to avoid too much data
            test_ugc_posts = ugc_post_urns[:2] if ugc_post_urns else None
            test_shares = share_urns[:2] if share_urns else None
            
            request = ShareStatisticsRequest.create_timebound_posts_request(
                organizational_entity=organization_urn,
                start_date=start_date,
                end_date=end_date,
                granularity="DAY",
                share_urns=test_shares,
                ugc_post_urns=test_ugc_posts
            )
            print(f"🔍 Request parameters: {request.model_dump(by_alias=True)}")
            print(f"📅 Date range: {start_date.date()} to {end_date.date()}")
            print(f"📋 Testing specific posts with time boundaries")
            
            success, stats_response = await linkedin_client.get_org_share_statistics(request)
            
            print(f"✅ API Success: {success}")
            if success and stats_response:
                print(f"📈 Combined statistics retrieved: {len(stats_response.elements)} elements")
                
                # Group by post and summarize
                post_summaries = {}
                for stat in stats_response.elements:
                    post_id = stat.ugc_post or stat.share or "Unknown"
                    if post_id not in post_summaries:
                        post_summaries[post_id] = {
                            'total_impressions': 0,
                            'total_engagement': 0,
                            'days': 0
                        }
                    post_summaries[post_id]['total_impressions'] += stat.total_share_statistics.impression_count
                    post_summaries[post_id]['total_engagement'] += stat.total_share_statistics.engagement
                    post_summaries[post_id]['days'] += 1
                
                for post_id, summary in post_summaries.items():
                    print(f"\n📊 Post Summary ({post_id}):")
                    print(f"   Total Impressions (14 days): {summary['total_impressions']:,}")
                    print(f"   Total Engagement (14 days): {summary['total_engagement']:.4f}")
                    print(f"   Days with data: {summary['days']}")
                    print(f"   Avg Daily Impressions: {summary['total_impressions']/max(1, summary['days']):,.1f}")
            else:
                print(f"❌ Failed to retrieve combined statistics")
                
        except Exception as e:
            print(f"❌ Error in combined statistics test: {str(e)}")
            import traceback
            traceback.print_exc()
    
    else:
        print(f"\n⚠️  SKIPPING post-specific tests - no posts available")
    
    # # Test 6: Error handling - Invalid organization URN
    # print(f"\n{'='*60}")
    # print("📊 TEST 6: ERROR HANDLING - Invalid Organization URN")
    # print(f"{'='*60}")
    
    # try:
    #     invalid_request = ShareStatisticsRequest.create_lifetime_request(
    #         organizational_entity="urn:li:organization:1035"  # Invalid org  MICROSOFT!
    #     )
    #     print(f"🔍 Testing with invalid organization URN")
        
    #     success, stats_response = await linkedin_client.get_org_share_statistics(invalid_request)
        
    #     print(f"✅ API Success: {success}")
    #     if not success:
    #         print(f"✅ Error handling working correctly - invalid org rejected")
    #     else:

    #         # Print detailed statistics
    #         for i, stat in enumerate(stats_response.elements):
    #             print(f"\n📊 Element {i+1}:")
    #             print(f"   Organization: {stat.organizational_entity}")
    #             print(f"   Impressions: {stat.total_share_statistics.impression_count:,}")
    #             print(f"   Clicks: {stat.total_share_statistics.click_count:,}")
    #             print(f"   Likes: {stat.total_share_statistics.like_count:,}")
    #             print(f"   Comments: {stat.total_share_statistics.comment_count:,}")
    #             print(f"   Shares: {stat.total_share_statistics.share_count:,}")
    #             print(f"   Engagement: {stat.total_share_statistics.engagement:.4f}")

    #         print(f"⚠️  Unexpected: Invalid org request succeeded")
            
    # except Exception as e:
    #     print(f"✅ Exception caught as expected: {str(e)}")
    
    # Test 7: Validation - Invalid URN format
    print(f"\n{'='*60}")
    print("📊 TEST 7: VALIDATION - Invalid URN Format")
    print(f"{'='*60}")
    
    try:
        # This should raise a validation error
        invalid_request = ShareStatisticsRequest(
            organizational_entity="invalid-urn-format"
        )
        print(f"❌ Validation failed - should have rejected invalid URN format")
        
    except ValueError as e:
        print(f"✅ Validation working correctly: {str(e)}")
    except Exception as e:
        print(f"⚠️  Unexpected error type: {str(e)}")
    
    print(f"\n{'='*80}")
    print("🎉 COMPREHENSIVE SHARE STATISTICS TESTING COMPLETE")
    print(f"{'='*80}")


async def test_org_selection(linkedin_client: LinkedInClient) -> None:
    """
    Fetches all organization roles for the authenticated member, prompts the user to select one,
    and then tests several organization-level API methods using the selected organization URN.

    Args:
        linkedin_client: An instance of LinkedInClient properly configured with credentials.
    """

    # urn:li:organization:105029503  (KIWIQ AI)
    # urn:li:organization:102995539  (Stealth AI)

    organization_urn = "urn:li:organization:105029503"  # overwrite with stealth AI startup URN!  

    print(f"\n🏢 Using organization: {organization_urn}")
    
    # Run comprehensive share statistics testing
    await test_share_statistics_comprehensive(linkedin_client, organization_urn)
    
    print(f"\n✅ All testing completed!")


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
    await test_org_selection(linkedin_client)

if __name__ == "__main__":
    asyncio.run(main())
