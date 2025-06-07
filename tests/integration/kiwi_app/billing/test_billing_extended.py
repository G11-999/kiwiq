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
        'test_basic_seat_count_plan',  # Seat count test plans
        'test_premium_seat_count_plan',
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
    stripe_event_dao: billing_crud.StripeEventDAO

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
        self.stripe_event_dao = billing_crud.StripeEventDAO()

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
            promotion_code_usage_dao=self.promotion_code_usage_dao,
            org_dao=self.org_dao,
            stripe_event_dao=self.stripe_event_dao
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
                if pattern.startswith('test_') and not '%' in pattern:
                    # Exact match for specific plan names
                    delete_stmt = text("DELETE FROM kiwiq_billing_subscription_plan WHERE name = :name")
                    result = await db.execute(delete_stmt, {"name": pattern})
                    if result.rowcount > 0:
                        print(f"Deleted {result.rowcount} subscription plan with exact name '{pattern}'")
                else:
                    # Pattern match for wildcards
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

            # Test consumption beyond available credits WITHOUT dollar fallback
            large_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=150,  # More than available
                event_type="excess_consumption_test",
                metadata={"test": "error_handling"}
            )

            with self.assertRaises(InsufficientCreditsException) as context:
                await self.billing_service.consume_credits(
                    db=db, org_id=test_org.id, user_id=test_user.id, 
                    consumption_request=large_consumption, 
                    allow_dollar_fallback=False
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

            # Now test WITH dollar fallback (default behavior)
            # Apply dollar credits
            dollar_app = billing_schemas.PromotionCodeApply(code='test_MULTIUSE_PER_ORG')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=dollar_app
            )

            # Consume remaining workflow credits
            exhaust_workflow = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=50.0,
                event_type="exhaust_workflows",
                metadata={"test": "setup_for_fallback"}
            )
            await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=exhaust_workflow
            )

            # Now try to consume more - should use dollar fallback
            fallback_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=100.0,  # 100 * $0.05 = $5.00
                event_type="fallback_to_dollars",
                metadata={"test": "dollar_fallback"}
            )

            result = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=fallback_consumption
            )

            # Should succeed with dollar fallback
            self.assertTrue(result.success)
            
            # Check dollar credits were consumed
            final_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            dollar_balance = next(b for b in final_balances if b.credit_type == CreditType.DOLLAR_CREDITS)
            self.assertEqual(dollar_balance.credits_balance, 5.0)  # $10 - $5 = $5

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
            await self.billing_service.apply_subscription_credits(db, subscription, plan, is_renewal=False)

            # Verify credits were allocated (multiplied by seat count: 3 seats)
            credit_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            
            workflow_balance = next(b for b in credit_balances if b.credit_type == CreditType.WORKFLOWS)
            websearch_balance = next(b for b in credit_balances if b.credit_type == CreditType.WEB_SEARCHES)
            dollar_balance = next(b for b in credit_balances if b.credit_type == CreditType.DOLLAR_CREDITS)

            self.assertEqual(workflow_balance.credits_balance, 1500)  # 500 × 3 seats
            self.assertEqual(websearch_balance.credits_balance, 6000)  # 2000 × 3 seats
            self.assertEqual(dollar_balance.credits_balance, 300)  # 100 × 3 seats

            # Test regular renewal (not trial-to-paid)
            renewal_result = await self.billing_service.apply_subscription_credits(db, subscription, plan, is_renewal=True)
            
            self.assertTrue(renewal_result["success"])
            self.assertEqual(renewal_result["allocation_type"], "renewal_rotation")

            # Verify subscription remains active
            updated_subscription = await self.org_subscription_dao.get(db, subscription.id)
            self.assertEqual(updated_subscription.status, SubscriptionStatus.ACTIVE)
            self.assertFalse(updated_subscription.is_trial_active)

    async def test_dollar_credit_fallback_basic_functionality(self):
        """Test basic dollar credit fallback when non-dollar credits are insufficient."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(0)
            test_user = self._get_test_user(0)

            # Apply both workflow and dollar credits
            workflow_app = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=workflow_app
            )
            
            dollar_app = billing_schemas.PromotionCodeApply(code='test_MULTIUSE_PER_ORG')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=dollar_app
            )

            # Consume all workflow credits first
            first_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=100.0,
                event_type="exhaust_workflow_credits",
                metadata={"test": "dollar_fallback"}
            )
            await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=first_consumption
            )

            # Now try to consume more workflow credits - should fallback to dollar credits
            # 20 workflow credits = 20 * $0.05 = $1.00 in dollar credits
            fallback_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=20.0,
                event_type="workflow_with_dollar_fallback",
                metadata={"test": "dollar_fallback", "expected_dollar_consumption": 1.0}
            )

            result = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=fallback_consumption
            )

            # Verify successful consumption
            self.assertTrue(result.success)
            # When dollar fallback happens, result shows dollar credits consumed
            # 20 workflow credits * $0.05 = $1.00 dollar credits
            # Check if dollar fallback occurred
            if result.dollar_credit_fallback:
                # Fallback occurred - result shows dollar credits consumed
                self.assertEqual(result.credits_consumed, 1.0)
                self.assertEqual(result.consumed_in_dollar_credits, 1.0)
                self.assertEqual(result.credit_type, CreditType.DOLLAR_CREDITS)
            else:
                # No fallback - original credits consumed
                self.assertEqual(result.credits_consumed, 20.0)
                self.assertEqual(result.credit_type, CreditType.WORKFLOWS)
            
            # Check that dollar credits were consumed
            balances = await self.billing_service.get_credit_balances(db, test_org.id)
            workflow_balance = next(b for b in balances if b.credit_type == CreditType.WORKFLOWS)
            dollar_balance = next(b for b in balances if b.credit_type == CreditType.DOLLAR_CREDITS)
            
            # Workflow credits should still be at 0 (100 consumed - 100 granted)
            self.assertEqual(workflow_balance.credits_balance, 0.0)
            # Dollar credits: started with $10, consumed $1.00 = $9.00 remaining
            self.assertEqual(dollar_balance.credits_balance, 9.0)

    async def test_dollar_credit_fallback_conversion_rates(self):
        """Test correct conversion rates for different credit types falling back to dollar credits."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(1)
            test_user = self._get_test_user(3)

            # Apply only dollar credits (no workflow or web search credits)
            dollar_app = billing_schemas.PromotionCodeApply(code='test_MULTIUSE_PER_ORG')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=dollar_app
            )

            # Test workflow credit consumption with dollar fallback
            # 100 workflow credits * $0.05 = $5.00
            workflow_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=100.0,
                event_type="workflow_dollar_conversion_test",
                metadata={"conversion_test": True}
            )

            result = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=workflow_consumption
            )

            self.assertTrue(result.success)
            
            # Check dollar balance
            balances = await self.billing_service.get_credit_balances(db, test_org.id)
            dollar_balance = next(b for b in balances if b.credit_type == CreditType.DOLLAR_CREDITS)
            self.assertEqual(dollar_balance.credits_balance, 5.0)  # $10 - $5 = $5

            # Apply web search credits test promotion
            websearch_app = billing_schemas.PromotionCodeApply(code='test_WEBSEARCH50_LIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=websearch_app
            )

            # Consume all web search credits
            websearch_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WEB_SEARCHES,
                credits_consumed=50.0,
                event_type="exhaust_websearch_credits",
                metadata={"test": "exhaust"}
            )
            await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=websearch_consumption
            )

            # Now test web search consumption with dollar fallback
            # 40 web search credits * $0.05 = $2.00
            websearch_fallback_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WEB_SEARCHES,
                credits_consumed=40.0,
                event_type="websearch_dollar_conversion_test",
                metadata={"conversion_test": True}
            )

            result2 = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=websearch_fallback_consumption
            )

            self.assertTrue(result2.success)
            
            # Check final dollar balance
            final_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            final_dollar_balance = next(b for b in final_balances if b.credit_type == CreditType.DOLLAR_CREDITS)
            self.assertEqual(final_dollar_balance.credits_balance, 3.0)  # $5 - $2 = $3

    async def test_dollar_credit_fallback_insufficient_dollar_credits(self):
        """Test when both non-dollar and dollar credits are insufficient."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(2)
            test_user = self._get_test_user(5)

            # Apply limited dollar credits only
            dollar_app = billing_schemas.PromotionCodeApply(code='test_MULTIUSE_PER_ORG')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=dollar_app
            )

            # Try to consume workflow credits that would cost more than available dollar credits
            # 500 workflow credits * $0.05 = $25.00 (but only $10 available)
            large_workflow_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=500.0,
                event_type="insufficient_dollar_fallback_test",
                metadata={"test": "insufficient_dollars"}
            )

            with self.assertRaises(InsufficientCreditsException) as context:
                await self.billing_service.consume_credits(
                    db=db, org_id=test_org.id, user_id=test_user.id, 
                    consumption_request=large_workflow_consumption
                )

            # Verify the exception is for dollar credits (the fallback type)
            exception = context.exception
            self.assertEqual(exception.credit_type, CreditType.DOLLAR_CREDITS)
            self.assertEqual(exception.required, 25.0)  # $25 required
            self.assertAlmostEqual(exception.available, 11.0, places=5)  # $10 + 10% overage = $11

    async def test_dollar_credit_fallback_with_partial_credits(self):
        """Test dollar fallback when there are some non-dollar credits but not enough."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(3)
            test_user = self._get_test_user(6)

            # Apply both workflow and dollar credits
            workflow_app = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=workflow_app
            )
            
            dollar_app = billing_schemas.PromotionCodeApply(code='test_MULTIUSE_PER_ORG')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=dollar_app
            )

            # Consume most workflow credits, leaving only 10
            partial_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=90.0,
                event_type="partial_workflow_consumption",
                metadata={"test": "partial_credits"}
            )
            await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=partial_consumption
            )

            # Now try to consume 30 workflow credits (only 10 + 10% overage = 20 available)
            # Since the implementation does all-or-nothing fallback, it will use dollar credits entirely
            # 30 workflow credits * $0.05 = $1.50 from dollar credits
            mixed_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=30.0,
                event_type="mixed_credits_consumption",
                metadata={"test": "partial_plus_dollar"}
            )

            result = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=mixed_consumption
            )

            self.assertTrue(result.success)
            
            # Check final balances
            balances = await self.billing_service.get_credit_balances(db, test_org.id)
            workflow_balance = next(b for b in balances if b.credit_type == CreditType.WORKFLOWS)
            dollar_balance = next(b for b in balances if b.credit_type == CreditType.DOLLAR_CREDITS)
            
            # Since implementation uses all-or-nothing fallback:
            # Workflow credits remain at 10 (90 consumed out of 100)
            self.assertEqual(workflow_balance.credits_balance, 10.0)
            self.assertEqual(workflow_balance.credits_consumed, 90.0)  # Only the initial consumption
            # Dollar credits: $10 - $1.50 = $8.50 (for all 30 credits via fallback)
            self.assertEqual(dollar_balance.credits_balance, 8.5)

    async def test_dollar_credit_fallback_with_overage(self):
        """Test dollar credit fallback interaction with overage limits."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(0)
            test_user = self._get_test_user(1)

            # Apply workflow credits
            workflow_app = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=workflow_app
            )
            
            # Apply dollar credits
            dollar_app = billing_schemas.PromotionCodeApply(code='test_MULTIUSE_PER_ORG')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=dollar_app
            )

            # Consume all workflow credits plus 10% overage (110 total)
            overage_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=110.0,
                event_type="consume_with_overage",
                metadata={"test": "overage"}
            )
            result1 = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=overage_consumption
            )
            
            self.assertTrue(result1.success)
            self.assertTrue(result1.is_overage)

            # Now any additional workflow consumption should use dollar credits
            # 25 workflow credits * $0.05 = $1.25
            dollar_fallback_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=25.0,
                event_type="dollar_fallback_after_overage",
                metadata={"test": "post_overage_dollar"}
            )

            result2 = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=dollar_fallback_consumption
            )

            self.assertTrue(result2.success)
            
            # Check balances
            balances = await self.billing_service.get_credit_balances(db, test_org.id)
            workflow_balance = next(b for b in balances if b.credit_type == CreditType.WORKFLOWS)
            dollar_balance = next(b for b in balances if b.credit_type == CreditType.DOLLAR_CREDITS)
            
            # Workflow credits should show overage consumption
            self.assertEqual(workflow_balance.credits_balance, 0.0)
            self.assertEqual(workflow_balance.credits_consumed, 110.0)  # Only the original consumption
            # Dollar credits: $10 - $1.25 = $8.75
            self.assertEqual(dollar_balance.credits_balance, 8.75)

    async def test_dollar_credit_fallback_concurrent_consumption(self):
        """Test dollar credit fallback with concurrent consumption by multiple users."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(3)
            users = [self._get_test_user(6), self._get_test_user(7), self._get_test_user(8)]

            # Apply limited workflow credits and dollar credits
            workflow_app = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=users[0].id, code_application=workflow_app
            )
            
            # Apply dollar credits multiple times for more balance
            dollar_app = billing_schemas.PromotionCodeApply(code='test_MULTIUSE_PER_ORG')
            for i in range(3):  # $30 total
                await self.billing_service.apply_promotion_code(
                    db=db, org_id=test_org.id, user_id=users[i].id, code_application=dollar_app
                )

            # Consume most workflow credits
            initial_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=80.0,
                event_type="initial_concurrent_consumption",
                metadata={"test": "concurrent_setup"}
            )
            await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=users[0].id, consumption_request=initial_consumption
            )

            # Simulate concurrent consumption that will trigger dollar fallback
            concurrent_consumptions = []
            for i, user in enumerate(users):
                # Each user tries to consume 15 workflow credits
                # Total: 45 credits needed, but only 20 available
                # Fallback: 25 credits * $0.05 = $1.25 from dollar credits
                consumption = billing_schemas.CreditConsumptionRequest(
                    credit_type=CreditType.WORKFLOWS,
                    credits_consumed=15.0,
                    event_type=f"concurrent_consumption_{i}",
                    metadata={"test": "concurrent", "user_index": i}
                )
                result = await self.billing_service.consume_credits(
                    db=db, org_id=test_org.id, user_id=user.id, consumption_request=consumption
                )
                concurrent_consumptions.append(result)

            # Verify all consumptions succeeded
            for result in concurrent_consumptions:
                self.assertTrue(result.success)

            # Check final balances
            final_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            workflow_balance = next(b for b in final_balances if b.credit_type == CreditType.WORKFLOWS)
            dollar_balance = next(b for b in final_balances if b.credit_type == CreditType.DOLLAR_CREDITS)
            
            # Workflow credits should be at or over limit
            self.assertEqual(workflow_balance.credits_balance, 0.0)
            self.assertGreaterEqual(workflow_balance.credits_consumed, 110.0)  # 80 + 45 = 125 (with overage)
            # Dollar credits should have been consumed for the overflow
            self.assertLess(dollar_balance.credits_balance, 30.0)

    async def test_dollar_credit_fallback_complex_mixed_scenarios(self):
        """Test complex scenarios with multiple credit types and dollar fallback."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(1)
            test_user = self._get_test_user(4)

            # Apply multiple credit types
            workflow_app = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=workflow_app
            )
            
            websearch_app = billing_schemas.PromotionCodeApply(code='test_WEBSEARCH50_LIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=websearch_app
            )
            
            dollar_app = billing_schemas.PromotionCodeApply(code='test_MULTIUSE_PER_ORG')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=dollar_app
            )

            # Scenario 1: Consume all workflow credits
            workflow_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=100.0,
                event_type="exhaust_workflows",
                metadata={"scenario": "complex_mixed"}
            )
            await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=workflow_consumption
            )

            # Scenario 2: Consume all web search credits
            websearch_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WEB_SEARCHES,
                credits_consumed=50.0,
                event_type="exhaust_websearches",
                metadata={"scenario": "complex_mixed"}
            )
            await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=websearch_consumption
            )

            # Scenario 3: Mixed consumption requiring dollar fallback for both types
            # 50 workflow credits * $0.05 = $2.50
            workflow_fallback = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=50.0,
                event_type="workflow_dollar_fallback",
                metadata={"scenario": "complex_mixed"}
            )
            
            # 30 web search credits * $0.05 = $1.50  
            websearch_fallback = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WEB_SEARCHES,
                credits_consumed=30.0,
                event_type="websearch_dollar_fallback",
                metadata={"scenario": "complex_mixed"}
            )

            result1 = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=workflow_fallback
            )
            result2 = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=websearch_fallback
            )

            self.assertTrue(result1.success)
            self.assertTrue(result2.success)

            # Check final dollar balance
            final_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            dollar_balance = next(b for b in final_balances if b.credit_type == CreditType.DOLLAR_CREDITS)
            # $10 - $2.50 - $1.50 = $6.00
            self.assertEqual(dollar_balance.credits_balance, 6.0)

    async def test_dollar_credit_fallback_edge_cases(self):
        """Test edge cases for dollar credit fallback mechanism."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(2)
            test_user = self._get_test_user(5)

            # Edge case 1: Zero credit consumption with fallback
            # Apply only dollar credits
            dollar_app = billing_schemas.PromotionCodeApply(code='test_MULTIUSE_PER_ORG')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=dollar_app
            )

            zero_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=0.0,
                event_type="zero_consumption_fallback",
                metadata={"edge_case": "zero"}
            )

            result = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=zero_consumption
            )

            self.assertTrue(result.success)
            self.assertEqual(result.credits_consumed, 0.0)

            # Check no dollar credits were consumed
            balances = await self.billing_service.get_credit_balances(db, test_org.id)
            dollar_balance = next(b for b in balances if b.credit_type == CreditType.DOLLAR_CREDITS)
            self.assertEqual(dollar_balance.credits_balance, 10.0)

            # Edge case 2: Very small consumption requiring dollar fallback
            # 0.1 workflow credits * $0.05 = $0.005
            tiny_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=0.1,
                event_type="tiny_consumption_fallback",
                metadata={"edge_case": "tiny"}
            )

            result2 = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=tiny_consumption
            )

            self.assertTrue(result2.success)
            
            # Check dollar balance for tiny consumption
            balances2 = await self.billing_service.get_credit_balances(db, test_org.id)
            dollar_balance2 = next(b for b in balances2 if b.credit_type == CreditType.DOLLAR_CREDITS)
            self.assertAlmostEqual(dollar_balance2.credits_balance, 9.995, places=3)

            # Edge case 3: Exactly matching dollar credit balance
            # Consume exactly what's left in dollar credits
            # Current balance: ~$9.995
            # Need to consume: ~199.9 workflow credits to use exactly $9.995
            exact_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=199.9,
                event_type="exact_dollar_balance_consumption",
                metadata={"edge_case": "exact_balance"}
            )

            result3 = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=exact_consumption
            )

            self.assertTrue(result3.success)
            
            # Dollar balance should be very close to 0
            balances3 = await self.billing_service.get_credit_balances(db, test_org.id)
            dollar_balance3 = next(b for b in balances3 if b.credit_type == CreditType.DOLLAR_CREDITS)
            self.assertAlmostEqual(dollar_balance3.credits_balance, 0.0, places=2)

    async def test_dollar_credit_fallback_with_allocations(self):
        """Test that allocations don't support dollar credit fallback (by design)."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(0)
            test_user = self._get_test_user(2)

            # Apply limited workflow credits and dollar credits
            workflow_app = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=workflow_app
            )
            
            dollar_app = billing_schemas.PromotionCodeApply(code='test_MULTIUSE_PER_ORG')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=dollar_app
            )

            # Consume most workflow credits
            initial_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=95.0,
                event_type="setup_for_allocation_test",
                metadata={"test": "allocation_setup"}
            )
            await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=initial_consumption
            )

            # Try to allocate credits that would require dollar fallback
            # Only 5 workflow credits left (+ 10% overage = 15 total), but allocating 30
            # Allocations don't support dollar fallback, so this should fail
            operation_id = str(uuid.uuid4())
            
            with self.assertRaises(InsufficientCreditsException) as context:
                await self.billing_service.allocate_credits_for_operation(
                    db=db,
                    org_id=test_org.id,
                    user_id=test_user.id,
                    credit_type=CreditType.WORKFLOWS,
                    estimated_credits=30.0,
                    operation_id=operation_id,
                    metadata={"test": "allocation_without_fallback"}
                )
            
            # Verify the exception is for workflow credits (no fallback)
            exception = context.exception
            self.assertEqual(exception.credit_type, CreditType.WORKFLOWS)
            self.assertEqual(exception.required, 30.0)
            
            # Verify balances remain unchanged
            balances = await self.billing_service.get_credit_balances(db, test_org.id)
            workflow_balance = next(b for b in balances if b.credit_type == CreditType.WORKFLOWS)
            dollar_balance = next(b for b in balances if b.credit_type == CreditType.DOLLAR_CREDITS)
            
            # Workflow balance should still be 5
            self.assertEqual(workflow_balance.credits_balance, 5.0)
            self.assertEqual(workflow_balance.credits_consumed, 95.0)
            # Dollar credits should be untouched
            self.assertEqual(dollar_balance.credits_balance, 10.0)
            
            # Now test successful allocation within available credits
            smaller_operation_id = str(uuid.uuid4())
            allocation_result = await self.billing_service.allocate_credits_for_operation(
                db=db,
                org_id=test_org.id,
                user_id=test_user.id,
                credit_type=CreditType.WORKFLOWS,
                estimated_credits=10.0,  # Within 5 + 10% overage = 15 available
                operation_id=smaller_operation_id,
                metadata={"test": "allocation_within_limits"}
            )

            self.assertTrue(allocation_result.success)
            self.assertEqual(allocation_result.allocated_credits, 10.0)

            # Check balances after successful allocation
            balances2 = await self.billing_service.get_credit_balances(db, test_org.id)
            workflow_balance2 = next(b for b in balances2 if b.credit_type == CreditType.WORKFLOWS)
            
            # Workflow should show consumption
            self.assertEqual(workflow_balance2.credits_balance, 0.0)
            self.assertEqual(workflow_balance2.credits_consumed, 105.0)  # 95 + 10

            # Test adjustment for the smaller allocation
            adjustment_result = await self.billing_service.adjust_allocated_credits(
                db=db,
                org_id=test_org.id,
                user_id=test_user.id,
                credit_type=CreditType.WORKFLOWS,
                operation_id=smaller_operation_id,
                actual_credits=7.0,  # Less than allocated 10
                allocated_credits=10.0,
                metadata={"test": "adjustment_without_fallback"}
            )

            self.assertTrue(adjustment_result.success)
            self.assertTrue(adjustment_result.adjustment_needed)
            self.assertEqual(adjustment_result.credit_difference, -3.0)
            
            # Some credits should be returned, reducing overage
            final_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            final_workflow_balance = next(b for b in final_balances if b.credit_type == CreditType.WORKFLOWS)
            
            # 3 credits should be returned, reducing consumption from 105 to 102, but still in overage
            self.assertEqual(final_workflow_balance.credits_balance, 0.0)  # Still in overage (102 > 100)
            self.assertEqual(final_workflow_balance.credits_consumed, 102.0)  # 95 + 7

    async def test_dollar_credit_fallback_transaction_integrity(self):
        """Test transaction integrity when dollar credit fallback occurs."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(1)
            test_user = self._get_test_user(3)

            # Apply only dollar credits
            dollar_app = billing_schemas.PromotionCodeApply(code='test_MULTIUSE_PER_ORG')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=dollar_app
            )

            # Get initial state
            initial_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            initial_dollar = next(b for b in initial_balances if b.credit_type == CreditType.DOLLAR_CREDITS)
            initial_dollar_balance = initial_dollar.credits_balance

            # Track all consumption events
            consumption_events = []
            
            # Perform multiple consumptions that require dollar fallback
            for i in range(5):
                consumption = billing_schemas.CreditConsumptionRequest(
                    credit_type=CreditType.WORKFLOWS,
                    credits_consumed=10.0,  # 10 * $0.05 = $0.50 each
                    event_type=f"transaction_test_{i}",
                    metadata={"test": "transaction_integrity", "index": i}
                )
                
                result = await self.billing_service.consume_credits(
                    db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=consumption
                )
                consumption_events.append({
                    "index": i,
                    "success": result.success,
                    "credits_consumed": result.credits_consumed
                })

            # Verify all consumptions succeeded
            for event in consumption_events:
                self.assertTrue(event["success"])

            # Check final balance matches expected
            final_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            final_dollar = next(b for b in final_balances if b.credit_type == CreditType.DOLLAR_CREDITS)
            
            # 5 consumptions * $0.50 = $2.50 total consumed
            expected_balance = initial_dollar_balance - 2.50
            self.assertEqual(final_dollar.credits_balance, expected_balance)

            # Verify usage events were created correctly
            usage_summary = await self.billing_service.get_usage_summary(
                db=db, 
                org_id=test_org.id, 
                start_date=datetime_now_utc() - timedelta(hours=1),
                end_date=datetime_now_utc()
            )
            
            # Should have 5 workflow events even though dollar credits were used
            workflow_events = [e for e in usage_summary.events_by_type.keys() if "transaction_test" in e]
            self.assertEqual(len(workflow_events), 5)

    async def test_dollar_credit_fallback_audit_trail(self):
        """Test that dollar credit fallback creates proper audit trail and tracking."""
        async with get_async_db_as_manager() as db:
            test_org = self._get_test_org(3)
            test_user = self._get_test_user(9)

            # Apply both credit types
            workflow_app = billing_schemas.PromotionCodeApply(code='test_WORKFLOW100_UNLIMITED')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=workflow_app
            )
            
            dollar_app = billing_schemas.PromotionCodeApply(code='test_MULTIUSE_PER_ORG')
            await self.billing_service.apply_promotion_code(
                db=db, org_id=test_org.id, user_id=test_user.id, code_application=dollar_app
            )

            # Consume all workflow credits
            exhaust_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=100.0,
                event_type="exhaust_for_audit_test",
                metadata={"test": "audit_setup"}
            )
            await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=exhaust_consumption
            )

            # Now consume with dollar fallback and track the event
            fallback_consumption = billing_schemas.CreditConsumptionRequest(
                credit_type=CreditType.WORKFLOWS,
                credits_consumed=40.0,  # 40 * $0.05 = $2.00
                event_type="workflow_with_dollar_fallback_audit",
                metadata={
                    "test": "audit_trail",
                    "expected_dollar_cost": 2.0,
                    "original_credit_type": "workflows"
                }
            )

            result = await self.billing_service.consume_credits(
                db=db, org_id=test_org.id, user_id=test_user.id, consumption_request=fallback_consumption
            )

            self.assertTrue(result.success)

            # Get usage events - need to look for the modified event type
            # When dollar fallback occurs, event type is prefixed with "dollar_credit_fallback_for__"
            usage_events = await self.usage_event_dao.get_by_org_and_period(
                db=db,
                org_id=test_org.id,
                start_date=datetime_now_utc() - timedelta(hours=1),
                end_date=datetime_now_utc(),
                event_type="dollar_credit_fallback_for__workflow_with_dollar_fallback_audit"
            )

            self.assertEqual(len(usage_events), 1)
            audit_event = usage_events[0]
            
            # Verify the event tracks dollar credit consumption
            self.assertEqual(audit_event.credit_type, CreditType.DOLLAR_CREDITS)
            self.assertEqual(audit_event.credits_consumed, 2.0)  # Dollar amount consumed
            self.assertEqual(audit_event.event_type, "dollar_credit_fallback_for__workflow_with_dollar_fallback_audit")
            
            # Check metadata for fallback information
            self.assertIn("dollar_credit_fallback", audit_event.usage_metadata)
            self.assertTrue(audit_event.usage_metadata["dollar_credit_fallback"])
            self.assertEqual(audit_event.usage_metadata["consumed_in_dollar_credits"], 2.0)
            
            # Check that dollar credits were actually consumed
            balances = await self.billing_service.get_credit_balances(db, test_org.id)
            dollar_balance = next(b for b in balances if b.credit_type == CreditType.DOLLAR_CREDITS)
            self.assertEqual(dollar_balance.credits_balance, 8.0)  # $10 - $2 = $8

            # Verify billing dashboard shows the correct information
            dashboard = await self.billing_service.get_billing_dashboard(db, test_org.id)
            
            # Check that recent usage includes our fallback event
            recent_fallback_events = [
                e for e in dashboard.recent_usage 
                if e.event_type == "dollar_credit_fallback_for__workflow_with_dollar_fallback_audit"
            ]
            self.assertEqual(len(recent_fallback_events), 1)
            
            # Also check the original workflow consumption event
            original_events = [
                e for e in dashboard.recent_usage 
                if e.event_type == "exhaust_for_audit_test"
            ]
            self.assertEqual(len(original_events), 1)
            
            # Verify credit balances in dashboard
            dashboard_dollar_balance = next(
                b for b in dashboard.credit_balances 
                if b.credit_type == CreditType.DOLLAR_CREDITS
            )
            self.assertEqual(dashboard_dollar_balance.credits_balance, 8.0)
            self.assertEqual(dashboard_dollar_balance.credits_consumed, 2.0)

    async def test_get_total_seat_count_for_org(self):
        """
        Test getting total seat count for organizations with various subscription scenarios.
        
        This test verifies the OrganizationSubscriptionDAO.get_total_seat_count_for_org() method:
        - Returns 0 for organizations with no subscriptions
        - Correctly sums seats from single subscription
        - Correctly sums seats from multiple subscriptions  
        - Includes all subscription statuses (active, trial, past_due, etc.)
        - Handles edge cases (zero seats, large seat counts)
        - Handles non-existent organizations
        - Returns proper integer type
        - Updates correctly when subscriptions are deleted
        
        Test entities created are automatically tracked and cleaned up via:
        - self.created_entity_ids tracking for asyncTearDown cleanup
        - TEST_PLAN_PATTERNS for pattern-based cleanup of plans
        """
        async with get_async_db_as_manager() as db:
            # Test organizations
            test_org_no_subs = self._get_test_org(0)  # Will have no subscriptions
            test_org_single_sub = self._get_test_org(1)  # Will have one subscription
            test_org_multiple_subs = self._get_test_org(2)  # Will have multiple subscriptions
            test_org_mixed_status = self._get_test_org(3)  # Will have mixed subscription statuses

            # Test 1: Organization with no subscriptions should return 0
            total_seats_no_subs = await self.org_subscription_dao.get_total_seat_count_for_org(
                db, test_org_no_subs.id
            )
            self.assertEqual(total_seats_no_subs, 0)

            # Create test subscription plans
            plan_data_basic = billing_schemas.SubscriptionPlanCreate(
                name="test_basic_seat_count_plan",
                description="Test basic plan for seat count testing",
                stripe_product_id="prod_basic_seat_test",
                max_seats=5,
                monthly_credits={
                    CreditType.WORKFLOWS.value: 100,
                    CreditType.WEB_SEARCHES.value: 500,
                    CreditType.DOLLAR_CREDITS.value: 25.0
                },
                monthly_price=29.99,
                annual_price=299.99,
                is_trial_eligible=True,
                trial_days=14
            )
            
            plan_data_premium = billing_schemas.SubscriptionPlanCreate(
                name="test_premium_seat_count_plan",
                description="Test premium plan for seat count testing",
                stripe_product_id="prod_premium_seat_test",
                max_seats=20,
                monthly_credits={
                    CreditType.WORKFLOWS.value: 500,
                    CreditType.WEB_SEARCHES.value: 2000,
                    CreditType.DOLLAR_CREDITS.value: 100.0
                },
                monthly_price=99.99,
                annual_price=999.99,
                is_trial_eligible=True,
                trial_days=7
            )

            basic_plan = await self.subscription_plan_dao.create(db=db, obj_in=plan_data_basic)
            premium_plan = await self.subscription_plan_dao.create(db=db, obj_in=plan_data_premium)
            self.created_entity_ids['subscription_plans'].extend([basic_plan.id, premium_plan.id])

            now = datetime_now_utc()

            # Test 2: Organization with single subscription
            single_subscription = billing_models.OrganizationSubscription(
                org_id=test_org_single_sub.id,
                plan_id=basic_plan.id,
                stripe_subscription_id="sub_single_seat_test",
                status=SubscriptionStatus.ACTIVE,
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                seats_count=3,  # 3 seats
                is_annual=False,
                is_trial_active=False,
                created_at=now,
                updated_at=now
            )
            
            single_subscription = await self.org_subscription_dao.create(db=db, obj_in=single_subscription)
            self.created_entity_ids['organization_subscriptions'].append(single_subscription.id)

            total_seats_single = await self.org_subscription_dao.get_total_seat_count_for_org(
                db, test_org_single_sub.id
            )
            self.assertEqual(total_seats_single, 3)

            # Test 3: Organization with multiple subscriptions (should sum them)
            subscription_1 = billing_models.OrganizationSubscription(
                org_id=test_org_multiple_subs.id,
                plan_id=basic_plan.id,
                stripe_subscription_id="sub_multiple_1_seat_test",
                status=SubscriptionStatus.ACTIVE,
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                seats_count=5,  # 5 seats
                is_annual=False,
                is_trial_active=False,
                created_at=now,
                updated_at=now
            )
            
            subscription_2 = billing_models.OrganizationSubscription(
                org_id=test_org_multiple_subs.id,
                plan_id=premium_plan.id,
                stripe_subscription_id="sub_multiple_2_seat_test",
                status=SubscriptionStatus.ACTIVE,
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                seats_count=8,  # 8 seats
                is_annual=True,
                is_trial_active=False,
                created_at=now,
                updated_at=now
            )
            
            subscription_1 = await self.org_subscription_dao.create(db=db, obj_in=subscription_1)
            subscription_2 = await self.org_subscription_dao.create(db=db, obj_in=subscription_2)
            self.created_entity_ids['organization_subscriptions'].extend([subscription_1.id, subscription_2.id])

            total_seats_multiple = await self.org_subscription_dao.get_total_seat_count_for_org(
                db, test_org_multiple_subs.id
            )
            self.assertEqual(total_seats_multiple, 13)  # 5 + 8 = 13

            # Test 4: Organization with mixed subscription statuses (should count all)
            active_subscription = billing_models.OrganizationSubscription(
                org_id=test_org_mixed_status.id,
                plan_id=basic_plan.id,
                stripe_subscription_id="sub_mixed_active_seat_test",
                status=SubscriptionStatus.ACTIVE,
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                seats_count=4,  # 4 seats
                is_annual=False,
                is_trial_active=False,
                created_at=now,
                updated_at=now
            )
            
            trial_subscription = billing_models.OrganizationSubscription(
                org_id=test_org_mixed_status.id,
                plan_id=premium_plan.id,
                stripe_subscription_id="sub_mixed_trial_seat_test",
                status=SubscriptionStatus.TRIAL,
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                seats_count=6,  # 6 seats
                is_annual=False,
                is_trial_active=True,
                trial_start=now,
                trial_end=now + timedelta(days=14),
                created_at=now,
                updated_at=now
            )
            
            past_due_subscription = billing_models.OrganizationSubscription(
                org_id=test_org_mixed_status.id,
                plan_id=basic_plan.id,
                stripe_subscription_id="sub_mixed_pastdue_seat_test",
                status=SubscriptionStatus.PAST_DUE,
                current_period_start=now - timedelta(days=30),
                current_period_end=now,
                seats_count=2,  # 2 seats
                is_annual=False,
                is_trial_active=False,
                created_at=now - timedelta(days=30),
                updated_at=now
            )
            
            active_subscription = await self.org_subscription_dao.create(db=db, obj_in=active_subscription)
            trial_subscription = await self.org_subscription_dao.create(db=db, obj_in=trial_subscription)
            past_due_subscription = await self.org_subscription_dao.create(db=db, obj_in=past_due_subscription)
            self.created_entity_ids['organization_subscriptions'].extend([
                active_subscription.id, trial_subscription.id, past_due_subscription.id
            ])

            total_seats_mixed = await self.org_subscription_dao.get_total_seat_count_for_org(
                db, test_org_mixed_status.id
            )
            self.assertEqual(total_seats_mixed, 12)  # 4 + 6 + 2 = 12

            # Test 5: Edge case - organization with zero-seat subscription
            zero_seat_subscription = billing_models.OrganizationSubscription(
                org_id=test_org_single_sub.id,  # Add to existing org with 3 seats
                plan_id=basic_plan.id,
                stripe_subscription_id="sub_zero_seat_test",
                status=SubscriptionStatus.CANCELED,
                current_period_start=now - timedelta(days=30),
                current_period_end=now,
                seats_count=0,  # 0 seats (edge case)
                is_annual=False,
                is_trial_active=False,
                created_at=now - timedelta(days=30),
                updated_at=now
            )
            
            zero_seat_subscription = await self.org_subscription_dao.create(db=db, obj_in=zero_seat_subscription)
            self.created_entity_ids['organization_subscriptions'].append(zero_seat_subscription.id)

            # Should still be 3 (original subscription) + 0 (zero seat subscription) = 3
            total_seats_with_zero = await self.org_subscription_dao.get_total_seat_count_for_org(
                db, test_org_single_sub.id
            )
            self.assertEqual(total_seats_with_zero, 3)

            # Test 6: Verify method returns integer type
            result = await self.org_subscription_dao.get_total_seat_count_for_org(
                db, test_org_no_subs.id
            )
            self.assertIsInstance(result, int)
            
            # Test 7: Non-existent organization should return 0
            non_existent_org_id = uuid.uuid4()
            total_seats_nonexistent = await self.org_subscription_dao.get_total_seat_count_for_org(
                db, non_existent_org_id
            )
            self.assertEqual(total_seats_nonexistent, 0)

            # Test 8: Performance test with large seat count
            large_seat_subscription = billing_models.OrganizationSubscription(
                org_id=test_org_single_sub.id,
                plan_id=premium_plan.id,
                stripe_subscription_id="sub_large_seat_test",
                status=SubscriptionStatus.ACTIVE,
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                seats_count=1000,  # Large seat count
                is_annual=True,
                is_trial_active=False,
                created_at=now,
                updated_at=now
            )
            
            large_seat_subscription = await self.org_subscription_dao.create(db=db, obj_in=large_seat_subscription)
            self.created_entity_ids['organization_subscriptions'].append(large_seat_subscription.id)

            # Should be 3 (original) + 0 (zero seats) + 1000 (large) = 1003
            total_seats_large = await self.org_subscription_dao.get_total_seat_count_for_org(
                db, test_org_single_sub.id
            )
            self.assertEqual(total_seats_large, 1003)

            # Test-specific cleanup verification: ensure our method handles deletions correctly
            # Delete one subscription and verify count updates
            await self.org_subscription_dao.remove(db, id=large_seat_subscription.id)
            total_after_deletion = await self.org_subscription_dao.get_total_seat_count_for_org(
                db, test_org_single_sub.id
            )
            self.assertEqual(total_after_deletion, 3)  # Back to original 3 seats

            print("✓ All seat count tests passed successfully!")
            print(f"✓ Test created and tracked {len(self.created_entity_ids['subscription_plans'])} plans and {len(self.created_entity_ids['organization_subscriptions'])} subscriptions for cleanup")

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
            await self.billing_service.apply_subscription_credits(db, subscription, plan, is_renewal=False)

            # Verify credits were allocated (multiplied by seat count: 3 seats)
            credit_balances = await self.billing_service.get_credit_balances(db, test_org.id)
            
            workflow_balance = next(b for b in credit_balances if b.credit_type == CreditType.WORKFLOWS)
            websearch_balance = next(b for b in credit_balances if b.credit_type == CreditType.WEB_SEARCHES)
            dollar_balance = next(b for b in credit_balances if b.credit_type == CreditType.DOLLAR_CREDITS)

            self.assertEqual(workflow_balance.credits_balance, 1500)  # 500 × 3 seats
            self.assertEqual(websearch_balance.credits_balance, 6000)  # 2000 × 3 seats
            self.assertEqual(dollar_balance.credits_balance, 300)  # 100 × 3 seats

            # Test regular renewal (not trial-to-paid)
            renewal_result = await self.billing_service.apply_subscription_credits(db, subscription, plan, is_renewal=True)
            
            self.assertTrue(renewal_result["success"])
            self.assertEqual(renewal_result["allocation_type"], "renewal_rotation")

            # Verify subscription remains active
            updated_subscription = await self.org_subscription_dao.get(db, subscription.id)
            self.assertEqual(updated_subscription.status, SubscriptionStatus.ACTIVE)
            self.assertFalse(updated_subscription.is_trial_active)


if __name__ == '__main__':
    unittest.main()
