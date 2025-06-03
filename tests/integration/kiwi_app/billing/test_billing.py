"""
Comprehensive integration tests for KiwiQ billing system.

This module tests the billing DAOs and services with actual database operations,
including complex scenarios with multiple users, organizations, credit types,
and promotion codes. All test data is created and cleaned up in the database.
"""

import unittest
import uuid
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from decimal import Decimal

# Database and session imports
from db.session import get_async_db_as_manager
from sqlalchemy.ext.asyncio import AsyncSession

# Billing imports
from kiwi_app.billing import crud as billing_crud, models as billing_models, schemas as billing_schemas
from kiwi_app.billing.models import CreditType, SubscriptionStatus, CreditSourceType, PaymentStatus
from kiwi_app.billing.services import BillingService
from kiwi_app.billing.exceptions import (
    InsufficientCreditsException,
    PromotionCodeNotFoundException,
    PromotionCodeExpiredException,
    PromotionCodeExhaustedException,
    PromotionCodeAlreadyUsedException,
    PromotionCodeNotAllowedException
)

# Auth imports for test users and orgs
from kiwi_app.auth import crud as auth_crud, models as auth_models, schemas as auth_schemas
from kiwi_app.auth.services import AuthService
from kiwi_app.auth.utils import datetime_now_utc
from kiwi_app.auth.security import get_password_hash
from kiwi_app.auth.constants import DefaultRoles

# Settings
from kiwi_app.settings import settings


class TestBillingSystem(unittest.IsolatedAsyncioTestCase):
    """
    Comprehensive integration tests for the billing system.

    Tests billing DAOs and services with real database operations,
    covering multiple users, organizations, credit types, and promotion codes.
    """

    # Test identifiers - all prefixed with "test_"
    test_users: List[auth_models.User] = []
    test_orgs: List[auth_models.Organization] = []
    test_promotion_codes: List[billing_models.PromotionCode] = []
    test_subscription_plans: List[billing_models.SubscriptionPlan] = []
    created_entity_ids: Dict[str, List[uuid.UUID]] = {}

    # Test entity naming patterns
    TEST_ORG_NAMES = [
        'test_tech_startup_billing',
        'test_marketing_agency_billing', 
        'test_solo_consultant_billing',
        'test_enterprise_billing'
    ]
    
    TEST_USER_EMAILS = [
        'test_ceo@techstartup-billing-test.com',
        'test_dev@techstartup-billing-test.com', 
        'test_manager@techstartup-billing-test.com',
        'test_owner@marketing-billing-test.com',
        'test_specialist@marketing-billing-test.com',
        'test_consultant@solo-billing-test.com',
        'test_admin@enterprise-billing-test.com',
        'test_user1@enterprise-billing-test.com',
        'test_user2@enterprise-billing-test.com',
        'test_user3@enterprise-billing-test.com'
    ]
    
    TEST_PROMO_CODES = [
        'test_WORKFLOW100_UNLIMITED',
        'test_WEBSEARCH50_LIMITED',
        'test_EXPIRED_DOLLAR25',
        'test_INACTIVE_WORKFLOW200',
        'test_HIGHVALUE_LIMITED2',
        'test_ORG_RESTRICTED_SPECIAL',
        'test_MULTIUSE_PER_ORG'
    ]
    
    TEST_PLAN_PATTERNS = [
        'test_%',  # All test plans
    ]

    # DAOs and Services
    billing_service: BillingService
    auth_service: AuthService
    
    # Individual DAOs for direct testing
    user_dao: auth_crud.UserDAO
    org_dao: auth_crud.OrganizationDAO
    role_dao: auth_crud.RoleDAO
    permission_dao: auth_crud.PermissionDAO
    refresh_token_dao: auth_crud.RefreshTokenDAO
    
    subscription_plan_dao: billing_crud.SubscriptionPlanDAO
    org_subscription_dao: billing_crud.OrganizationSubscriptionDAO
    org_credits_dao: billing_crud.OrganizationCreditsDAO
    org_net_credits_dao: billing_crud.OrganizationNetCreditsDAO
    usage_event_dao: billing_crud.UsageEventDAO
    credit_purchase_dao: billing_crud.CreditPurchaseDAO
    promotion_code_dao: billing_crud.PromotionCodeDAO
    promotion_code_usage_dao: billing_crud.PromotionCodeUsageDAO

    async def asyncSetUp(self):
        """Set up test environment with DAOs, services, and test data."""
        await self._setup_test_environment()
        await self._cleanup_existing_test_entities()
        await self._setup_test_entities()

    async def asyncTearDown(self):
        """Clean up all test data from the database."""
        await self._cleanup_test_entities()

    # --- Dedicated Setup Functions ---

    async def _setup_test_environment(self):
        """Initialize DAOs, services, and entity tracking."""
        print("Setting up test environment...")
        
        # Initialize entity tracking
        self.test_users = []
        self.test_orgs = []
        self.test_promotion_codes = []
        self.test_subscription_plans = []
        self.created_entity_ids = {
            'users': [],
            'organizations': [],
            'promotion_codes': [],
            'subscription_plans': [],
            'organization_subscriptions': [],
            'organization_credits': [],
            'organization_net_credits': [],
            'usage_events': [],
            'credit_purchases': [],
            'promotion_code_usages': []
        }

        # Initialize DAOs
        self.user_dao = auth_crud.UserDAO()
        self.org_dao = auth_crud.OrganizationDAO()
        self.role_dao = auth_crud.RoleDAO()
        self.permission_dao = auth_crud.PermissionDAO()
        self.refresh_token_dao = auth_crud.RefreshTokenDAO()
        
        self.subscription_plan_dao = billing_crud.SubscriptionPlanDAO()
        self.org_subscription_dao = billing_crud.OrganizationSubscriptionDAO()
        self.org_credits_dao = billing_crud.OrganizationCreditsDAO()
        self.org_net_credits_dao = billing_crud.OrganizationNetCreditsDAO()
        self.usage_event_dao = billing_crud.UsageEventDAO()
        self.credit_purchase_dao = billing_crud.CreditPurchaseDAO()
        self.promotion_code_dao = billing_crud.PromotionCodeDAO()
        self.promotion_code_usage_dao = billing_crud.PromotionCodeUsageDAO()

        # Initialize services
        self.auth_service = AuthService(
            user_dao=self.user_dao,
            org_dao=self.org_dao,
            role_dao=self.role_dao,
            permission_dao=self.permission_dao,
            refresh_token_dao=self.refresh_token_dao
        )
        
        self.billing_service = BillingService(
            subscription_plan_dao=self.subscription_plan_dao,
            org_subscription_dao=self.org_subscription_dao,
            org_credits_dao=self.org_credits_dao,
            org_net_credits_dao=self.org_net_credits_dao,
            usage_event_dao=self.usage_event_dao,
            credit_purchase_dao=self.credit_purchase_dao,
            promotion_code_dao=self.promotion_code_dao,
            promotion_code_usage_dao=self.promotion_code_usage_dao
        )
        
        print("Test environment setup completed.")

    async def _setup_test_entities(self):
        """Create all test entities (users, orgs, promotion codes)."""
        print("Creating test entities...")
        await self._create_test_users_and_orgs()
        await self._create_test_promotion_codes()
        print("Test entities created successfully.")

    # --- Dedicated Cleanup Functions ---

    async def _cleanup_test_entities(self):
        """Clean up all test entities in the correct order."""
        print("Starting cleanup of test entities...")
        
        async with get_async_db_as_manager() as db:
            try:
                # Get all test user and org IDs for billing cleanup
                test_user_ids = [user.id for user in self.test_users if user and user.id]
                test_org_ids = [org.id for org in self.test_orgs if org and org.id]
                
                # Clean up billing entities first (in dependency order)
                await self._cleanup_billing_entities_for_users_and_orgs(db, test_user_ids, test_org_ids)
                
                # Clean up tracked entities in reverse dependency order
                await self._cleanup_tracked_entities(db)
                
                # Clean up test promotion codes
                await self._cleanup_test_promotion_codes(db)
                
                # Clean up test users
                await self._cleanup_test_users(db)
                
                # Clean up test organizations (last)
                await self._cleanup_test_organizations(db)

                await db.commit()
                
            except Exception as e:
                print(f"Error during cleanup, rolling back: {e}")
                await db.rollback()
        
        # Reset tracking lists
        self._reset_test_entity_tracking()
        print("Test entities cleanup completed.")

    async def _cleanup_existing_test_entities(self):
        """Clean up any existing test entities from previous runs."""
        print("Cleaning up any existing test entities from previous runs...")
        
        async with get_async_db_as_manager() as db:
            try:
                # Get user and org IDs for cleanup
                test_user_ids = []
                test_org_ids = []
                
                for email in self.TEST_USER_EMAILS:
                    try:
                        user = await self.user_dao.get_by_email(db, email=email)
                        if user:
                            test_user_ids.append(user.id)
                    except Exception as e:
                        print(f"Error finding user {email}: {e}")
                
                for org_name in self.TEST_ORG_NAMES:
                    try:
                        org = await self.org_dao.get_by_name(db, name=org_name)
                        if org:
                            test_org_ids.append(org.id)
                    except Exception as e:
                        print(f"Error finding org {org_name}: {e}")
                
                # Clean up billing entities first
                await self._cleanup_billing_entities_for_users_and_orgs(db, test_user_ids, test_org_ids)
                
                # Clean up test subscription plans with pattern matching
                await self._cleanup_test_subscription_plans_by_pattern(db)
                
                # Clean up test promotion codes
                await self._cleanup_existing_test_promotion_codes(db)
                
                # Clean up test users 
                await self._cleanup_existing_test_users(db)
                
                # Clean up test organizations 
                await self._cleanup_existing_test_organizations(db)
                
                await db.commit()
                
            except Exception as e:
                print(f"Error during existing entity cleanup, rolling back: {e}")
                await db.rollback()

        print("Cleanup of existing test entities completed.")

    # --- Specific Cleanup Helper Functions ---

    async def _cleanup_billing_entities_for_users_and_orgs(
        self, 
        db: AsyncSession, 
        user_ids: List[uuid.UUID], 
        org_ids: List[uuid.UUID]
    ):
        """Clean up all billing entities that reference the given user and org IDs."""
        if not user_ids and not org_ids:
            return
        
        try:
            from sqlalchemy import delete as sql_delete
            
            # 1. Delete usage events
            for user_id in user_ids:
                try:
                    delete_stmt = sql_delete(billing_models.UsageEvent).where(billing_models.UsageEvent.user_id == user_id)
                    result = await db.execute(delete_stmt)
                    if result.rowcount > 0:
                        print(f"Deleted {result.rowcount} usage events for user {user_id}")
                except Exception as e:
                    print(f"Error deleting usage events for user {user_id}: {e}")
            
            for org_id in org_ids:
                try:
                    delete_stmt = sql_delete(billing_models.UsageEvent).where(billing_models.UsageEvent.org_id == org_id)
                    result = await db.execute(delete_stmt)
                    if result.rowcount > 0:
                        print(f"Deleted {result.rowcount} usage events for org {org_id}")
                except Exception as e:
                    print(f"Error deleting usage events for org {org_id}: {e}")
            
            # 2. Delete promotion code usages
            for user_id in user_ids:
                try:
                    delete_stmt = sql_delete(billing_models.PromotionCodeUsage).where(billing_models.PromotionCodeUsage.user_id == user_id)
                    result = await db.execute(delete_stmt)
                    if result.rowcount > 0:
                        print(f"Deleted {result.rowcount} promotion code usages for user {user_id}")
                except Exception as e:
                    print(f"Error deleting promotion code usages for user {user_id}: {e}")
            
            for org_id in org_ids:
                try:
                    delete_stmt = sql_delete(billing_models.PromotionCodeUsage).where(billing_models.PromotionCodeUsage.org_id == org_id)
                    result = await db.execute(delete_stmt)
                    if result.rowcount > 0:
                        print(f"Deleted {result.rowcount} promotion code usages for org {org_id}")
                except Exception as e:
                    print(f"Error deleting promotion code usages for org {org_id}: {e}")
            
            # 3. Delete credit purchases
            for user_id in user_ids:
                try:
                    delete_stmt = sql_delete(billing_models.CreditPurchase).where(billing_models.CreditPurchase.user_id == user_id)
                    result = await db.execute(delete_stmt)
                    if result.rowcount > 0:
                        print(f"Deleted {result.rowcount} credit purchases for user {user_id}")
                except Exception as e:
                    print(f"Error deleting credit purchases for user {user_id}: {e}")
            
            for org_id in org_ids:
                try:
                    delete_stmt = sql_delete(billing_models.CreditPurchase).where(billing_models.CreditPurchase.org_id == org_id)
                    result = await db.execute(delete_stmt)
                    if result.rowcount > 0:
                        print(f"Deleted {result.rowcount} credit purchases for org {org_id}")
                except Exception as e:
                    print(f"Error deleting credit purchases for org {org_id}: {e}")
            
            # 4. Delete organization net credits
            for org_id in org_ids:
                try:
                    delete_stmt = sql_delete(billing_models.OrganizationNetCredits).where(billing_models.OrganizationNetCredits.org_id == org_id)
                    result = await db.execute(delete_stmt)
                    if result.rowcount > 0:
                        print(f"Deleted {result.rowcount} org net credits for org {org_id}")
                except Exception as e:
                    print(f"Error deleting org net credits for org {org_id}: {e}")
            
            # 5. Delete organization credits
            for org_id in org_ids:
                try:
                    delete_stmt = sql_delete(billing_models.OrganizationCredits).where(billing_models.OrganizationCredits.org_id == org_id)
                    result = await db.execute(delete_stmt)
                    if result.rowcount > 0:
                        print(f"Deleted {result.rowcount} org credits for org {org_id}")
                except Exception as e:
                    print(f"Error deleting org credits for org {org_id}: {e}")
            
            # 6. Delete organization subscriptions
            for org_id in org_ids:
                try:
                    delete_stmt = sql_delete(billing_models.OrganizationSubscription).where(billing_models.OrganizationSubscription.org_id == org_id)
                    result = await db.execute(delete_stmt)
                    if result.rowcount > 0:
                        print(f"Deleted {result.rowcount} org subscriptions for org {org_id}")
                except Exception as e:
                    print(f"Error deleting org subscriptions for org {org_id}: {e}")
                    
            await db.commit()
            print("Billing entities cleanup completed successfully")
            
        except Exception as e:
            print(f"Error during billing entities cleanup: {e}")
            await db.rollback()
            raise

    async def _cleanup_tracked_entities(self, db: AsyncSession):
        """Clean up entities tracked in created_entity_ids."""
        # Clean up in reverse dependency order
        cleanup_order = [
            'usage_events',
            'promotion_code_usages', 
            'credit_purchases',
            'organization_net_credits',
            'organization_credits',
            'organization_subscriptions',
            'subscription_plans'
        ]
        
        dao_map = {
            'usage_events': self.usage_event_dao,
            'promotion_code_usages': self.promotion_code_usage_dao,
            'credit_purchases': self.credit_purchase_dao,
            'organization_net_credits': self.org_net_credits_dao,
            'organization_credits': self.org_credits_dao,
            'organization_subscriptions': self.org_subscription_dao,
            'subscription_plans': self.subscription_plan_dao
        }
        
        for entity_type in cleanup_order:
            for entity_id in self.created_entity_ids.get(entity_type, []):
                try:
                    dao = dao_map[entity_type]
                    await dao.remove(db, id=entity_id)
                    print(f"Cleaned tracked {entity_type[:-1]} {entity_id}")
                except Exception as e:
                    print(f"Error cleaning tracked {entity_type[:-1]} {entity_id}: {e}")

    async def _cleanup_test_subscription_plans_by_pattern(self, db: AsyncSession):
        """Clean up test subscription plans using pattern matching."""
        try:
            from sqlalchemy import text
            for pattern in self.TEST_PLAN_PATTERNS:
                delete_stmt = text("DELETE FROM kiwiq_billing_subscription_plan WHERE name LIKE :pattern")
                result = await db.execute(delete_stmt, {"pattern": pattern})
                if result.rowcount > 0:
                    print(f"Deleted {result.rowcount} subscription plans matching pattern '{pattern}'")
        except Exception as e:
            print(f"Error cleaning subscription plans: {e}")

    async def _cleanup_existing_test_promotion_codes(self, db: AsyncSession):
        """Clean up existing test promotion codes."""
        for code in self.TEST_PROMO_CODES:
            try:
                promo = await self.promotion_code_dao.get_by_code(db, code=code)
                if promo:
                    print(f"Found existing test promo code: {code}, deleting...")
                    await self.promotion_code_dao.remove(db, id=promo.id)
            except Exception as e:
                print(f"Error cleaning promo code {code}: {e}")

    async def _cleanup_test_promotion_codes(self, db: AsyncSession):
        """Clean up test promotion codes."""
        for entity_id in self.created_entity_ids.get('promotion_codes', []):
            try:
                await self.promotion_code_dao.remove(db, id=entity_id)
                print(f"Cleaned test promotion code {entity_id}")
            except Exception as e:
                print(f"Error cleaning promotion code {entity_id}: {e}")

    async def _cleanup_existing_test_users(self, db: AsyncSession):
        """Clean up existing test users."""
        for email in self.TEST_USER_EMAILS:
            try:
                user = await self.user_dao.get_by_email(db, email=email)
                if user:
                    print(f"Found existing test user: {email}, deleting...")
                    await self.user_dao.remove(db, id=user.id)
            except Exception as e:
                print(f"Error cleaning user {email}: {e}")

    async def _cleanup_test_users(self, db: AsyncSession):
        """Clean up test users."""
        for entity_id in self.created_entity_ids.get('users', []):
            try:
                user = await self.user_dao.get(db, id=entity_id)
                if user:
                    await self.user_dao.remove(db, id=entity_id)
                    print(f"Cleaned test user {entity_id}")
            except Exception as e:
                print(f"Error cleaning user {entity_id}: {e}")

    async def _cleanup_existing_test_organizations(self, db: AsyncSession):
        """Clean up existing test organizations."""
        for org_name in self.TEST_ORG_NAMES:
            try:
                org = await self.org_dao.get_by_name(db, name=org_name)
                if org:
                    print(f"Found existing test org: {org_name}, deleting...")
                    await self.org_dao.remove(db, id=org.id)
            except Exception as e:
                print(f"Error cleaning org {org_name}: {e}")

    async def _cleanup_test_organizations(self, db: AsyncSession):
        """Clean up test organizations."""
        for entity_id in self.created_entity_ids.get('organizations', []):
            try:
                org = await self.org_dao.get(db, id=entity_id)
                if org:
                    await self.org_dao.remove(db, id=entity_id)
                    print(f"Cleaned test organization {entity_id}")
            except Exception as e:
                print(f"Error cleaning organization {entity_id}: {e}")

    def _reset_test_entity_tracking(self):
        """Reset all test entity tracking lists."""
        self.test_users = []
        self.test_orgs = []
        self.test_promotion_codes = []
        self.test_subscription_plans = []
        self.created_entity_ids = {key: [] for key in self.created_entity_ids.keys()}

    # --- Test Entity Creation Functions ---

    async def _create_test_users_and_orgs(self):
        """Create test users and organizations for testing."""
        test_data = [
            # Org 1: Tech startup with 3 users
            {
                'org_name': self.TEST_ORG_NAMES[0],
                'users': [
                    {'email': self.TEST_USER_EMAILS[0], 'full_name': 'Test Tech CEO', 'is_superuser': False},
                    {'email': self.TEST_USER_EMAILS[1], 'full_name': 'Test Tech Developer', 'is_superuser': False},
                    {'email': self.TEST_USER_EMAILS[2], 'full_name': 'Test Tech Manager', 'is_superuser': False}
                ]
            },
            # Org 2: Marketing agency with 2 users
            {
                'org_name': self.TEST_ORG_NAMES[1],
                'users': [
                    {'email': self.TEST_USER_EMAILS[3], 'full_name': 'Test Marketing Owner', 'is_superuser': False},
                    {'email': self.TEST_USER_EMAILS[4], 'full_name': 'Test Marketing Specialist', 'is_superuser': False}
                ]
            },
            # Org 3: Solo consultant (1 user)
            {
                'org_name': self.TEST_ORG_NAMES[2],
                'users': [
                    {'email': self.TEST_USER_EMAILS[5], 'full_name': 'Test Solo Consultant', 'is_superuser': False}
                ]
            },
            # Org 4: Enterprise (4 users)
            {
                'org_name': self.TEST_ORG_NAMES[3],
                'users': [
                    {'email': self.TEST_USER_EMAILS[6], 'full_name': 'Test Enterprise Admin', 'is_superuser': False},
                    {'email': self.TEST_USER_EMAILS[7], 'full_name': 'Test Enterprise User 1', 'is_superuser': False},
                    {'email': self.TEST_USER_EMAILS[8], 'full_name': 'Test Enterprise User 2', 'is_superuser': False},
                    {'email': self.TEST_USER_EMAILS[9], 'full_name': 'Test Enterprise User 3', 'is_superuser': False}
                ]
            }
        ]

        async with get_async_db_as_manager() as db:
            # Get admin role
            admin_role = await self.role_dao.get_by_name(db, name=DefaultRoles.ADMIN)
            if not admin_role:
                raise Exception("Admin role not found. Please run auth setup.")

            for org_data in test_data:
                try:
                    # Create organization
                    org_create = auth_schemas.OrganizationCreate(name=org_data['org_name'])
                    org = await self.org_dao.create(db=db, obj_in=org_create)
                    self.test_orgs.append(org)
                    self.created_entity_ids['organizations'].append(org.id)
                    print(f"Created test organization: {org.name} (ID: {org.id})")

                    # Create users for this organization
                    for user_data in org_data['users']:
                        try:
                            # Create user
                            user_create = auth_schemas.UserCreate(
                                email=user_data['email'],
                                full_name=user_data['full_name'],
                                password="test_password_123"  # Same password for all test users
                            )
                            user = await self.user_dao.create_user(db=db, user_in=user_create)
                            
                            # Mark as verified for testing
                            await self.user_dao.update(
                                db, 
                                db_obj=user, 
                                obj_in=auth_schemas.UserAdminUpdate(is_verified=True)
                            )
                            
                            self.test_users.append(user)
                            self.created_entity_ids['users'].append(user.id)
                            print(f"Created test user: {user.email} (ID: {user.id})")

                            # Add user to organization with admin role
                            await self.user_dao.add_user_to_org(db=db, user=user, organization=org, role=admin_role)
                            print(f"Added user {user.email} to organization {org.name}")
                            
                        except Exception as e:
                            print(f"Error creating user {user_data['email']}: {e}")
                            continue

                except Exception as e:
                    print(f"Error creating test org/users for {org_data['org_name']}: {e}")
                    await db.rollback()
                    raise

    async def _create_test_promotion_codes(self):
        """Create various promotion codes for testing different scenarios."""
        promo_codes_data = [
            # Active unlimited workflow credits promo
            {
                'code': self.TEST_PROMO_CODES[0],  # test_WORKFLOW100_UNLIMITED
                'description': 'Test unlimited use workflow credits promotion',
                'credit_type': CreditType.WORKFLOWS,
                'credits_amount': 100.0,
                'max_uses': None,  # Unlimited
                'max_uses_per_org': 1,
                'expires_at': datetime_now_utc() + timedelta(days=30),
                'is_active': True,
                'granted_credits_expire_days': 60
            },
            # Limited use web searches promo
            {
                'code': self.TEST_PROMO_CODES[1],  # test_WEBSEARCH50_LIMITED
                'description': 'Test limited use web search credits',
                'credit_type': CreditType.WEB_SEARCHES,
                'credits_amount': 50.0,
                'max_uses': 10,  # Only 10 total uses
                'max_uses_per_org': 1,
                'expires_at': datetime_now_utc() + timedelta(days=15),
                'is_active': True,
                'granted_credits_expire_days': 30
            },
            # Expired dollar credits promo
            {
                'code': self.TEST_PROMO_CODES[2],  # test_EXPIRED_DOLLAR25
                'description': 'Test expired dollar credits promotion',
                'credit_type': CreditType.DOLLAR_CREDITS,
                'credits_amount': 25.0,  # $25 in dollars
                'max_uses': 5,
                'max_uses_per_org': 1,
                'expires_at': datetime_now_utc() - timedelta(days=1),  # Expired
                'is_active': True,
                'granted_credits_expire_days': 90
            },
            # Inactive workflow promo
            {
                'code': self.TEST_PROMO_CODES[3],  # test_INACTIVE_WORKFLOW200
                'description': 'Test inactive workflow promotion',
                'credit_type': CreditType.WORKFLOWS,
                'credits_amount': 200.0,
                'max_uses': 100,
                'max_uses_per_org': 2,
                'expires_at': datetime_now_utc() + timedelta(days=60),
                'is_active': False,  # Inactive
                'granted_credits_expire_days': 45
            },
            # High-value limited promo for testing exhaustion
            {
                'code': self.TEST_PROMO_CODES[4],  # test_HIGHVALUE_LIMITED2
                'description': 'Test high value limited to 2 total uses',
                'credit_type': CreditType.WORKFLOWS,
                'credits_amount': 500.0,
                'max_uses': 2,  # Very limited
                'max_uses_per_org': 1,
                'expires_at': datetime_now_utc() + timedelta(days=45),
                'is_active': True,
                'granted_credits_expire_days': 30
            },
            # Org-restricted promo (only for first test org)
            {
                'code': self.TEST_PROMO_CODES[5],  # test_ORG_RESTRICTED_SPECIAL
                'description': 'Test special promo for specific organization only',
                'credit_type': CreditType.WEB_SEARCHES,
                'credits_amount': 75.0,
                'max_uses': 5,
                'max_uses_per_org': 1,
                'expires_at': datetime_now_utc() + timedelta(days=20),
                'is_active': True,
                'allowed_org_ids': None,  # Will be set after orgs are created
                'granted_credits_expire_days': 40
            },
            # Multiple use per org promo
            {
                'code': self.TEST_PROMO_CODES[6],  # test_MULTIUSE_PER_ORG
                'description': 'Test multiple uses allowed per organization',
                'credit_type': CreditType.DOLLAR_CREDITS,
                'credits_amount': 10.0,  # $10 in dollars
                'max_uses': 50,
                'max_uses_per_org': 3,  # Each org can use 3 times
                'expires_at': datetime_now_utc() + timedelta(days=25),
                'is_active': True,
                'granted_credits_expire_days': 35
            }
        ]

        async with get_async_db_as_manager() as db:
            for promo_data in promo_codes_data:
                try:
                    # Handle org restriction - set to first test org if this is the restricted promo
                    if promo_data['code'] == self.TEST_PROMO_CODES[5] and self.test_orgs:  # test_ORG_RESTRICTED_SPECIAL
                        promo_data['allowed_org_ids'] = [str(self.test_orgs[0].id)]

                    # Create promotion code
                    promo_create = billing_schemas.PromotionCodeCreate(**promo_data)
                    promo_code = await self.promotion_code_dao.create(db=db, obj_in=promo_create)
                    
                    self.test_promotion_codes.append(promo_code)
                    self.created_entity_ids['promotion_codes'].append(promo_code.id)
                    print(f"Created test promotion code: {promo_code.code} (ID: {promo_code.id})")

                except Exception as e:
                    print(f"Error creating promotion code {promo_data['code']}: {e}")
                    await db.rollback()
                    raise

    # --- Helper Functions for Tests ---

    def _get_test_org(self, index: int = 0) -> auth_models.Organization:
        """Get a test organization by index."""
        if index >= len(self.test_orgs):
            raise IndexError(f"Test org index {index} out of range. Available: {len(self.test_orgs)}")
        return self.test_orgs[index]

    def _get_test_user(self, index: int = 0) -> auth_models.User:
        """Get a test user by index."""
        if index >= len(self.test_users):
            raise IndexError(f"Test user index {index} out of range. Available: {len(self.test_users)}")
        return self.test_users[index]

    def _get_test_promo_code(self, code: str):
        """Get a test promotion code by code string (without test_ prefix)."""
        test_code = f"test_{code}"
        for promo_code in self.test_promotion_codes:
            if promo_code.code == test_code:
                return promo_code
        raise ValueError(f"Test promotion code '{test_code}' not found")
    
    async def _get_test_promo_code_fresh(self, db: AsyncSession, code: str):
        """Get a fresh test promotion code from the database by code string (without test_ prefix)."""
        test_code = f"test_{code}"
        promo_code = await self.promotion_code_dao.get_by_code(db, code=test_code)
        if not promo_code:
            raise ValueError(f"Test promotion code '{test_code}' not found in database")
        return promo_code

    # --- Promotion Code DAO Tests ---

    async def test_promotion_code_dao_basic_operations(self):
        """Test basic CRUD operations for promotion codes."""
        async with get_async_db_as_manager() as db:
            # Test get_by_code
            workflow_promo = self._get_test_promo_code('WORKFLOW100_UNLIMITED')
            retrieved_promo = await self.promotion_code_dao.get_by_code(db, code=workflow_promo.code)
            self.assertIsNotNone(retrieved_promo)
            self.assertEqual(retrieved_promo.id, workflow_promo.id)
            self.assertEqual(retrieved_promo.credit_type, CreditType.WORKFLOWS)
            self.assertEqual(retrieved_promo.credits_amount, 100.0)

            # Test get_active_codes
            active_codes = await self.promotion_code_dao.get_active_codes(db)
            active_codes_list = list(active_codes)
            self.assertGreater(len(active_codes_list), 0)
            
            # Check that expired and inactive codes are not included
            active_code_strings = [code.code for code in active_codes_list]
            self.assertIn('test_WORKFLOW100_UNLIMITED', active_code_strings)
            self.assertNotIn('test_EXPIRED_DOLLAR25', active_code_strings)  # Expired

    async def test_promotion_code_dao_usage_eligibility(self):
        """Test promotion code usage eligibility checks."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(0)
            
            # Test eligible code
            workflow_promo = await self._get_test_promo_code_fresh(db, 'WORKFLOW100_UNLIMITED')
            is_eligible, reason = await self.promotion_code_dao.check_usage_eligibility(
                db, workflow_promo, test_org.id
            )
            self.assertTrue(is_eligible)
            self.assertIsNone(reason)

            # Test expired code
            expired_promo = await self._get_test_promo_code_fresh(db, 'EXPIRED_DOLLAR25')
            is_eligible, reason = await self.promotion_code_dao.check_usage_eligibility(
                db, expired_promo, test_org.id
            )
            self.assertFalse(is_eligible)
            self.assertIn("expired", reason.lower())

            # Test inactive code
            inactive_promo = await self._get_test_promo_code_fresh(db, 'INACTIVE_WORKFLOW200')
            is_eligible, reason = await self.promotion_code_dao.check_usage_eligibility(
                db, inactive_promo, test_org.id
            )
            self.assertFalse(is_eligible)
            self.assertIsNotNone(reason)
            self.assertIn("not active", reason.lower())

    async def test_promotion_code_dao_org_restrictions(self):
        """Test organization-restricted promotion codes."""
        async with get_async_db_as_manager() as db:
            restricted_promo = self._get_test_promo_code('ORG_RESTRICTED_SPECIAL')
            allowed_org = self._get_test_org(0)  # First org should be allowed
            restricted_org = self._get_test_org(1)  # Second org should be restricted

            # Test allowed organization
            is_eligible, reason = await self.promotion_code_dao.check_usage_eligibility(
                db, restricted_promo, allowed_org.id
            )
            self.assertTrue(is_eligible)
            self.assertIsNone(reason)

            # Test restricted organization
            is_eligible, reason = await self.promotion_code_dao.check_usage_eligibility(
                db, restricted_promo, restricted_org.id
            )
            self.assertFalse(is_eligible)
            self.assertIn("not allowed", reason.lower())

    async def test_promotion_code_dao_usage_count_tracking(self):
        """Test usage count tracking for promotion codes."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(0)
            test_user = self._get_test_user(0)
            limited_promo = self._get_test_promo_code('HIGHVALUE_LIMITED2')

            # Initial usage count should be 0
            initial_count = await self.promotion_code_dao.get_org_usage_count(
                db, limited_promo.id, test_org.id
            )
            self.assertEqual(initial_count, 0)

            # Create a usage record
            usage = await self.promotion_code_usage_dao.create_usage(
                db=db,
                promo_code_id=limited_promo.id,
                org_id=test_org.id,
                user_id=test_user.id,
                credits_applied=limited_promo.credits_amount
            )
            self.created_entity_ids['promotion_code_usages'].append(usage.id)

            # Usage count should now be 1
            count_after_use = await self.promotion_code_dao.get_org_usage_count(
                db, limited_promo.id, test_org.id
            )
            self.assertEqual(count_after_use, 1)

    # --- Promotion Code Service Tests ---

    async def test_promotion_code_service_successful_application(self):
        """Test successful promotion code application through service."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(0)
            test_user = self._get_test_user(0)
            
            # Apply workflow promotion code
            application = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            result = await self.billing_service.apply_promotion_code(
                db=db,
                org_id=test_org.id,
                user_id=test_user.id,
                code_application=application
            )

            # Verify successful application
            self.assertTrue(result.success)
            self.assertEqual(result.credits_applied, 100.0)
            self.assertEqual(result.credit_type, CreditType.WORKFLOWS)
            self.assertIn("Successfully applied", result.message)

            # Verify credits were added to the organization
            credit_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            workflow_balance = next(
                (balance for balance in credit_balances if balance.credit_type == CreditType.WORKFLOWS),
                None
            )
            self.assertIsNotNone(workflow_balance)
            self.assertEqual(workflow_balance.credits_balance, 100.0)
            self.assertEqual(workflow_balance.credits_granted, 100.0)
            self.assertEqual(workflow_balance.credits_consumed, 0.0)

    async def test_promotion_code_service_multiple_credit_types(self):
        """Test applying promotion codes for different credit types."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(1)  # Use different org
            test_user = self._get_test_user(3)  # Use different user

            # Apply workflow credits
            workflow_app = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            workflow_result = await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=workflow_app
            )

            # Apply web search credits
            websearch_app = billing_schemas.PromotionCodeApply(code='test_WEBSEARCH50_LIMITED')
            websearch_result = await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=websearch_app
            )

            # Verify both applications
            self.assertTrue(workflow_result.success)
            self.assertTrue(websearch_result.success)
            self.assertEqual(workflow_result.credit_type, CreditType.WORKFLOWS)
            self.assertEqual(websearch_result.credit_type, CreditType.WEB_SEARCHES)

            # Check final balances
            credit_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            
            workflow_balance = next(
                (b for b in credit_balances if b.credit_type == CreditType.WORKFLOWS), None
            )
            websearch_balance = next(
                (b for b in credit_balances if b.credit_type == CreditType.WEB_SEARCHES), None
            )

            self.assertIsNotNone(workflow_balance)
            self.assertIsNotNone(websearch_balance)
            self.assertEqual(workflow_balance.credits_balance, 100.0)
            self.assertEqual(websearch_balance.credits_balance, 50.0)

    async def test_promotion_code_service_error_cases(self):
        """Test various error cases when applying promotion codes."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(0)
            test_user = self._get_test_user(0)

            # Test non-existent code
            with self.assertRaises(PromotionCodeNotFoundException):
                await self.billing_service.apply_promotion_code(
                    db=db,
                    org_id=test_org.id,
                    user_id=test_user.id,
                    code_application=billing_schemas.PromotionCodeApply(code='NONEXISTENT_CODE')
                )

            # Test expired code
            with self.assertRaises(PromotionCodeExpiredException):
                await self.billing_service.apply_promotion_code(
                    db=db,
                    org_id=test_org.id,
                    user_id=test_user.id,
                    code_application=billing_schemas.PromotionCodeApply(code='test_EXPIRED_DOLLAR25')
                )

            # Test inactive code
            with self.assertRaises((PromotionCodeNotAllowedException, Exception)) as context:
                await self.billing_service.apply_promotion_code(
                    db=db,
                    org_id=test_org.id,
                    user_id=test_user.id,
                    code_application=billing_schemas.PromotionCodeApply(code='test_INACTIVE_WORKFLOW200')
                )

            # Test org-restricted code with wrong org
            restricted_org = self._get_test_org(1)  # Not the allowed org
            with self.assertRaises(PromotionCodeNotAllowedException):
                await self.billing_service.apply_promotion_code(
                    db=db,
                    org_id=restricted_org.id,
                    user_id=test_user.id,
                    code_application=billing_schemas.PromotionCodeApply(code='test_ORG_RESTRICTED_SPECIAL')
                )

    async def test_promotion_code_service_duplicate_usage_prevention(self):
        """Test that organizations can't use the same promo code multiple times when restricted."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(2)  # Use solo consultant org
            test_user = self._get_test_user(5)  # Solo consultant user

            # First application should succeed
            application = billing_schemas.PromotionCodeApply(code='test_WEBSEARCH50_LIMITED')
            result1 = await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=application
            )
            self.assertTrue(result1.success)

            # Second application should fail
            with self.assertRaises(PromotionCodeAlreadyUsedException):
                await self.billing_service.apply_promotion_code(
                    db=db, org_id=test_org.id, user_id=test_user.id, code_application=application
                )

    async def test_promotion_code_service_multiple_uses_per_org(self):
        """Test promotion codes that allow multiple uses per organization."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(3)  # Enterprise org
            test_user1 = self._get_test_user(6)
            test_user2 = self._get_test_user(7)
            test_user3 = self._get_test_user(8)

            multiuse_application = billing_schemas.PromotionCodeApply(code='test_MULTIUSE_PER_ORG')

            # First use should succeed
            result1 = await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user1.id, code_application=multiuse_application
            )
            self.assertTrue(result1.success)
            self.assertEqual(result1.credits_applied, 10.0)

            # Second use should succeed
            result2 = await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user2.id, code_application=multiuse_application
            )
            self.assertTrue(result2.success)
            self.assertEqual(result2.credits_applied, 10.0)

            # Third use should succeed
            result3 = await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user3.id, code_application=multiuse_application
            )
            self.assertTrue(result3.success)
            self.assertEqual(result3.credits_applied, 10.0)

            # Fourth use should fail (max 3 per org)
            with self.assertRaises(PromotionCodeAlreadyUsedException):
                await self.billing_service.apply_promotion_code(
                    db=db, org_id=test_org.id, user_id=test_user1.id, code_application=multiuse_application
                )

            # Verify total credits granted
            credit_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            dollar_balance = next(
                (b for b in credit_balances if b.credit_type == CreditType.DOLLAR_CREDITS), None
            )
            self.assertIsNotNone(dollar_balance)
            self.assertEqual(dollar_balance.credits_balance, 30.0)  # 3 uses × $10.0

    async def test_promotion_code_service_global_usage_limit(self):
        """Test promotion codes with global usage limits across all organizations."""
        async with get_async_db_as_manager() as db:
            # Use the high-value limited promo that has max_uses=2
            limited_promo_application = billing_schemas.PromotionCodeApply(code='test_HIGHVALUE_LIMITED2')

            # First org uses it
            org1 = self._get_test_org(0)
            user1 = self._get_test_user(0)
            result1 = await self.billing_service.apply_promotion_code(
                db=db, org_id=org1.id, user_id=user1.id, code_application=limited_promo_application
            )
            self.assertTrue(result1.success)

            # Second org uses it
            org2 = self._get_test_org(1)
            user2 = self._get_test_user(3)
            result2 = await self.billing_service.apply_promotion_code(
                db=db, org_id=org2.id, user_id=user2.id, code_application=limited_promo_application
            )
            self.assertTrue(result2.success)

            # Third org should fail (global limit reached)
            org3 = self._get_test_org(2)
            user3 = self._get_test_user(5)
            with self.assertRaises(PromotionCodeExhaustedException):
                await self.billing_service.apply_promotion_code(
                    db=db, org_id=org3.id, user_id=user3.id, code_application=limited_promo_application
                )

    # --- Credit Management and Consumption Tests ---

    async def test_credit_consumption_basic_functionality(self):
        """Test basic credit consumption functionality."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(0)
            test_user = self._get_test_user(0)

            # First, apply a promotion code to get credits
            application = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=application
            )

            # Consume some credits
            consumption_request = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=25.0,
                event_type="workflow_execution",
                metadata={"workflow_id": str(uuid.uuid4()), "execution_time": "120s"}
            )

            result = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=consumption_request
            )

            # Verify consumption result
            self.assertTrue(result.success)
            self.assertEqual(result.credits_consumed, 25.0)
            self.assertEqual(result.remaining_balance, 75.0)
            self.assertFalse(result.is_overage)
            self.assertEqual(result.grace_credits_used, 0.0)

            # Verify balances
            credit_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            workflow_balance = next(
                (b for b in credit_balances if b.credit_type == CreditType.WORKFLOWS), None
            )
            self.assertIsNotNone(workflow_balance)
            self.assertEqual(workflow_balance.credits_balance, 75.0)
            self.assertEqual(workflow_balance.credits_granted, 100.0)
            self.assertEqual(workflow_balance.credits_consumed, 25.0)

    async def test_credit_consumption_insufficient_credits(self):
        """Test credit consumption when insufficient credits are available."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(1)
            test_user = self._get_test_user(3)

            # Apply small amount of credits
            application = billing_schemas.PromotionCodeApply(code='test_WEBSEARCH50_LIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=application
            )

            # Try to consume more credits than available
            consumption_request = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WEB_SEARCHES,
                credits_consumed=75.0,  # More than the 50 available
                event_type="web_search",
                metadata={"query": "test search"}
            )

            with self.assertRaises(InsufficientCreditsException):
                await self.billing_service.consume_credits(
                    db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=consumption_request
                )

    async def test_credit_consumption_with_overage_grace(self):
        """Test credit consumption with overage grace period."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(2)
            test_user = self._get_test_user(5)

            # Apply credits
            application = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=application
            )

            # Consume exactly all credits
            consumption_request1 = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=100.0,
                event_type="workflow_execution",
                metadata={"workflow_id": str(uuid.uuid4())}
            )

            result1 = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=consumption_request1
            )

            self.assertTrue(result1.success)
            self.assertEqual(result1.remaining_balance, 0.0)
            self.assertFalse(result1.is_overage)

            # Try to consume additional credits that should use grace
            consumption_request2 = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=5.0,  # Small overage amount
                event_type="workflow_execution",
                metadata={"workflow_id": str(uuid.uuid4())}
            )

            result2 = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=consumption_request2
            )

            self.assertTrue(result2.success)
            self.assertEqual(result2.remaining_balance, 0.0)
            self.assertTrue(result2.is_overage)
            self.assertEqual(result2.grace_credits_used, 5.0)
            self.assertIsNotNone(result2.warning)

    async def test_credit_consumption_multiple_types_simultaneously(self):
        """Test consuming different types of credits for the same organization."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(3)
            test_user1 = self._get_test_user(6)
            test_user2 = self._get_test_user(7)
            test_user3 = self._get_test_user(8)

            # Apply multiple types of credits
            workflow_app = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user1.id, code_application=workflow_app
            )

            # Apply dollar credits (multiple uses allowed)
            dollar_app = billing_schemas.PromotionCodeApply(code='test_MULTIUSE_PER_ORG')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user2.id, code_application=dollar_app
            )

            # Consume workflow credits
            workflow_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=30.0,
                event_type="workflow_execution",
                metadata={"user_id": str(test_user1.id)}
            )

            # Consume dollar credits
            dollar_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.DOLLAR_CREDITS,
                credits_consumed=2.50,  # $2.50 worth
                event_type="llm_api_call",
                metadata={"user_id": str(test_user3.id), "model": "gpt-4"}
            )

            # Execute both consumptions
            workflow_result = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user1.id, consumption_request=workflow_consumption
            )

            dollar_result = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user3.id, consumption_request=dollar_consumption
            )

            # Verify both succeeded
            self.assertTrue(workflow_result.success)
            self.assertTrue(dollar_result.success)

            # Check final balances
            credit_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            
            workflow_balance = next(
                (b for b in credit_balances if b.credit_type == CreditType.WORKFLOWS), None
            )
            dollar_balance = next(
                (b for b in credit_balances if b.credit_type == CreditType.DOLLAR_CREDITS), None
            )

            self.assertEqual(workflow_balance.credits_balance, 70.0)  # 100 - 30
            self.assertEqual(dollar_balance.credits_balance, 7.50)  # 10.0 - 2.50

    async def test_credit_allocation_and_adjustment_operations(self):
        """Test credit allocation for operations and final adjustments."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(0)
            test_user = self._get_test_user(1)

            # Apply credits first
            application = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=application
            )

            operation_id = str(uuid.uuid4())
            estimated_credits = 40.0
            actual_credits = 35.0  # Less than estimated

            # Allocate credits for operation
            allocation_result = await self.billing_service.allocate_credits_for_operation(
                db=db,
                org_id=test_org.id,
                user_id=test_user.id,
                credit_type=CreditType.WORKFLOWS,
                estimated_credits=estimated_credits,
                operation_id=operation_id,
                metadata={"operation_type": "complex_workflow"}
            )

            self.assertTrue(allocation_result.success)
            self.assertEqual(allocation_result.allocated_credits, estimated_credits)

            # Check balance after allocation
            credit_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            workflow_balance = next(
                (b for b in credit_balances if b.credit_type == CreditType.WORKFLOWS), None
            )
            self.assertEqual(workflow_balance.credits_balance, 60.0)  # 100 - 40 allocated

            # Adjust with actual consumption
            adjustment_result = await self.billing_service.adjust_allocated_credits(
                db=db,
                org_id=test_org.id,
                user_id=test_user.id,
                credit_type=CreditType.WORKFLOWS,
                operation_id=operation_id,
                actual_credits=actual_credits,
                allocated_credits=estimated_credits,
                metadata={"actual_execution_time": "95s"}
            )

            self.assertTrue(adjustment_result.success)
            self.assertTrue(adjustment_result.adjustment_needed)
            self.assertEqual(adjustment_result.credit_difference, -5.0)  # 35 - 40
            self.assertEqual(adjustment_result.adjustment_type, "return")

            # Check final balance (5 credits should be returned)
            final_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            final_workflow_balance = next(
                (b for b in final_balances if b.credit_type == CreditType.WORKFLOWS), None
            )
            self.assertEqual(final_workflow_balance.credits_balance, 65.0)  # 100 - 35 actual

    async def test_usage_events_creation_and_tracking(self):
        """Test that usage events are properly created and tracked."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(1)
            test_user = self._get_test_user(3)

            # Apply credits
            application = billing_schemas.PromotionCodeApply(code='test_WEBSEARCH50_LIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=application
            )

            # Perform several consumption operations
            consumptions = [
                {
                    "credits": 10.0,
                    "event_type": "web_search",
                    "metadata": {"query": "AI trends 2024", "source": "google"}
                },
                {
                    "credits": 15.0,
                    "event_type": "web_search", 
                    "metadata": {"query": "machine learning algorithms", "source": "bing"}
                },
                {
                    "credits": 20.0,
                    "event_type": "web_search",
                    "metadata": {"query": "python best practices", "source": "duckduckgo"}
                }
            ]

            for consumption_data in consumptions:
                consumption_request = billing_schemas.CreditConsumptionRequest(
                    credit_type=CreditType.WEB_SEARCHES,
                    credits_consumed=consumption_data["credits"],
                    event_type=consumption_data["event_type"],
                    metadata=consumption_data["metadata"]
                )

                await self.billing_service.consume_credits(
                    db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=consumption_request
                )

            # Get usage summary
            end_date = datetime_now_utc()
            start_date = end_date - timedelta(hours=1)  # Last hour
            
            usage_summary = await self.billing_service.get_usage_summary(
                db=db, org_id=test_org.id, start_date=start_date, end_date=end_date
            )

            # Verify usage summary
            self.assertEqual(usage_summary.total_events, 3)
            self.assertIn("web_search", usage_summary.events_by_type)
            self.assertEqual(usage_summary.events_by_type["web_search"], 3)
            self.assertEqual(usage_summary.overage_events, 0)

            # Check remaining balance
            websearch_balance = next(
                (b for b in usage_summary.credit_balances if b.credit_type == CreditType.WEB_SEARCHES),
                None
            )
            self.assertIsNotNone(websearch_balance)
            self.assertEqual(websearch_balance.credits_balance, 5.0)  # 50 - 45 consumed
            self.assertEqual(websearch_balance.credits_consumed, 45.0)

    async def test_billing_dashboard_comprehensive_data(self):
        """Test the billing dashboard with comprehensive data across multiple organizations."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(2)
            test_user = self._get_test_user(5)

            # Set up credits and consumption for dashboard testing
            workflow_app = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=workflow_app
            )

            # Consume some credits to create usage history
            consumption_request = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=30.0,
                event_type="dashboard_test_workflow",
                metadata={"test": "billing_dashboard"}
            )

            await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=consumption_request
            )

            # Get billing dashboard
            dashboard = await self.billing_service.get_billing_dashboard(db, test_org.id)

            # Verify dashboard data
            self.assertEqual(dashboard.org_id, test_org.id)
            self.assertIsNotNone(dashboard.credit_balances)
            self.assertGreater(len(dashboard.credit_balances), 0)

            # Find workflow balance
            workflow_balance = next(
                (b for b in dashboard.credit_balances if b.credit_type == CreditType.WORKFLOWS),
                None
            )
            self.assertIsNotNone(workflow_balance)
            self.assertEqual(workflow_balance.credits_balance, 70.0)

            # Check for recent usage
            self.assertIsNotNone(dashboard.recent_usage)
            if dashboard.recent_usage:
                recent_usage_events = [
                    event for event in dashboard.recent_usage 
                    if event.event_type == "dashboard_test_workflow"
                ]
                self.assertGreater(len(recent_usage_events), 0)

    # --- Subscription Plan and Trial Tests ---

    async def test_subscription_plan_creation_and_management(self):
        """Test subscription plan creation with different configurations."""
        async with get_async_db_as_manager() as db:
            # Test plan data
            plan_data = billing_schemas.SubscriptionPlanCreate(
                name="test_professional_plan",
                description="Test professional plan for testing",
                stripe_product_id="prod_test_professional",
                max_seats=5,
                monthly_credits={
                    CreditType.WORKFLOWS.value: 200.0,
                    CreditType.WEB_SEARCHES.value: 1000.0,
                    CreditType.DOLLAR_CREDITS.value: 50.0  # $50
                },
                monthly_price=29.99,  # $29.99
                annual_price=299.99,  # $299.99
                is_trial_eligible=True,
                trial_days=14
            )

            # Create subscription plan
            plan = await self.subscription_plan_dao.create(db=db, obj_in=plan_data)
            self.created_entity_ids['subscription_plans'].append(plan.id)
            
            # Verify plan creation
            self.assertIsNotNone(plan.id)
            self.assertEqual(plan.name, "test_professional_plan")
            self.assertEqual(plan.max_seats, 5)
            self.assertEqual(plan.monthly_credits[CreditType.WORKFLOWS.value], 200.0)
            self.assertEqual(plan.monthly_credits[CreditType.WEB_SEARCHES.value], 1000.0)
            self.assertEqual(plan.monthly_credits[CreditType.DOLLAR_CREDITS.value], 50.0)
            self.assertTrue(plan.is_trial_eligible)
            self.assertEqual(plan.trial_days, 14)

            # Test plan retrieval
            retrieved_plan = await self.subscription_plan_dao.get(db, plan.id)
            self.assertEqual(retrieved_plan.name, plan.name)

            # Test active plans retrieval
            active_plans = await self.subscription_plan_dao.get_active_plans(db)
            plan_ids = [p.id for p in active_plans]
            self.assertIn(plan.id, plan_ids)

    async def test_free_trial_subscription_creation_and_management(self):
        """Test creating and managing free trial subscriptions."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(0)
            test_user = self._get_test_user(0)

            # Create a trial-eligible plan
            plan_data = billing_schemas.SubscriptionPlanCreate(
                name="test_trial_plan",
                description="Test plan with trial support",
                stripe_product_id="prod_trial_test",
                max_seats=3,
                monthly_credits={
                    CreditType.WORKFLOWS.value: 50,
                    CreditType.WEB_SEARCHES.value: 250,
                    CreditType.DOLLAR_CREDITS.value: 10.0  # $10
                },
                monthly_price=9.99,  # $9.99
                annual_price=99.99,  # $99.99
                is_trial_eligible=True,
                trial_days=7
            )

            plan = await self.subscription_plan_dao.create(db=db, obj_in=plan_data)
            self.created_entity_ids['subscription_plans'].append(plan.id)

            # Create trial subscription using proper constructor
            now = datetime_now_utc()
            trial_end = now - timedelta(hours=1)  # Set trial to have ended 1 hour ago to simulate expiration
            
            # Create the subscription model with proper field assignment
            subscription_model = billing_models.OrganizationSubscription(
                org_id=test_org.id,
                plan_id=plan.id,
                stripe_subscription_id="sub_test_trial",
                stripe_customer_id="cus_test_trial",
                status=SubscriptionStatus.TRIAL,
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                seats_count=2,
                is_annual=False,
                trial_start=now,
                trial_end=trial_end,
                is_trial_active=True,
                created_at=now,
                updated_at=now
            )

            subscription = await self.org_subscription_dao.create(db=db, obj_in=subscription_model)
            self.created_entity_ids['organization_subscriptions'].append(subscription.id)

            # Test subscription properties
            self.assertEqual(subscription.status, SubscriptionStatus.TRIAL)
            self.assertTrue(subscription.is_trial_active)
            self.assertIsNotNone(subscription.trial_end)
            self.assertEqual(subscription.seats_count, 2)

            # Test initial credit allocation for trial
            await self.billing_service._allocate_subscription_credits(db, subscription, plan, is_renewal=False)

            # Verify trial credits were allocated
            credit_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            
            workflow_balance = next(b for b in credit_balances if b.credit_type == CreditType.WORKFLOWS)
            websearch_balance = next(b for b in credit_balances if b.credit_type == CreditType.WEB_SEARCHES)
            dollar_balance = next(b for b in credit_balances if b.credit_type == CreditType.DOLLAR_CREDITS)

            self.assertEqual(workflow_balance.credits_balance, 50)
            self.assertEqual(websearch_balance.credits_balance, 250)
            self.assertEqual(dollar_balance.credits_balance, 10.0)

            # Test trial-to-paid transition
            renewal_result = await self.billing_service.process_subscription_renewal(db, subscription)
            
            self.assertTrue(renewal_result["success"])
            self.assertEqual(renewal_result["renewal_type"], "trial_to_paid")

            # Verify subscription status after renewal
            updated_subscription = await self.org_subscription_dao.get(db, subscription.id)
            self.assertFalse(updated_subscription.is_trial_active)
            self.assertEqual(updated_subscription.status, SubscriptionStatus.ACTIVE)

    async def test_subscription_credit_rotation(self):
        """Test subscription credit rotation functionality."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(1)
            test_user = self._get_test_user(3)

            # Create subscription plan
            plan_data = billing_schemas.SubscriptionPlanCreate(
                name="test_rotation_plan",
                description="Test plan for testing credit rotation",
                stripe_product_id="prod_rotation_test",
                max_seats=2,
                monthly_credits={
                    CreditType.WORKFLOWS.value: 100.0,
                    CreditType.WEB_SEARCHES.value: 500.0
                },
                monthly_price=19.99,
                annual_price=199.99,
                is_trial_eligible=False,
                trial_days=0
            )

            plan = await self.subscription_plan_dao.create(db=db, obj_in=plan_data)
            self.created_entity_ids['subscription_plans'].append(plan.id)

            # Create subscription using proper constructor
            now = datetime_now_utc()
            subscription_model = billing_models.OrganizationSubscription(
                org_id=test_org.id,
                plan_id=plan.id,
                stripe_subscription_id="sub_rotation_test",
                stripe_customer_id="cus_rotation_test",
                status=SubscriptionStatus.ACTIVE,
                current_period_start=now - timedelta(days=30),
                current_period_end=now,
                seats_count=1,
                is_annual=False,
                is_trial_active=False,
                created_at=now - timedelta(days=30),
                updated_at=now
            )

            subscription = await self.org_subscription_dao.create(db=db, obj_in=subscription_model)
            self.created_entity_ids['organization_subscriptions'].append(subscription.id)

            # Initial credit allocation
            await self.billing_service._allocate_subscription_credits(db, subscription, plan, is_renewal=False)

            # Consume some credits
            consumption_request = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=30.0,
                event_type="pre_rotation_test",
                metadata={"test": "rotation"}
            )

            await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=consumption_request
            )

            # Check balances before rotation
            balances_before = await self.billing_service.get_credit_balances(db, test_org.id)
            workflow_before = next(b for b in balances_before if b.credit_type == CreditType.WORKFLOWS)
            websearch_before = next(b for b in balances_before if b.credit_type == CreditType.WEB_SEARCHES)
            
            self.assertEqual(workflow_before.credits_balance, 70.0)  # 100 - 30
            self.assertEqual(workflow_before.credits_consumed, 30.0)
            self.assertEqual(websearch_before.credits_balance, 500.0)

            # Test subscription renewal with credit rotation
            new_credits = {
                CreditType.WORKFLOWS: 100.0,
                CreditType.WEB_SEARCHES: 500.0
            }
            new_expires_at = datetime_now_utc() + timedelta(days=30)

            rotation_result = await self.billing_service.rotate_subscription_credits(
                db=db,
                subscription_id=subscription.id,
                new_credits=new_credits,
                new_expires_at=new_expires_at
            )

            # Verify rotation result
            self.assertTrue(rotation_result["success"])
            self.assertEqual(rotation_result["total_expired_credits"], 600.0)  # 100 + 500 total allocated credits
            self.assertEqual(rotation_result["total_added_credits"], 600.0)  # 100 + 500 new

            # Check balances after rotation
            balances_after = await self.billing_service.get_credit_balances(db, test_org.id)
            workflow_after = next(b for b in balances_after if b.credit_type == CreditType.WORKFLOWS)
            websearch_after = next(b for b in balances_after if b.credit_type == CreditType.WEB_SEARCHES)

            # Should have new credits
            self.assertEqual(workflow_after.credits_balance, 100.0)  # Fresh 100 credits
            self.assertEqual(workflow_after.credits_consumed, 0.0)   # Reset consumption
            self.assertEqual(websearch_after.credits_balance, 500.0) # Fresh 500 credits
            self.assertEqual(websearch_after.credits_consumed, 0.0)  # Reset consumption

    async def test_subscription_plan_retrieval_methods(self):
        """Test various subscription plan retrieval methods."""
        async with get_async_db_as_manager() as db:
            # Clean up any existing plans with the same names first
            cleanup_plan_names = ["test_basic_plan", "test_pro_plan", "test_inactive_plan"]
            for plan_name in cleanup_plan_names:
                try:
                    existing_plan = await self.subscription_plan_dao.get_by_name(db, plan_name)
                    if existing_plan:
                        print(f"Found existing plan '{plan_name}' during cleanup, removing...")
                        await self.subscription_plan_dao.remove(db, id=existing_plan.id)
                except Exception as e:
                    print(f"Error cleaning up existing plan '{plan_name}': {e}")
            
            # Create multiple plans with different configurations
            plans_data = [
                {
                    "name": "test_basic_plan",
                    "stripe_product_id": "prod_basic_test",
                    "is_active": True,
                    "is_trial_eligible": True,
                    "monthly_price": 9.99
                },
                {
                    "name": "test_pro_plan", 
                    "stripe_product_id": "prod_pro_test",
                    "is_active": True,
                    "is_trial_eligible": False,
                    "monthly_price": 29.99
                },
                {
                    "name": "test_inactive_plan",
                    "stripe_product_id": "prod_inactive_test",
                    "is_active": False,
                    "is_trial_eligible": True,
                    "monthly_price": 19.99
                }
            ]

            created_plans = []
            for plan_data in plans_data:
                plan_create = billing_schemas.SubscriptionPlanCreate(
                    name=plan_data["name"],
                    description=f"Description for {plan_data['name']}",
                    stripe_product_id=plan_data["stripe_product_id"],
                    max_seats=5,
                    monthly_credits={CreditType.WORKFLOWS.value: 100.0},
                    monthly_price=plan_data["monthly_price"],
                    annual_price=plan_data["monthly_price"] * 10,
                    is_active=plan_data["is_active"],
                    is_trial_eligible=plan_data["is_trial_eligible"]
                )
                
                plan = await self.subscription_plan_dao.create(db=db, obj_in=plan_create)
                created_plans.append(plan)
                self.created_entity_ids['subscription_plans'].append(plan.id)
                
                # Verify the plan was created with correct is_active value
                print(f"Created plan '{plan.name}' with is_active={plan.is_active}")

            # Test get_active_plans
            active_plans = await self.subscription_plan_dao.get_active_plans(db)
            active_plan_names = [p.name for p in active_plans]
            
            # Debug output
            print(f"Active plans found: {active_plan_names}")
            for plan in active_plans:
                if "test_" in plan.name:  # Only show our test plans
                    print(f"  - {plan.name}: is_active={plan.is_active}")
            
            self.assertIn("test_basic_plan", active_plan_names)
            self.assertIn("test_pro_plan", active_plan_names)
            self.assertNotIn("test_inactive_plan", active_plan_names)

            # Test get_trial_eligible_plans
            trial_eligible_plans = await self.subscription_plan_dao.get_trial_eligible_plans(db)
            trial_eligible_names = [p.name for p in trial_eligible_plans]
            self.assertIn("test_basic_plan", trial_eligible_names)
            self.assertNotIn("test_pro_plan", trial_eligible_names)
            self.assertNotIn("test_inactive_plan", trial_eligible_names)  # Inactive plans excluded

            # Test get_by_name
            basic_plan = await self.subscription_plan_dao.get_by_name(db, "test_basic_plan")
            self.assertIsNotNone(basic_plan)
            self.assertEqual(basic_plan.name, "test_basic_plan")

            # Test get_by_stripe_product_id
            pro_plan = await self.subscription_plan_dao.get_by_stripe_product_id(db, "prod_pro_test")
            self.assertIsNotNone(pro_plan)
            self.assertEqual(pro_plan.name, "test_pro_plan")

    async def test_expire_all_organization_credits(self):
        """Test expiring credits across all organizations."""
        async with get_async_db_as_manager() as db:
            # Set up credits for multiple organizations
            orgs_with_credits = [
                self._get_test_org(0),
                self._get_test_org(1),
                self._get_test_org(2)
            ]

            # Apply promotion codes to all test organizations
            for i, org in enumerate(orgs_with_credits):
                user = self._get_test_user(i * 3)  # Use different users
                
                # Apply workflow credits
                workflow_app = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
                await self.billing_service.apply_promotion_code(
                    db=db, org_id=org.id, user_id=user.id, code_application=workflow_app
                )

            # Verify all organizations have credits before expiration
            total_credits_before = 0
            for org in orgs_with_credits:
                balances = await self.billing_service.get_credit_balances(db, org.id)
                workflow_balance = next(b for b in balances if b.credit_type == CreditType.WORKFLOWS)
                total_credits_before += workflow_balance.credits_balance

            self.assertEqual(total_credits_before, 300)  # 100 credits × 3 orgs

            # Test expiration for all organizations
            cutoff_time = datetime_now_utc() + timedelta(days=61)  # Expire all credits
            expiration_result = await self.billing_service.expire_organization_credits(
                db=db, cutoff_datetime=cutoff_time
            )

            # Verify expiration results
            self.assertTrue(expiration_result["success"])
            self.assertGreaterEqual(expiration_result["total_organizations_affected"], 3)  # At least 3, may be more from other tests
            self.assertGreaterEqual(expiration_result["total_expired_credits"], 300)  # At least 300, may be more from other tests
            self.assertGreaterEqual(len(expiration_result["organizations_processed"]), 3)  # At least 3 orgs processed

            # Verify all organizations have zero workflow credits after expiration
            total_credits_after = 0
            for org in orgs_with_credits:
                balances = await self.billing_service.get_credit_balances(db, org.id)
                workflow_balance = next(b for b in balances if b.credit_type == CreditType.WORKFLOWS)
                total_credits_after += workflow_balance.credits_balance

            self.assertEqual(total_credits_after, 0)  # All credits should be expired

    # --- Additional Missing Tests - Edge Cases and Complex Scenarios ---

    async def test_concurrent_credit_consumption_simulation(self):
        """Simulate concurrent credit consumption to test race conditions."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(3)
            test_users = [self._get_test_user(6), self._get_test_user(7), self._get_test_user(8)]

            # Apply credits
            application = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_users[0].id, code_application=application
            )

            # Simulate multiple users consuming credits "simultaneously"
            for i, user in enumerate(test_users):
                consumption_request = billing_schemas.CreditConsumptionRequest(
                    credit_type=CreditType.WORKFLOWS,
                    credits_consumed=20,
                    event_type=f"concurrent_workflow_{i}",
                    metadata={"user_index": i, "simulation": "concurrent_test"}
                )

                result = await self.billing_service.consume_credits(
                    db=db, org_id=test_org.id, user_id=user.id, consumption_request=consumption_request
                )
                self.assertTrue(result.success)

            # Verify final balance is correct (100 - 60 = 40)
            final_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            workflow_balance = next(
                (b for b in final_balances if b.credit_type == CreditType.WORKFLOWS), None
            )
            self.assertEqual(workflow_balance.credits_balance, 40)
            self.assertEqual(workflow_balance.credits_consumed, 60)

    async def test_zero_credit_consumption(self):
        """Test edge case of zero credit consumption."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(0)
            test_user = self._get_test_user(0)

            # Apply credits first
            application = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=application
            )

            # Consume zero credits (edge case)
            consumption_request = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=0,
                event_type="zero_credit_test",
                metadata={"test": "zero_consumption"}
            )

            result = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=consumption_request
            )

            # Should succeed without changing balances
            self.assertTrue(result.success)
            self.assertEqual(result.credits_consumed, 0)
            self.assertEqual(result.remaining_balance, 100)

    async def test_large_credit_consumption(self):
        """Test handling of large credit consumption amounts."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(1)
            test_user = self._get_test_user(3)

            # Apply multiple promotion codes to get substantial credits
            applications = [
                billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED'),
                billing_schemas.PromotionCodeApply(code='test_MULTIUSE_PER_ORG'),  # Dollar credits
            ]

            for app in applications:
                await self.billing_service.apply_promotion_code(
                    db=db, org_id=test_org.id, user_id=test_user.id, code_application=app
                )

            # Large consumption
            large_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=99,  # Almost all credits
                event_type="large_workflow_execution",
                metadata={"size": "enterprise", "duration": "2h"}
            )

            result = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=large_consumption
            )

            self.assertTrue(result.success)
            self.assertEqual(result.credits_consumed, 99)
            self.assertEqual(result.remaining_balance, 1)

    async def test_cross_organization_isolation(self):
        """Test that credit operations are properly isolated between organizations."""
        async with get_async_db_as_manager() as db:
            org1 = self._get_test_org(0)
            org2 = self._get_test_org(1)
            user1 = self._get_test_user(0)
            user2 = self._get_test_user(3)

            # Apply same promotion code to both orgs
            application = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            
            await self.billing_service.apply_promotion_code(
                db=db, org_id=org1.id, user_id=user1.id, code_application=application
            )
            await self.billing_service.apply_promotion_code(
                db=db, org_id=org2.id, user_id=user2.id, code_application=application
            )

            # Consume different amounts in each org
            consumption1 = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=30,
                event_type="org1_workflow",
                metadata={"org": "org1"}
            )

            consumption2 = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=50,
                event_type="org2_workflow",
                metadata={"org": "org2"}
            )

            await self.billing_service.consume_credits(
                db=db, org_id=org1.id, user_id=user1.id, consumption_request=consumption1
            )
            await self.billing_service.consume_credits(
                db=db, org_id=org2.id, user_id=user2.id, consumption_request=consumption2
            )

            # Verify isolation - each org should have different remaining balances
            org1_balances = await self.billing_service.get_credit_balances(db, org1.id)
            org2_balances = await self.billing_service.get_credit_balances(db, org2.id)

            org1_workflow = next(
                (b for b in org1_balances if b.credit_type == CreditType.WORKFLOWS), None
            )
            org2_workflow = next(
                (b for b in org2_balances if b.credit_type == CreditType.WORKFLOWS), None
            )

            self.assertEqual(org1_workflow.credits_balance, 70)  # 100 - 30
            self.assertEqual(org2_workflow.credits_balance, 50)  # 100 - 50
            self.assertNotEqual(org1_workflow.credits_consumed, org2_workflow.credits_consumed)

    async def test_credit_expiration_during_consumption(self):
        """Test credit consumption when credits expire during the operation."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(0)
            test_user = self._get_test_user(0)

            # Apply credits with short expiration
            application = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=application
            )

            # Simulate credit expiration by calling the expiration service with a future cutoff time
            cutoff_time = datetime_now_utc() + timedelta(days=61)  # 61 days from now
            expiration_result = await self.billing_service.expire_organization_credits(
                db=db, org_id=test_org.id, cutoff_datetime=cutoff_time
            )

            # Verify that credits were actually expired
            self.assertTrue(expiration_result["success"])
            self.assertGreater(expiration_result["total_expired_credits"], 0)

            # Try to consume credits after expiration
            consumption_request = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=50,
                event_type="post_expiration_consumption",
                metadata={"test": "expiration_scenario"}
            )

            # Should fail due to insufficient credits
            with self.assertRaises(InsufficientCreditsException):
                await self.billing_service.consume_credits(
                    db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=consumption_request
                )

    async def test_complex_credit_allocation_adjustment_scenarios(self):
        """Test complex credit allocation and adjustment scenarios with edge cases."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(1)
            test_user = self._get_test_user(3)

            # Apply credits
            application = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=application
            )

            # Test 1: Exact allocation and consumption
            operation_id_1 = str(uuid.uuid4())
            allocation_result_1 = await self.billing_service.allocate_credits_for_operation(
                db=db, org_id=test_org.id, user_id=test_user.id,
                credit_type=CreditType.WORKFLOWS, estimated_credits=30,
                operation_id=operation_id_1
            )

            adjustment_result_1 = await self.billing_service.adjust_allocated_credits(
                db=db, org_id=test_org.id, user_id=test_user.id,
                credit_type=CreditType.WORKFLOWS, operation_id=operation_id_1,
                actual_credits=30, allocated_credits=30
            )

            self.assertFalse(adjustment_result_1.adjustment_needed)
            self.assertEqual(adjustment_result_1.adjustment_type, "none")

            # Test 2: Over-estimation (return credits)
            operation_id_2 = str(uuid.uuid4())
            allocation_result_2 = await self.billing_service.allocate_credits_for_operation(
                db=db, org_id=test_org.id, user_id=test_user.id,
                credit_type=CreditType.WORKFLOWS, estimated_credits=25,
                operation_id=operation_id_2
            )

            adjustment_result_2 = await self.billing_service.adjust_allocated_credits(
                db=db, org_id=test_org.id, user_id=test_user.id,
                credit_type=CreditType.WORKFLOWS, operation_id=operation_id_2,
                actual_credits=10, allocated_credits=25
            )

            self.assertTrue(adjustment_result_2.adjustment_needed)
            self.assertEqual(adjustment_result_2.adjustment_type, "return")
            self.assertEqual(adjustment_result_2.credit_difference, -15)

            # Test 3: Under-estimation (consume more credits)
            operation_id_3 = str(uuid.uuid4())
            allocation_result_3 = await self.billing_service.allocate_credits_for_operation(
                db=db, org_id=test_org.id, user_id=test_user.id,
                credit_type=CreditType.WORKFLOWS, estimated_credits=20,
                operation_id=operation_id_3
            )

            adjustment_result_3 = await self.billing_service.adjust_allocated_credits(
                db=db, org_id=test_org.id, user_id=test_user.id,
                credit_type=CreditType.WORKFLOWS, operation_id=operation_id_3,
                actual_credits=35, allocated_credits=20
            )

            self.assertTrue(adjustment_result_3.adjustment_needed)
            self.assertEqual(adjustment_result_3.adjustment_type, "consume")
            self.assertEqual(adjustment_result_3.credit_difference, 15)

    async def test_promotion_code_complex_restrictions_and_limits(self):
        """Test complex promotion code scenarios with various restrictions and limits."""
        async with get_async_db_as_manager() as db:
            # Test scenario 1: Organization-restricted code with different orgs
            restricted_org = self._get_test_org(0)  # Allowed org
            non_restricted_org = self._get_test_org(1)  # Not allowed org
            user1 = self._get_test_user(0)
            user2 = self._get_test_user(3)

            # Apply restricted promo to allowed org - should succeed
            restricted_application = billing_schemas.PromotionCodeApply(code='test_ORG_RESTRICTED_SPECIAL')
            result1 = await self.billing_service.apply_promotion_code(
                db=db, org_id=restricted_org.id, user_id=user1.id, code_application=restricted_application
            )
            self.assertTrue(result1.success)

            # Try to apply same code to non-allowed org - should fail
            with self.assertRaises(PromotionCodeNotAllowedException):
                await self.billing_service.apply_promotion_code(
                    db=db, org_id=non_restricted_org.id, user_id=user2.id, code_application=restricted_application
                )

            # Test scenario 2: Global usage limit exhaustion
            high_value_app = billing_schemas.PromotionCodeApply(code='test_HIGHVALUE_LIMITED2')
            
            # First organization uses it (should succeed)
            org1 = self._get_test_org(2)
            user_org1 = self._get_test_user(5)
            result2 = await self.billing_service.apply_promotion_code(
                db=db, org_id=org1.id, user_id=user_org1.id, code_application=high_value_app
            )
            self.assertTrue(result2.success)

            # Second organization uses it (should succeed)
            org2 = self._get_test_org(3)
            user_org2 = self._get_test_user(6)
            result3 = await self.billing_service.apply_promotion_code(
                db=db, org_id=org2.id, user_id=user_org2.id, code_application=high_value_app
            )
            self.assertTrue(result3.success)

            # Third organization tries to use it (should fail - global limit reached)
            org3 = self._get_test_org(1)  # Using a different org
            user_org3 = self._get_test_user(4)
            with self.assertRaises(PromotionCodeExhaustedException):
                await self.billing_service.apply_promotion_code(
                    db=db, org_id=org3.id, user_id=user_org3.id, code_application=high_value_app
                )

    async def test_multi_credit_type_complex_operations(self):
        """Test complex operations involving multiple credit types simultaneously."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(2)
            test_user = self._get_test_user(5)

            # Apply multiple types of credits
            workflow_app = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            dollar_app = billing_schemas.PromotionCodeApply(code='test_MULTIUSE_PER_ORG')

            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=workflow_app
            )
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=dollar_app
            )

            # Perform concurrent operations on different credit types
            workflow_operations = []
            dollar_operations = []

            # Create multiple allocation operations
            for i in range(3):
                workflow_op_id = f"workflow_op_{i}"
                dollar_op_id = f"dollar_op_{i}"

                # Allocate workflow credits
                workflow_alloc = await self.billing_service.allocate_credits_for_operation(
                    db=db, org_id=test_org.id, user_id=test_user.id,
                    credit_type=CreditType.WORKFLOWS, estimated_credits=20,
                    operation_id=workflow_op_id
                )
                workflow_operations.append((workflow_op_id, 20, 15 + i))  # Varying actual consumption

                # Allocate dollar credits
                dollar_alloc = await self.billing_service.allocate_credits_for_operation(
                    db=db, org_id=test_org.id, user_id=test_user.id,
                    credit_type=CreditType.DOLLAR_CREDITS, estimated_credits=3.0,
                    operation_id=dollar_op_id
                )
                dollar_operations.append((dollar_op_id, 3.0, 2.0 + (i * 0.5)))  # Varying actual consumption

            # Adjust all operations
            for op_id, allocated, actual in workflow_operations:
                await self.billing_service.adjust_allocated_credits(
                    db=db, org_id=test_org.id, user_id=test_user.id,
                    credit_type=CreditType.WORKFLOWS, operation_id=op_id,
                    actual_credits=actual, allocated_credits=allocated
                )

            for op_id, allocated, actual in dollar_operations:
                await self.billing_service.adjust_allocated_credits(
                    db=db, org_id=test_org.id, user_id=test_user.id,
                    credit_type=CreditType.DOLLAR_CREDITS, operation_id=op_id,
                    actual_credits=actual, allocated_credits=allocated
                )

            # Verify final balances
            final_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            
            workflow_balance = next(b for b in final_balances if b.credit_type == CreditType.WORKFLOWS)
            dollar_balance = next(b for b in final_balances if b.credit_type == CreditType.DOLLAR_CREDITS)

            # Workflow: 100 - (15 + 16 + 17) = 52
            self.assertEqual(workflow_balance.credits_balance, 52.0)
            # Dollar: 10.0 - (2.0 + 2.5 + 3.0) = 2.5
            self.assertEqual(dollar_balance.credits_balance, 2.5)

    async def test_credit_expiration_with_active_consumption(self):
        """Test credit expiration scenarios with ongoing consumption."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(3)
            test_user = self._get_test_user(6)

            # Apply credits
            application = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=application
            )

            # Consume some credits first
            consumption_request = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=60,
                event_type="pre_expiration_consumption",
                metadata={"phase": "before_expiration"}
            )

            result = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=consumption_request
            )
            self.assertTrue(result.success)
            self.assertEqual(result.remaining_balance, 40)

            # Simulate expiration by using a future cutoff time (61 days from now)
            cutoff_time = datetime_now_utc() + timedelta(days=61)
            expiration_result = await self.billing_service.expire_organization_credits(
                db=db, org_id=test_org.id, cutoff_datetime=cutoff_time
            )

            # Verify that credits were actually expired
            self.assertTrue(expiration_result["success"])
            self.assertGreater(expiration_result["total_expired_credits"], 0)

            # Check that expiration was handled correctly
            post_expiration_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            workflow_balance = next(b for b in post_expiration_balances if b.credit_type == CreditType.WORKFLOWS)
            
            # After expiration, both granted and consumed should be reduced appropriately
            self.assertEqual(workflow_balance.credits_balance, 0)  # Should be 0 after expiration
            self.assertEqual(workflow_balance.credits_granted, 0)  # All granted credits should be expired
            self.assertEqual(workflow_balance.credits_consumed, 0)  # Consumed should be adjusted down to 0

    async def test_complex_usage_analytics_scenarios(self):
        """Test complex usage analytics with mixed event types and time periods."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(1)
            test_users = [self._get_test_user(3), self._get_test_user(4)]

            # Apply multiple credit types
            applications = [
                billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED'),
                billing_schemas.PromotionCodeApply(code='test_WEBSEARCH50_LIMITED')
            ]

            for app in applications:
                await self.billing_service.apply_promotion_code(
                    db=db, org_id=test_org.id, user_id=test_users[0].id, code_application=app
                )

            # Create diverse usage events
            usage_scenarios = [
                # Workflow events
                {"credit_type": CreditType.WORKFLOWS, "credits": 15.0, "event_type": "complex_workflow", "user_idx": 0},
                {"credit_type": CreditType.WORKFLOWS, "credits": 25.0, "event_type": "simple_workflow", "user_idx": 1},
                {"credit_type": CreditType.WORKFLOWS, "credits": 10.0, "event_type": "test_workflow", "user_idx": 0},
                
                # Web search events
                {"credit_type": CreditType.WEB_SEARCHES, "credits": 8.0, "event_type": "research_search", "user_idx": 1},
                {"credit_type": CreditType.WEB_SEARCHES, "credits": 12.0, "event_type": "fact_check", "user_idx": 0},
                {"credit_type": CreditType.WEB_SEARCHES, "credits": 5.0, "event_type": "quick_lookup", "user_idx": 1},

                # Mixed allocation and adjustment events
                {"credit_type": CreditType.WORKFLOWS, "credits": 0.0, "event_type": "credit_allocation", "user_idx": 0},
                {"credit_type": CreditType.WORKFLOWS, "credits": 20.0, "event_type": "credit_adjustment", "user_idx": 0},
            ]

            for scenario in usage_scenarios:
                consumption_request = billing_schemas.CreditConsumptionRequest(
                    credit_type=scenario["credit_type"],
                    credits_consumed=scenario["credits"],
                    event_type=scenario["event_type"],
                    metadata={
                        "user_index": scenario["user_idx"],
                        "test_scenario": "complex_analytics",
                        "timestamp": datetime_now_utc().isoformat()
                    }
                )

                await self.billing_service.consume_credits(
                    db=db, org_id=test_org.id, user_id=test_users[scenario["user_idx"]].id, 
                    consumption_request=consumption_request
                )

            # Get usage summary
            end_date = datetime_now_utc()
            start_date = end_date - timedelta(hours=1)
            
            usage_summary = await self.billing_service.get_usage_summary(
                db=db, org_id=test_org.id, start_date=start_date, end_date=end_date
            )

            # Verify analytics data
            self.assertEqual(usage_summary.total_events, len(usage_scenarios))
            self.assertIn("complex_workflow", usage_summary.events_by_type)
            self.assertIn("research_search", usage_summary.events_by_type)
            self.assertEqual(usage_summary.overage_events, 0)

            # Verify credit balances reflect consumption
            workflow_balance = next(b for b in usage_summary.credit_balances if b.credit_type == CreditType.WORKFLOWS)
            websearch_balance = next(b for b in usage_summary.credit_balances if b.credit_type == CreditType.WEB_SEARCHES)

            expected_workflow_consumed = 15 + 25 + 10 + 0 + 20  # 70
            expected_websearch_consumed = 8 + 12 + 5  # 25

            self.assertEqual(workflow_balance.credits_consumed, expected_workflow_consumed)
            self.assertEqual(websearch_balance.credits_consumed, expected_websearch_consumed)

    async def test_data_isolation_between_organizations(self):
        """Test comprehensive data isolation between organizations."""
        async with get_async_db_as_manager() as db:
            org1 = self._get_test_org(0)
            org2 = self._get_test_org(1)
            org3 = self._get_test_org(2)

            users = [self._get_test_user(0), self._get_test_user(3), self._get_test_user(5)]

            # Apply same promotion codes to all organizations
            application = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            
            for i, org in enumerate([org1, org2, org3]):
                await self.billing_service.apply_promotion_code(
                    db=db, org_id=org.id, user_id=users[i].id, code_application=application
                )

            # Perform different consumption patterns in each org
            consumption_patterns = [
                {"org": org1, "user": users[0], "amounts": [30, 20, 15]},
                {"org": org2, "user": users[1], "amounts": [50, 10]},
                {"org": org3, "user": users[2], "amounts": [25, 25, 25, 25]}
            ]

            for pattern in consumption_patterns:
                for i, amount in enumerate(pattern["amounts"]):
                    consumption_request = billing_schemas.CreditConsumptionRequest(
                        credit_type=CreditType.WORKFLOWS,
                        credits_consumed=amount,
                        event_type=f"isolation_test_{i}",
                        metadata={"pattern_test": True, "org_id": str(pattern["org"].id)}
                    )

                    await self.billing_service.consume_credits(
                        db=db, org_id=pattern["org"].id, user_id=pattern["user"].id, 
                        consumption_request=consumption_request
                    )

            # Verify isolation - each org should have different balances
            balances = {}
            for org in [org1, org2, org3]:
                org_balances = await self.billing_service.get_credit_balances(db, org.id)
                workflow_balance = next(b for b in org_balances if b.credit_type == CreditType.WORKFLOWS)
                balances[str(org.id)] = workflow_balance

            # Verify expected balances
            self.assertEqual(balances[str(org1.id)].credits_balance, 35)  # 100 - 65
            self.assertEqual(balances[str(org2.id)].credits_balance, 40)  # 100 - 60
            self.assertEqual(balances[str(org3.id)].credits_balance, 0)   # 100 - 100

            # Verify that no organization can see others' data
            for org in [org1, org2, org3]:
                dashboard = await self.billing_service.get_billing_dashboard(db, org.id)
                
                # Ensure all usage events belong to this organization
                for event in dashboard.recent_usage:
                    self.assertEqual(event.org_id, org.id)

    async def test_edge_case_promotion_code_timing(self):
        """Test edge cases related to promotion code timing and expiration."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(0)
            test_user = self._get_test_user(0)

            # Test applying expired promotion code
            expired_application = billing_schemas.PromotionCodeApply(code='test_EXPIRED_DOLLAR25')
            with self.assertRaises(PromotionCodeExpiredException):
                await self.billing_service.apply_promotion_code(
                    db=db, org_id=test_org.id, user_id=test_user.id, code_application=expired_application
                )

            # Test applying inactive promotion code
            inactive_application = billing_schemas.PromotionCodeApply(code='test_INACTIVE_WORKFLOW200')
            with self.assertRaises(PromotionCodeNotAllowedException):
                await self.billing_service.apply_promotion_code(
                    db=db, org_id=test_org.id, user_id=test_user.id, code_application=inactive_application
                )

    async def test_zero_and_negative_edge_cases(self):
        """Test edge cases involving zero and negative values."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(1)
            test_user = self._get_test_user(3)

            # Apply some credits first
            application = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=application
            )

            # Test zero credit consumption
            zero_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=0,
                event_type="zero_consumption_test",
                metadata={"test": "zero_edge_case"}
            )

            result = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=zero_consumption
            )

            self.assertTrue(result.success)
            self.assertEqual(result.credits_consumed, 0)
            self.assertEqual(result.remaining_balance, 100)

            # Test allocation with zero adjustment
            operation_id = str(uuid.uuid4())
            allocation_result = await self.billing_service.allocate_credits_for_operation(
                db=db, org_id=test_org.id, user_id=test_user.id,
                credit_type=CreditType.WORKFLOWS, estimated_credits=50,
                operation_id=operation_id
            )

            # Adjust with exact same amount (zero difference)
            adjustment_result = await self.billing_service.adjust_allocated_credits(
                db=db, org_id=test_org.id, user_id=test_user.id,
                credit_type=CreditType.WORKFLOWS, operation_id=operation_id,
                actual_credits=50, allocated_credits=50
            )

            self.assertFalse(adjustment_result.adjustment_needed)
            self.assertEqual(adjustment_result.credit_difference, 0)

    async def test_billing_dashboard_comprehensive_edge_cases(self):
        """Test billing dashboard with various edge cases and empty states."""
        async with get_async_db_as_manager() as db:
            # Test dashboard for organization with no credits
            empty_org = self._get_test_org(3)
            empty_dashboard = await self.billing_service.get_billing_dashboard(db, empty_org.id)

            self.assertEqual(empty_dashboard.org_id, empty_org.id)
            self.assertIsNone(empty_dashboard.subscription)
            
            # All credit balances should be zero
            for balance in empty_dashboard.credit_balances:
                self.assertEqual(balance.credits_balance, 0)
                self.assertEqual(balance.credits_granted, 0)
                self.assertEqual(balance.credits_consumed, 0)

            self.assertEqual(len(empty_dashboard.recent_usage), 0)
            self.assertEqual(len(empty_dashboard.recent_purchases), 0)

            # Test dashboard for organization with mixed activity
            active_org = self._get_test_org(2)
            active_user = self._get_test_user(5)

            # Apply credits and create some activity
            application = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=active_org.id, user_id=active_user.id, code_application=application
            )

            # Create usage events
            for i in range(5):
                consumption_request = billing_schemas.CreditConsumptionRequest(
                    credit_type=CreditType.WORKFLOWS,
                    credits_consumed=10,
                    event_type=f"dashboard_test_event_{i}",
                    metadata={"dashboard_test": True, "event_index": i}
                )

                await self.billing_service.consume_credits(
                    db=db, org_id=active_org.id, user_id=active_user.id, 
                    consumption_request=consumption_request
                )

            active_dashboard = await self.billing_service.get_billing_dashboard(db, active_org.id)

            # Verify dashboard content
            self.assertGreater(len(active_dashboard.recent_usage), 0)
            
            workflow_balance = next(
                b for b in active_dashboard.credit_balances 
                if b.credit_type == CreditType.WORKFLOWS
            )
            self.assertEqual(workflow_balance.credits_balance, 50)  # 100 - 50 consumed
            self.assertEqual(workflow_balance.credits_consumed, 50)

    async def test_complex_multi_user_scenarios_within_organization(self):
        """Test complex scenarios with multiple users within the same organization."""
        async with get_async_db_as_manager() as db:
            # Use enterprise org with multiple users
            test_org = self._get_test_org(3)
            users = [self._get_test_user(6), self._get_test_user(7), self._get_test_user(8), self._get_test_user(9)]

            # Apply credits using first user
            application = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=users[0].id, code_application=application
            )

            # Apply multi-use promotion code with different users
            multiuse_application = billing_schemas.PromotionCodeApply(code='test_MULTIUSE_PER_ORG')
            
            for i in range(3):  # Use 3 times (max allowed per org)
                await self.billing_service.apply_promotion_code(
                    db=db, org_id=test_org.id, user_id=users[i].id, code_application=multiuse_application
                )

            # Verify fourth use fails
            with self.assertRaises(PromotionCodeAlreadyUsedException):
                await self.billing_service.apply_promotion_code(
                    db=db, org_id=test_org.id, user_id=users[3].id, code_application=multiuse_application
                )

            # Simulate concurrent usage by multiple users
            for i, user in enumerate(users):
                # Each user consumes different amounts of different credit types
                workflow_consumption = billing_schemas.CreditConsumptionRequest(
                    credit_type=CreditType.WORKFLOWS,
                    credits_consumed=15 + (i * 5),  # 15, 20, 25, 30
                    event_type=f"multi_user_workflow_{i}",
                    metadata={"user_index": i, "multi_user_test": True}
                )

                dollar_consumption = billing_schemas.CreditConsumptionRequest(
                    credit_type=CreditType.DOLLAR_CREDITS,
                    credits_consumed=1.0 + (i * 0.5),  # 1.0, 1.5, 2.0, 2.5
                    event_type=f"multi_user_dollar_{i}",
                    metadata={"user_index": i, "multi_user_test": True}
                )

                # Execute consumption for each user
                await self.billing_service.consume_credits(
                    db=db, org_id=test_org.id, user_id=user.id, consumption_request=workflow_consumption
                )

                await self.billing_service.consume_credits(
                    db=db, org_id=test_org.id, user_id=user.id, consumption_request=dollar_consumption
                )

            # Verify final balances
            final_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            
            workflow_balance = next(b for b in final_balances if b.credit_type == CreditType.WORKFLOWS)
            dollar_balance = next(b for b in final_balances if b.credit_type == CreditType.DOLLAR_CREDITS)

            # Workflow: 100 - (15 + 20 + 25 + 30) = 10
            self.assertEqual(workflow_balance.credits_balance, 10)
            # Dollar: 30.0 - (1.0 + 1.5 + 2.0 + 2.5) = 23.0
            self.assertEqual(dollar_balance.credits_balance, 23.0)

            # Verify usage events are attributed to correct users
            end_date = datetime_now_utc()
            start_date = end_date - timedelta(hours=1)
            usage_summary = await self.billing_service.get_usage_summary(
                db=db, org_id=test_org.id, start_date=start_date, end_date=end_date
            )

            # Should have 8 total events (4 users × 2 credit types)
            self.assertEqual(usage_summary.total_events, 8)

    async def test_error_handling_and_rollback_scenarios(self):
        """Test error handling and transaction rollback scenarios."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(0)
            test_user = self._get_test_user(0)

            # Apply some credits first
            application = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=application
            )

            # Test consumption beyond available credits
            large_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=150,  # More than available
                event_type="excess_consumption_test",
                metadata={"test": "error_handling"}
            )

            with self.assertRaises(InsufficientCreditsException) as context:
                await self.billing_service.consume_credits(
                    db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=large_consumption
                )

            exception = context.exception
            self.assertEqual(exception.credit_type, CreditType.WORKFLOWS)
            self.assertEqual(exception.required, 150.0)
            self.assertAlmostEqual(exception.available, 110.0, places=5)  # 100 + 10% overage

            # Verify that failed consumption didn't affect balances
            post_error_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            workflow_balance = next(b for b in post_error_balances if b.credit_type == CreditType.WORKFLOWS)
            self.assertEqual(workflow_balance.credits_balance, 100.0)
            self.assertEqual(workflow_balance.credits_consumed, 0.0)

            # Test successful consumption after error
            normal_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=50.0,
                event_type="normal_consumption_after_error",
                metadata={"test": "recovery"}
            )

            result = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=normal_consumption
            )

            self.assertTrue(result.success)
            self.assertEqual(result.remaining_balance, 50.0)

    async def test_paid_subscription_management(self):
        """Test paid subscription creation and management."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(2)
            test_user = self._get_test_user(5)

            # Create premium plan
            plan_data = billing_schemas.SubscriptionPlanCreate(
                name="test_premium_plan",
                description="Test premium subscription plan",
                stripe_product_id="prod_premium_test",
                max_seats=10,
                monthly_credits={
                    CreditType.WORKFLOWS.value: 500,
                    CreditType.WEB_SEARCHES.value: 2000,
                    CreditType.DOLLAR_CREDITS.value: 100.0  # $100
                },
                monthly_price=49.99,  # $49.99
                annual_price=499.99,  # $499.99
                is_trial_eligible=True,
                trial_days=14
            )

            plan = await self.subscription_plan_dao.create(db=db, obj_in=plan_data)
            self.created_entity_ids['subscription_plans'].append(plan.id)

            # Create paid subscription (no trial) using proper constructor
            now = datetime_now_utc()
            subscription_model = billing_models.OrganizationSubscription(
                org_id=test_org.id,
                plan_id=plan.id,
                stripe_subscription_id="sub_premium_test",
                stripe_customer_id="cus_premium_test",
                status=SubscriptionStatus.ACTIVE,
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                seats_count=3,
                is_annual=False,
                is_trial_active=False,
                created_at=now,
                updated_at=now
            )

            subscription = await self.org_subscription_dao.create(db=db, obj_in=subscription_model)
            self.created_entity_ids['organization_subscriptions'].append(subscription.id)

            # Test initial credit allocation for paid subscription
            await self.billing_service._allocate_subscription_credits(db, subscription, plan, is_renewal=False)

            # Verify credits were allocated
            credit_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            
            workflow_balance = next(b for b in credit_balances if b.credit_type == CreditType.WORKFLOWS)
            websearch_balance = next(b for b in credit_balances if b.credit_type == CreditType.WEB_SEARCHES)
            dollar_balance = next(b for b in credit_balances if b.credit_type == CreditType.DOLLAR_CREDITS)

            self.assertEqual(workflow_balance.credits_balance, 500)
            self.assertEqual(websearch_balance.credits_balance, 2000)
            self.assertEqual(dollar_balance.credits_balance, 100)

            # Test regular renewal (not trial-to-paid)
            renewal_result = await self.billing_service.process_subscription_renewal(db, subscription)
            
            self.assertTrue(renewal_result["success"])
            self.assertEqual(renewal_result["renewal_type"], "regular")

            # Verify subscription remains active
            updated_subscription = await self.org_subscription_dao.get(db, subscription.id)
            self.assertEqual(updated_subscription.status, SubscriptionStatus.ACTIVE)
            self.assertFalse(updated_subscription.is_trial_active)


if __name__ == '__main__':
    unittest.main()
