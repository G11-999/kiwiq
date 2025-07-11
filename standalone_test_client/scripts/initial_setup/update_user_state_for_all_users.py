"""
Bulk User State Update Script

This script initializes user state documents for multiple users at once.
It takes a list of users with their LinkedIn URLs and on_behalf_of_user_id,
then creates user state documents and optionally updates onboarded status.

Usage:
    python scripts/update_user_state_for_all_users.py
"""

import asyncio
import logging
import uuid
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

# Import from the parent directory
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.initial_setup.update_user_state import UserStateTestClient
from kiwi_client.auth_client import AuthenticatedClient, AuthenticationError
from kiwi_client.schemas import app_state_schemas as us_schemas

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Enable debug mode for more detailed logging
DEBUG_MODE = True  # Set to True for detailed logging
if DEBUG_MODE:
    logging.getLogger().setLevel(logging.DEBUG)
    logging.getLogger('kiwi_client').setLevel(logging.DEBUG)
    logging.getLogger('httpx').setLevel(logging.INFO)  # Show HTTP requests

@dataclass
class UserInfo:
    """Data class to hold user information for bulk processing."""
    linkedin_url: str
    on_behalf_of_user_id: Optional[str] = None
    name: Optional[str] = None  # Optional name for better logging

class BulkUserStateUpdater:
    """Handles bulk user state initialization and updates."""
    
    def __init__(self, auth_client: AuthenticatedClient):
        self.auth_client = auth_client
        self.user_state_client = UserStateTestClient(auth_client)
        self.results = []
        
    async def process_users(self, users: List[UserInfo], update_onboarded: bool = True) -> Dict[str, Any]:
        """
        Process multiple users to initialize their user state.
        
        Args:
            users: List of UserInfo objects containing user data
            update_onboarded: Whether to update onboarded status to True for all pages
            
        Returns:
            Dictionary with processing results
        """
        logger.info(f"Starting bulk user state processing for {len(users)} users")
        
        successful_users = []
        failed_users = []
        
        for i, user in enumerate(users, 1):
            logger.info(f"Processing user {i}/{len(users)}: {user.name or user.linkedin_url}")
            
            try:
                # Convert string UUID to uuid.UUID if provided
                on_behalf_of_user_id = None
                if user.on_behalf_of_user_id:
                    on_behalf_of_user_id = uuid.UUID(user.on_behalf_of_user_id)
                
                # Step 1: Initialize user state
                logger.info(f"Step 1: Initializing user state for {user.name or user.linkedin_url}")
                init_response = await self.user_state_client.initialize_user_state(
                    linkedin_profile_url=user.linkedin_url,
                    on_behalf_of_user_id=on_behalf_of_user_id
                )
                
                if not init_response or not init_response.docname:
                    logger.error(f"❌ Failed to initialize user state for {user.name or user.linkedin_url}: No response or docname")
                    failed_users.append({
                        "user_info": user,
                        "error": "User state initialization failed - no response or docname",
                        "initialization_success": False
                    })
                    continue
                
                # Step 2: Verify document was actually created by retrieving it
                logger.info(f"Step 2: Verifying document creation for {user.name or user.linkedin_url}")
                verification_response = await self.user_state_client.get_user_state(
                    docname=init_response.docname,
                    on_behalf_of_user_id=on_behalf_of_user_id
                )
                
                if not verification_response or not verification_response.retrieved_states:
                    logger.error(f"❌ Document verification failed for {user.name or user.linkedin_url}: Document not found on server")
                    failed_users.append({
                        "user_info": user,
                        "error": "Document verification failed - document not found on server",
                        "initialization_success": False
                    })
                    continue
                
                logger.info(f"✅ User state initialized and verified for {user.name or user.linkedin_url}. "
                          f"Docname: {init_response.docname}")
                
                user_result = {
                    "user_info": user,
                    "docname": init_response.docname,
                    "initialization_success": True,
                    "verification_success": True,
                    "onboarded_update_success": False
                }
                
                # Step 3: Update onboarded status if requested
                if update_onboarded:
                    logger.info(f"Step 3: Updating onboarded status for {user.name or user.linkedin_url}")
                    onboarded_success = await self._update_onboarded_status(
                        init_response.docname, 
                        on_behalf_of_user_id
                    )
                    user_result["onboarded_update_success"] = onboarded_success
                    
                    if onboarded_success:
                        logger.info(f"✅ Onboarded status updated for {user.name or user.linkedin_url}")
                        
                        # Step 4: Verify onboarded update was successful
                        final_verification = await self.user_state_client.get_user_state(
                            docname=init_response.docname,
                            on_behalf_of_user_id=on_behalf_of_user_id
                        )
                        
                        if final_verification and final_verification.retrieved_states:
                            onboarded_status = final_verification.retrieved_states.get('onboarded', False)
                            logger.info(f"Final onboarded status for {user.name or user.linkedin_url}: {onboarded_status}")
                        
                    else:
                        logger.warning(f"⚠️ Failed to update onboarded status for {user.name or user.linkedin_url}")
                
                successful_users.append(user_result)
                
            except Exception as e:
                logger.error(f"❌ Error processing user {user.name or user.linkedin_url}: {str(e)}")
                logger.exception(f"Full error details for {user.name or user.linkedin_url}:")
                failed_users.append({
                    "user_info": user,
                    "error": str(e),
                    "initialization_success": False
                })
        
        # Summary
        logger.info(f"\n=== BULK PROCESSING SUMMARY ===")
        logger.info(f"Total users processed: {len(users)}")
        logger.info(f"Successful: {len(successful_users)}")
        logger.info(f"Failed: {len(failed_users)}")
        
        if successful_users:
            logger.info("\n✅ Successfully processed users:")
            for result in successful_users:
                user = result["user_info"]
                onboarded_status = "✅ Onboarded" if result.get("onboarded_update_success") else "⚠️ Not onboarded"
                logger.info(f"  - {user.name or user.linkedin_url}: {result['docname']} ({onboarded_status})")
        
        if failed_users:
            logger.info("\n❌ Failed to process users:")
            for result in failed_users:
                user = result["user_info"]
                logger.info(f"  - {user.name or user.linkedin_url}: {result['error']}")
        
        return {
            "total_users": len(users),
            "successful_users": successful_users,
            "failed_users": failed_users,
            "success_count": len(successful_users),
            "failure_count": len(failed_users)
        }
    
    async def _update_onboarded_status(self, docname: str, on_behalf_of_user_id: Optional[uuid.UUID]) -> bool:
        """
        Update all onboarded page statuses to True for a specific user.
        
        Args:
            docname: The document name to update
            on_behalf_of_user_id: The user ID to act on behalf of
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            # List of all onboarded pages that need to be set to True
            onboarded_pages = [
                "page_1_linkedin",
                "page_2_sources", 
                "page_3_goals",
                "page_4_audience",
                "page_5_time",
                "page_6_content_perspectives",
                "page_7_content_beliefs",
                "page_8_content_pillars",
                "page_9_strategy",
                "page_10_dna_summary",
                "page_11_content_style_analysis",
                "page_12_style_test"
            ]
            
            # Create StateUpdate objects for each onboarded page
            updates_to_send = []
            for page in onboarded_pages:
                updates_to_send.append(
                    us_schemas.StateUpdate(
                        keys=["onboarded", page], 
                        update_value=True
                    )
                )
            
            logger.info(f"Sending {len(updates_to_send)} onboarded page updates for docname: {docname}")
            
            # Update user state
            updated_state = await self.user_state_client.update_user_state(
                docname=docname,
                updates=updates_to_send,
                on_behalf_of_user_id=on_behalf_of_user_id
            )
            
            if updated_state is None:
                logger.error(f"Update user state returned None for docname: {docname}")
                return False
            
            logger.info(f"Successfully updated onboarded status for docname: {docname}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating onboarded status for {docname}: {str(e)}")
            logger.exception(f"Full error details for onboarded update {docname}:")
            return False


async def verify_documents_on_server(bulk_updater: BulkUserStateUpdater, successful_users: List[Dict]) -> None:
    """
    Verify that all documents were actually created on the server.
    
    Args:
        bulk_updater: The BulkUserStateUpdater instance
        successful_users: List of successful user results
    """
    logger.info("Verifying documents exist on server...")
    
    try:
        # Use the first user's on_behalf_of_user_id for listing documents
        on_behalf_of_user_id = None
        if successful_users and successful_users[0]['user_info'].on_behalf_of_user_id:
            on_behalf_of_user_id = uuid.UUID(successful_users[0]['user_info'].on_behalf_of_user_id)
        
        # Get all documents for the authenticated user
        all_docs = await bulk_updater.user_state_client.list_user_state_documents(
            on_behalf_of_user_id=on_behalf_of_user_id
        )
        
        if all_docs and all_docs.docnames:
            logger.info(f"Total documents found on server: {len(all_docs.docnames)}")
            logger.info(f"Server documents: {all_docs.docnames}")
            
            # Check each successful user's document
            for user_result in successful_users:
                docname = user_result['docname']
                user_info = user_result['user_info']
                
                if docname in all_docs.docnames:
                    logger.info(f"✅ VERIFIED: {user_info.name or user_info.linkedin_url} - {docname}")
                else:
                    logger.error(f"❌ MISSING: {user_info.name or user_info.linkedin_url} - {docname}")
        else:
            logger.error("❌ No documents found on server or list request failed")
            
    except Exception as e:
        logger.error(f"Error verifying documents on server: {str(e)}")
        logger.exception("Full error details:")


def print_env_update_instructions():
    """
    Print instructions for updating the .env file with the correct TEST_ORG_ID.
    """
    USER_TO_ORG_MAPPING = {
        "Test User": "dc9baf1b-3742-4682-90cd-e383df9d4c08",
        "Test User": "1949d64f-bd0b-485c-b81f-68d27e787e5b", 
        "Test User": "170502af-8c59-4dca-9998-c5268d8a834b",
        "Test User": "03683ae6-05c6-4506-bd9e-f5cea1fed0de",
        "Test User": "c6958a2e-ddd3-44f3-b57a-136bc2d74060"
    }
    
    print("\n" + "="*60)
    print("📝 UPDATE YOUR .env FILE")
    print("="*60)
    print("To run this script, you need to update the TEST_ORG_ID in your .env file")
    print("based on which user's organization context you want to run in:")
    print()
    
    for user_name, org_id in USER_TO_ORG_MAPPING.items():
        print(f"For {user_name}:")
        print(f"  TEST_ORG_ID={org_id}")
        print()
    
    print("IMPORTANT DISTINCTION:")
    print("- TEST_ORG_ID (in .env): Used for X-Active-Org header during authentication")
    print("- on_behalf_of_user_id (in script): Used as parameter in API calls")
    print("- These are DIFFERENT values!")
    print()
    print("="*60)


async def main():
    """Main function to run the bulk user state update process."""
    logger.info("=== BULK USER STATE UPDATE SCRIPT ===")
    
    # =============================================================================
    # USER CONFIGURATION - UPDATE THESE VALUES BEFORE RUNNING
    # =============================================================================
    
    # Organization ID mapping for each user
    # This is used to understand which organization context each user belongs to
    USER_TO_ORG_MAPPING = {
        "Test User": "dc9baf1b-3742-4682-90cd-e383df9d4c08",
        "Test User": "1949d64f-bd0b-485c-b81f-68d27e787e5b", 
        "Test User": "170502af-8c59-4dca-9998-c5268d8a834b",
        "Test User": "03683ae6-05c6-4506-bd9e-f5cea1fed0de",
        "Test User": "c6958a2e-ddd3-44f3-b57a-136bc2d74060"
    }
    
    # Define the list of users to process
    # NOTE: on_behalf_of_user_id is DIFFERENT from the organization ID above
    # on_behalf_of_user_id is used as a parameter in API calls
    # The organization ID above is used for TEST_ORG_ID in .env file
    s = [
        # UserInfo(
        #     linkedin_url="https://www.linkedin.com/in/example-user-1/",
        #     on_behalf_of_user_id="f6bd0245-5b9b-4c45-87c0-bd7b7902c3cc",
        #     name="Test User"
        # )
        # UserInfo(
        #     linkedin_url="https://www.linkedin.com/in/example-user-2/",
        #     on_behalf_of_user_id="ae464205-8b99-42c0-a202-c01bb060a5cc",
        #     name="Test User"
        # )
        # UserInfo(
        #     linkedin_url="https://www.linkedin.com/in/example-user-3/",
        #     on_behalf_of_user_id="39a2fc5b-c7b9-4d3a-81ca-bd1def5922b5",
        #     name="Test User"
        # )
        # UserInfo(
        #     linkedin_url="https://www.linkedin.com/in/example-user-4/",
        #     on_behalf_of_user_id="dbcf00d1-eb23-4165-a349-53da0a3ac9de",
        #     name="Test User"
        # )
        UserInfo(
            linkedin_url="https://www.linkedin.com/in/example-user-5/",
            on_behalf_of_user_id="42aa9f1a-6ad5-468b-bc3d-0b30e02079f8",
            name="Test User"
        )
    ]
    
    # Whether to update onboarded status for all users (set to True to mark all users as onboarded)
    UPDATE_ONBOARDED_STATUS = True
    
    # =============================================================================
    # IMPORTANT: UPDATE .env FILE BEFORE RUNNING
    # =============================================================================
    
    # Print organization mapping for reference
    logger.info("\n=== ORGANIZATION MAPPING ===")
    logger.info("You need to update TEST_ORG_ID in your .env file based on which user's organization context you want to run in:")
    for user_name, org_id in USER_TO_ORG_MAPPING.items():
        logger.info(f"  {user_name}: {org_id}")
    
    # Check current TEST_ORG_ID
    current_test_org_id = os.getenv("TEST_ORG_ID")
    logger.info(f"\nCurrent TEST_ORG_ID in .env: {current_test_org_id}")
    
    # Determine which user's organization context we're running in
    current_user_context = None
    for user_name, org_id in USER_TO_ORG_MAPPING.items():
        if current_test_org_id == org_id:
            current_user_context = user_name
            break
    
    if current_user_context:
        logger.info(f"Running in {current_user_context}'s organization context")
    else:
        logger.warning("⚠️ Current TEST_ORG_ID doesn't match any known user organization!")
        logger.warning("⚠️ Please update TEST_ORG_ID in your .env file to match one of the organizations above")
        
        # Ask user to confirm
        logger.info("\n=== CONTINUE ANYWAY? ===")
        logger.info("The script can still run, but it may not work as expected.")
        
    # =============================================================================
    
    if not users_to_process:
        logger.error("No users defined in users_to_process list. Please add users before running.")
        return
    
    try:
        async with AuthenticatedClient() as auth_client:
            logger.info("Authentication successful.")
            
            # Create the bulk updater
            bulk_updater = BulkUserStateUpdater(auth_client)
            
            # Process all users
            results = await bulk_updater.process_users(
                users=users_to_process,
                update_onboarded=UPDATE_ONBOARDED_STATUS
            )
            
            # Final summary
            logger.info(f"\n=== FINAL RESULTS ===")
            logger.info(f"Successfully processed: {results['success_count']}/{results['total_users']} users")
            
            # Verify documents exist on server
            logger.info(f"\n=== SERVER VERIFICATION ===")
            await verify_documents_on_server(bulk_updater, results['successful_users'])
            
            if results['success_count'] > 0:
                logger.info("✅ Script completed successfully!")
            else:
                logger.warning("⚠️ Script completed but no users were processed successfully.")
                
    except AuthenticationError as e:
        logger.error(f"Authentication Error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.exception("Full error details:")


def create_user_list_template():
    """
    Helper function to create a template for user list configuration.
    Call this function to see the expected format for users_to_process.
    """
    template = """
    # User List Template
    # Copy this format and replace with your actual user data
    
    users_to_process = [
        UserInfo(
            linkedin_url="https://www.linkedin.com/in/user-linkedin-handle/",
            on_behalf_of_user_id="your-organization-uuid-here",  # Optional
            name="User Display Name"  # Optional, for better logging
        ),
        UserInfo(
            linkedin_url="https://www.linkedin.com/in/another-user/",
            on_behalf_of_user_id="your-organization-uuid-here",
            name="Another User"
        ),
        # Add more users as needed...
    ]
    """
    print(template)


if __name__ == "__main__":
    print("Bulk User State Update Script")
    print("=" * 50)
    print("This script will initialize user state for multiple users.")
    print("=" * 50)
    
    # Show env update instructions
    print_env_update_instructions()
    
    print("\n🚀 Script is ready to run with 5 users:")
    print("   - Test User")
    print("   - Test User") 
    print("   - Test User")
    print("   - Test User")
    print("   - Test User")
    print("\nTo run the script:")
    print("   python scripts/update_user_state_for_all_users.py")
    
    # Script is ready to run with the provided user data
    asyncio.run(main())
    
    # Uncomment the line below to see the user list template
    # create_user_list_template()
