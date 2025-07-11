#!/usr/bin/env python3
"""
Create accounts for all specified users using the AdminClient.

This script creates accounts for a predefined list of users using the KiwiQ AdminClient.
Requires superuser authentication.
"""

import asyncio
import logging
import sys
import os
from typing import List, Dict, Any

# Add the parent directory to the path so we can import kiwi_client
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kiwi_client.admin_client import AdminClient
from kiwi_client.auth_client import AuthenticatedClient, AuthenticationError
from kiwi_client.schemas.auth_schemas import UserReadWithSuperuserStatus

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# User data to create
USERS_TO_CREATE = [
    # {
    #     'email': 'user1@example.com',
    #     'password': 'SecurePassword#123',
    #     'full_name': 'Alejandra',
    #     'is_verified': True,
    #     'is_superuser': False
    # },
    # {
    #     'email': 'user2@example.com',
    #     'password': 'SecurePassword#123',
    #     'full_name': 'Test User',
    #     'is_verified': True,
    #     'is_superuser': False
    # },
    # {
    #     'email': 'user3@example.com',
    #     'password': 'SecurePassword#123',
    #     'full_name': 'Jason',
    #     'is_verified': True,
    #     'is_superuser': False
    # },
    # {
    #     'email': 'user4@example.com',
    #     'password': 'SecurePassword#123',
    #     'full_name': 'Thomas',
    #     'is_verified': True,
    #     'is_superuser': False
    # },
    # {
    #     'email': 'user5@example.com',
    #     'password': 'SecurePassword#123',
    #     'full_name': 'Damon',
    #     'is_verified': True,
    #     'is_superuser': False
    # },
    # {
    #     'email': 'user6@example.com',
    #     'password': 'SecurePassword#123',
    #     'full_name': 'Mahak',
    #     'is_verified': True,
    #     'is_superuser': False
    # },
    # {
    #     'email': 'user7@example.com',
    #     'password': 'SecurePassword#123',
    #     'full_name': 'Test User',
    #     'is_verified': True,
    #     'is_superuser': False
    # },
    # {
    #     'email': 'user8@example.com',
    #     'password': 'SecurePassword#123',
    #     'full_name': 'Test User',
    #     'is_verified': True,
    #     'is_superuser': False
    # },
    # {
    #     'email': 'user9@example.com',
    #     'password': 'SecurePassword#123',
    #     'full_name': 'Founder B',
    #     'is_verified': True,
    #     'is_superuser': False
    # },
    # {
    #     'email': 'user10@example.com',
    #     'password': 'SecurePassword#123',
    #     'full_name': 'Gaurav Kumar',
    #     'is_verified': True,
    #     'is_superuser': False
    # }
]


async def create_all_users():
    """Create all specified users using the AdminClient."""
    
    print("=== Creating Accounts for All Users ===")
    print(f"Total users to create: {len(USERS_TO_CREATE)}")
    
    successful_users = []
    failed_users = []
    
    try:
        async with AuthenticatedClient() as auth_client:
            logger.info("Successfully authenticated as admin")
            admin_client = AdminClient(auth_client)
            
            # Create each user
            for i, user_data in enumerate(USERS_TO_CREATE, 1):
                print(f"\n{i}/{len(USERS_TO_CREATE)} - Creating user: {user_data['email']}")
                
                try:
                    created_user = await admin_client.admin_register_user(
                        email=user_data['email'],
                        password=user_data['password'],
                        full_name=user_data['full_name'],
                        is_verified=user_data['is_verified'],
                        is_superuser=user_data['is_superuser']
                    )
                    
                    if created_user:
                        successful_users.append(created_user)
                        print(f"  ✓ Successfully created: {created_user.email}")
                        print(f"    - Name: {created_user.full_name}")
                        print(f"    - ID: {created_user.id}")
                        print(f"    - Verified: {created_user.is_verified}")
                    else:
                        failed_users.append(user_data)
                        print(f"  ✗ Failed to create: {user_data['email']}")
                        
                except Exception as e:
                    failed_users.append(user_data)
                    print(f"  ✗ Error creating {user_data['email']}: {e}")
                    logger.exception(f"Error creating user {user_data['email']}")
            
            # Summary
            print(f"\n=== CREATION SUMMARY ===")
            print(f"Total users processed: {len(USERS_TO_CREATE)}")
            print(f"Successfully created: {len(successful_users)}")
            print(f"Failed to create: {len(failed_users)}")
            
            if successful_users:
                print(f"\n✓ Successfully created users:")
                for user in successful_users:
                    print(f"  - {user.email} ({user.full_name})")
            
            if failed_users:
                print(f"\n✗ Failed to create users:")
                for user_data in failed_users:
                    print(f"  - {user_data['email']} ({user_data['full_name']})")
                    
            return successful_users, failed_users
                    
    except AuthenticationError as e:
        print(f"❌ Authentication failed: {e}")
        print("Make sure you're authenticated as a superuser")
        return [], USERS_TO_CREATE
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logger.exception("Unexpected error during user creation")
        return [], USERS_TO_CREATE


def show_users_to_create():
    """Display the list of users that will be created."""
    print("=== Users to Create ===")
    for i, user_data in enumerate(USERS_TO_CREATE, 1):
        print(f"{i}. {user_data['full_name']} - {user_data['email']}")
    print(f"\nTotal: {len(USERS_TO_CREATE)} users")


async def main():
    """Main function."""
    print("KiwiQ Admin - Create Accounts for All Users")
    print("=" * 50)
    
    # Show what will be created
    show_users_to_create()
    
    # Ask for confirmation
    try:
        confirm = input(f"\nDo you want to create these {len(USERS_TO_CREATE)} users? (y/N): ").strip().lower()
        if confirm not in ['y', 'yes']:
            print("Operation cancelled.")
            return
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        return
    
    # Create the users
    successful, failed = await create_all_users()
    
    # Exit with appropriate code
    if failed:
        print(f"\n⚠️  Some users failed to create. Check the logs above.")
        sys.exit(1)
    else:
        print(f"\n🎉 All users created successfully!")
        sys.exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
