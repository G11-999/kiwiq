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
import logging

# Import our LinkedInClient and required models
from linkedin_integration.client.linkedin_client_member_analytics import LinkedInMemberAnalyticsClient
from kiwi_app.settings import settings


async def test_member_analytics(linkedin_client: LinkedInMemberAnalyticsClient) -> None:
    """
    Tests member analytics APIs using the sample identifiers from curl examples.
    
    Tests include:
    - Member total analytics (various query types)
    - Member daily analytics with date ranges  
    - Single post analytics using specific share URNs
    - Activities API to convert activity URNs to share URNs
    - Convenience methods
    
    Args:
        linkedin_client: An instance of LinkedInMemberAnalyticsClient properly configured with credentials.
    """
    
    # Import the required models
    from linkedin_integration.client.linkedin_client_member_analytics import (
        MemberPostAnalyticsRequest, 
        MemberPostAnalyticsDateRange, 
        DateComponent
    )
    
    print("=== Testing LinkedIn Member Post Analytics ===\n")
    
    # Enable debug logging to see raw API responses
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    
    # Test identifiers from curl examples
    test_share_urns = [
        # "urn:li:share:7340981576178024448",
        "urn:li:share:7288408228378427392"
    ]
    
    test_activity_urns = [
        "urn:li:activity:7288408229108203520", 
        "urn:li:activity:7311079094459252736"
    ]
    
    # Test date range (from curl examples)
    test_date_range = MemberPostAnalyticsDateRange(
        start=DateComponent(year=2024, month=5, day=4),
        end=DateComponent(year=2024, month=5, day=6)
    )
    
    print("1. Testing Activities API (Convert activity URNs to share URNs)")
    print("=" * 60)
    
    try:
        # Test single activity conversion
        print(f"Testing single activity: {test_activity_urns[0]}")
        success, activity = await linkedin_client.get_activity(test_activity_urns[0])
        if success and activity:
            print(f"✅ Single activity conversion successful:")
            print(f"   Activity: {test_activity_urns[0]}")
            print(f"   Share URN: {activity.object}")
            print(f"   Actor: {activity.actor}")
            print(f"   Verb: {activity.verb}")
        else:
            print(f"❌ Single activity conversion failed")
        print()
        
        # Test batch activities conversion
        print(f"Testing batch activities: {test_activity_urns}")
        success, activities = await linkedin_client.get_activities(test_activity_urns)
        if success and activities:
            print(f"✅ Batch activities conversion successful:")
            activity_to_share_map = linkedin_client.extract_share_urns_from_activities(activities)
            for activity_urn, share_urn in activity_to_share_map.items():
                print(f"   {activity_urn} -> {share_urn}")
                # Add converted share URNs to our test list
                if share_urn not in test_share_urns:
                    test_share_urns.append(share_urn)
        else:
            print(f"❌ Batch activities conversion failed")
        print()
        
    except Exception as e:
        print(f"❌ Activities API test failed: {str(e)}")
        print()
    
    print("1.5. Debug Single Analytics Call")
    print("=" * 60)
    
    try:
        print("Testing single member impression analytics (debug)...")
        request = MemberPostAnalyticsRequest.create_member_total_request(
            query_type="IMPRESSION"
        )
        
        # Make the call and catch any errors
        success, analytics = await linkedin_client.get_member_post_analytics(request)
        
        if success and analytics:
            print(f"✅ Debug analytics call successful: {len(analytics.elements)} entries")
            if analytics.elements:
                first_element = analytics.elements[0]
                print(f"   First element - Count: {first_element.count}")
                print(f"   First element - Metric Type: {first_element.metric_type}")
                print(f"   First element - Target Entity: {first_element.target_entity}")
                print(f"   First element - Date Range: {first_element.date_range}")
        else:
            print(f"❌ Debug analytics call failed")
        print()
        
    except Exception as e:
        print(f"❌ Debug analytics call failed with exception: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        print()
    
    print("2. Testing Member Total Analytics (All Query Types)")
    print("=" * 60)
    
    query_types = ["IMPRESSION", "MEMBERS_REACHED", "RESHARE", "REACTION", "COMMENT"]
    
    for query_type in query_types:
        try:
            print(f"Testing member total {query_type}...")
            
            # Test without date range (lifetime)
            request = MemberPostAnalyticsRequest.create_member_total_request(
                query_type=query_type
            )
            success, analytics = await linkedin_client.get_member_post_analytics(request)
            
            if success and analytics:
                print(f"✅ Member total {query_type} (lifetime): {len(analytics.elements)} entries")
                if analytics.elements:
                    for entry in analytics.elements[:2]:  # Show first 2 entries
                        print(f"   Count: {entry.count}, Metric: {entry.metric_type}")
            else:
                print(f"❌ Member total {query_type} (lifetime) failed")
            
            # Test with date range
            if query_type != "MEMBERS_REACHED":  # Skip MEMBERS_REACHED for date range as it might not be supported
                request = MemberPostAnalyticsRequest.create_member_total_request(
                    query_type=query_type,
                    date_range=test_date_range
                )
                success, analytics = await linkedin_client.get_member_post_analytics(request)
                
                if success and analytics:
                    print(f"✅ Member total {query_type} (date range): {len(analytics.elements)} entries")
                else:
                    print(f"❌ Member total {query_type} (date range) failed")
            
            print()
            
        except Exception as e:
            print(f"❌ Member total {query_type} test failed: {str(e)}")
            print()
    
    print("3. Testing Member Daily Analytics")
    print("=" * 60)
    
    # Test daily analytics (excluding MEMBERS_REACHED as it doesn't support DAILY)
    daily_query_types = ["IMPRESSION", "RESHARE", "REACTION", "COMMENT"]
    
    for query_type in daily_query_types:
        try:
            print(f"Testing member daily {query_type}...")
            
            request = MemberPostAnalyticsRequest.create_member_daily_request(
                query_type=query_type,
                date_range=test_date_range
            )
            success, analytics = await linkedin_client.get_member_post_analytics(request)
            
            if success and analytics:
                print(f"✅ Member daily {query_type}: {len(analytics.elements)} entries")
                if analytics.elements:
                    for entry in analytics.elements[:2]:  # Show first 2 entries
                        date_info = ""
                        if entry.date_range:
                            date_info = f" ({entry.date_range.start.year}-{entry.date_range.start.month}-{entry.date_range.start.day})"
                        print(f"   Count: {entry.count}, Metric: {entry.metric_type}{date_info}")
            else:
                print(f"❌ Member daily {query_type} failed")
            
            print()
            
        except Exception as e:
            print(f"❌ Member daily {query_type} test failed: {str(e)}")
            print()
    
    print("4. Testing Single Post Analytics")
    print("=" * 60)
    
    for share_urn in test_share_urns[:2]:  # Test first 2 share URNs
        print(f"Testing analytics for post: {share_urn}")
        
        for query_type in ["IMPRESSION", "REACTION", "COMMENT", "RESHARE"]:
            try:
                # Test total analytics for post
                request = MemberPostAnalyticsRequest.create_post_total_request(
                    entity=share_urn,
                    query_type=query_type
                )
                success, analytics = await linkedin_client.get_member_post_analytics(request)
                
                if success and analytics:
                    print(f"✅ Post total {query_type}: {len(analytics.elements)} entries")
                    if analytics.elements:
                        for entry in analytics.elements:
                            print(f"   Count: {entry.count}, Metric: {entry.metric_type}, Entity: {entry.target_entity}")
                else:
                    print(f"❌ Post total {query_type} failed")
                
                # Test daily analytics for post (except MEMBERS_REACHED)
                if query_type != "MEMBERS_REACHED":
                    request = MemberPostAnalyticsRequest.create_post_daily_request(
                        entity=share_urn,
                        query_type=query_type,
                        date_range=test_date_range
                    )
                    success, analytics = await linkedin_client.get_member_post_analytics(request)
                    
                    if success and analytics:
                        print(f"✅ Post daily {query_type}: {len(analytics.elements)} entries")
                    else:
                        print(f"❌ Post daily {query_type} failed")
                
            except Exception as e:
                print(f"❌ Post {query_type} test failed: {str(e)}")
        
        print()
    
    print("5. Testing Convenience Methods")
    print("=" * 60)
    
    try:
        # Test member impressions convenience methods
        print("Testing member impressions total (lifetime)...")
        success, analytics = await linkedin_client.get_member_impressions_total()
        if success and analytics:
            print(f"✅ Member impressions total (lifetime): {len(analytics.elements)} entries")
        else:
            print(f"❌ Member impressions total (lifetime) failed")
        
        print("Testing member impressions total (date range)...")
        from datetime import datetime
        start_date = datetime(2024, 5, 4)
        end_date = datetime(2024, 5, 6)
        success, analytics = await linkedin_client.get_member_impressions_total(start_date, end_date)
        if success and analytics:
            print(f"✅ Member impressions total (date range): {len(analytics.elements)} entries")
        else:
            print(f"❌ Member impressions total (date range) failed")
        
        print("Testing member impressions daily...")
        success, analytics = await linkedin_client.get_member_impressions_daily(start_date, end_date)
        if success and analytics:
            print(f"✅ Member impressions daily: {len(analytics.elements)} entries")
        else:
            print(f"❌ Member impressions daily failed")
        
        # Test post-specific convenience methods
        if test_share_urns:
            test_share = test_share_urns[0]
            
            print(f"Testing post impressions total for {test_share}...")
            success, analytics = await linkedin_client.get_post_impressions_total(test_share)
            if success and analytics:
                print(f"✅ Post impressions total: {len(analytics.elements)} entries")
            else:
                print(f"❌ Post impressions total failed")
            
            print(f"Testing post reactions total for {test_share}...")
            success, analytics = await linkedin_client.get_post_reactions_total(test_share)
            if success and analytics:
                print(f"✅ Post reactions total: {len(analytics.elements)} entries")
            else:
                print(f"❌ Post reactions total failed")
            
            print(f"Testing post reactions daily for {test_share}...")
            success, analytics = await linkedin_client.get_post_reactions_daily(test_share, start_date, end_date)
            if success and analytics:
                print(f"✅ Post reactions daily: {len(analytics.elements)} entries")
            else:
                print(f"❌ Post reactions daily failed")
        
        print()
        
    except Exception as e:
        print(f"❌ Convenience methods test failed: {str(e)}")
        print()
    
    print("6. Testing Advanced Request Building")
    print("=" * 60)
    
    try:
        # Test creating request from datetime objects
        print("Testing request creation from datetime objects...")
        from datetime import datetime
        start_dt = datetime(2024, 5, 4)
        end_dt = datetime(2024, 5, 6)
        
        request = MemberPostAnalyticsRequest.create_from_datetime_range(
            finder_type="me",
            query_type="IMPRESSION",
            start_date=start_dt,
            end_date=end_dt,
            aggregation="DAILY"
        )
        
        success, analytics = await linkedin_client.get_member_post_analytics(request)
        if success and analytics:
            print(f"✅ Advanced request building: {len(analytics.elements)} entries")
        else:
            print(f"❌ Advanced request building failed")
        
        # Test validation - should fail for MEMBERS_REACHED + DAILY
        print("Testing validation (should fail for MEMBERS_REACHED + DAILY)...")
        try:
            invalid_request = MemberPostAnalyticsRequest(
                finder_type="me",
                query_type="MEMBERS_REACHED",
                aggregation="DAILY",
                date_range=test_date_range
            )
            print(f"❌ Validation failed - should have thrown an error")
        except ValueError as ve:
            print(f"✅ Validation working correctly: {str(ve)}")
        
        print()
        
    except Exception as e:
        print(f"❌ Advanced request building test failed: {str(e)}")
        print()
    
    print("=== Member Analytics Testing Complete ===")
    print("Note: Some tests may fail due to API permissions, rate limits, or data availability.")
    print("Check the detailed error messages above for specific issues.")

    print("7. Testing Pagination Methods")
    print("=" * 60)
    
    try:
        # Test pagination with custom limits
        print("Testing member analytics with custom limits...")
        request = MemberPostAnalyticsRequest.create_member_total_request(
            query_type="IMPRESSION"
        )
        success, analytics = await linkedin_client.get_member_post_analytics_with_limits(
            request=request,
            total_limit=50,
            elements_per_page=10
        )
        if success and analytics:
            print(f"✅ Member analytics with custom limits: {len(analytics.elements)} entries")
        else:
            print(f"❌ Member analytics with custom limits failed")
        
        # Test getting all member analytics
        print("Testing get_all_member_post_analytics...")
        success, analytics = await linkedin_client.get_all_member_post_analytics(request)
        if success and analytics:
            print(f"✅ Get all member analytics: {len(analytics.elements)} entries")
        else:
            print(f"❌ Get all member analytics failed")
        
        # Test enhanced convenience method
        if test_share_urns:
            test_share = test_share_urns[0]
            print(f"Testing get_all_post_analytics for {test_share}...")
            from datetime import datetime
            start_date = datetime(2024, 5, 4)
            end_date = datetime(2024, 5, 6)
            
            success, analytics = await linkedin_client.get_all_post_analytics(
                entity_urn=test_share,
                query_type="IMPRESSION",
                start_date=start_date,
                end_date=end_date,
                aggregation="TOTAL",
                elements_per_page=25
            )
            if success and analytics:
                print(f"✅ Get all post analytics: {len(analytics.elements)} entries")
            else:
                print(f"❌ Get all post analytics failed")
        
        print()
        
    except Exception as e:
        print(f"❌ Pagination methods test failed: {str(e)}")
        print()
    
    # post_id = "urn:li:activity:7288408229108203520"
    # print(quote(post_id, safe=""))
    # return

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
    access_token = settings.LINKEDIN_ACCESS_TOKEN
    # urn:li:person:NxwL-IvR2n
    # urn:li:person:qUvas1UvE2
    version_input = settings.LINKEDIN_API_MEMBER_ANALYTICS_VERSION

    # Instantiate the LinkedInClient with caching disabled for testing.
    linkedin_client = LinkedInMemberAnalyticsClient(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        version=version_input,
        enable_caching=False  # Disable caching to force live API calls for testing
    )

    # Run the organization selection and subsequent tests.
    await test_member_analytics(linkedin_client)

if __name__ == "__main__":
    asyncio.run(main())
