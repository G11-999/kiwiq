"""
Tests for credit calculation functionality.

This module tests the credit calculator which estimates API credit consumption
for different LinkedIn scraping jobs.
"""

import math
import unittest
from unittest.mock import patch, MagicMock

from scraper_service.client.utils.enums import JobType
from scraper_service.credit_calculator import calculate_credits, _calculate_reaction_credits
from scraper_service.client.schemas import (
    PostsRequest,
    ProfileRequest,
    CompanyRequest,
    PostReactionsRequest,
    ProfilePostCommentsRequest,
    CompanyPostCommentsRequest
)

# Constants for testing
TEST_BATCH_SIZE = 50 
TEST_REACTION_BATCH_SIZE = 30


def setup_test_settings():
    """Set up mock settings for consistent test values."""
    mock_settings = MagicMock()
    mock_settings.BATCH_SIZE = TEST_BATCH_SIZE
    mock_settings.DEFAULT_POST_LIMIT = 50
    mock_settings.DEFAULT_REACTION_LIMIT = TEST_REACTION_BATCH_SIZE
    return mock_settings


class TestReactionCreditsCalculator(unittest.TestCase):
    """Tests for the reaction credits calculation helper function."""
    
    def setUp(self):
        """Set up test environment."""
        self.settings_patcher = patch('scraper_service.credit_calculator.rapid_api_settings', 
                                      setup_test_settings())
        self.mock_settings = self.settings_patcher.start()
        
    def tearDown(self):
        """Clean up test environment."""
        self.settings_patcher.stop()
        
    def test_zero_limit(self):
        """Test that zero limit returns zero credits."""
        min_credits, max_credits = _calculate_reaction_credits(0)
        self.assertEqual(min_credits, 1)
        self.assertEqual(max_credits, 1)
        
    def test_none_limit(self):
        """Test that None limit falls back to default limit."""
        min_credits, max_credits = _calculate_reaction_credits(None)
        expected = math.ceil(TEST_REACTION_BATCH_SIZE / TEST_REACTION_BATCH_SIZE)
        self.assertEqual(min_credits, expected)
        self.assertEqual(max_credits, expected)
        
    def test_single_batch(self):
        """Test that a small limit fits in a single batch."""
        min_credits, max_credits = _calculate_reaction_credits(TEST_REACTION_BATCH_SIZE)
        self.assertEqual(min_credits, 1)
        self.assertEqual(max_credits, 1)
        
    def test_multiple_batches(self):
        """Test that larger limits require multiple batches."""
        limit = TEST_REACTION_BATCH_SIZE * 2 + 1
        min_credits, max_credits = _calculate_reaction_credits(limit)
        expected = math.ceil(limit / TEST_REACTION_BATCH_SIZE)
        self.assertEqual(min_credits, expected)
        self.assertEqual(max_credits, expected)


class TestProfileCreditCalculator(unittest.TestCase):
    """Tests for profile credit calculation."""
    
    def setUp(self):
        """Set up test environment."""
        self.settings_patcher = patch('scraper_service.credit_calculator.rapid_api_settings', 
                                      setup_test_settings())
        self.mock_settings = self.settings_patcher.start()
        
    def tearDown(self):
        """Clean up test environment."""
        self.settings_patcher.stop()
        
    def test_user_profile_credits(self):
        """Test fetching a user profile costs 1 credit."""
        request = ProfileRequest(username="testuser")
        min_credits, max_credits = calculate_credits(JobType.FETCH_USER_PROFILE, request)
        self.assertEqual(min_credits, 1)
        self.assertEqual(max_credits, 1)
        
    def test_company_profile_credits(self):
        """Test fetching a company profile costs 1 credit."""
        request = CompanyRequest(username="testcompany")
        min_credits, max_credits = calculate_credits(JobType.FETCH_COMPANY_PROFILE, request)
        self.assertEqual(min_credits, 1)
        self.assertEqual(max_credits, 1)
        
    def test_wrong_request_type_for_profile(self):
        """Test that using the wrong request type raises TypeError."""
        request = PostsRequest(username="testuser")
        with self.assertRaises(TypeError):
            calculate_credits(JobType.FETCH_USER_PROFILE, request)
            
    def test_wrong_request_type_for_company(self):
        """Test that using the wrong request type for company profile raises TypeError."""
        request = PostsRequest(username="testcompany")
        with self.assertRaises(TypeError):
            calculate_credits(JobType.FETCH_COMPANY_PROFILE, request)


class TestPostListCreditCalculator(unittest.TestCase):
    """Tests for post list credit calculation (user posts, company posts, user likes)."""
    
    def setUp(self):
        """Set up test environment."""
        self.settings_patcher = patch('scraper_service.credit_calculator.rapid_api_settings', 
                                      setup_test_settings())
        self.mock_settings = self.settings_patcher.start()
        
        # Test job types for parametrization
        self.job_types = [
            JobType.FETCH_USER_POSTS,
            JobType.FETCH_COMPANY_POSTS,
            JobType.FETCH_USER_LIKES
        ]
        
    def tearDown(self):
        """Clean up test environment."""
        self.settings_patcher.stop()
    
    def test_zero_posts(self):
        """Test that explicitly setting post_limit=0 returns zero credits."""
        for job_type in self.job_types:
            with self.subTest(job_type=job_type):
                request = PostsRequest(username="testuser", post_limit=0)
                min_credits, max_credits = calculate_credits(job_type, request)
                self.assertEqual(min_credits, 0)
                self.assertEqual(max_credits, 0)
                
    def test_posts_only(self):
        """Test credit calculation for fetching posts without comments or reactions."""
        post_limit = 10
        for job_type in self.job_types:
            with self.subTest(job_type=job_type):
                request = PostsRequest(
                    username="testuser",
                    post_limit=post_limit,
                    post_comments="no",
                    post_reactions="no"
                )
                min_credits, max_credits = calculate_credits(job_type, request)
                expected = math.ceil(post_limit / TEST_BATCH_SIZE)
                self.assertEqual(min_credits, expected)
                self.assertEqual(max_credits, expected)
                
    def test_posts_with_comments(self):
        """Test credit calculation for fetching posts with comments."""
        post_limit = 10
        for job_type in self.job_types:
            with self.subTest(job_type=job_type):
                request = PostsRequest(
                    username="testuser",
                    post_limit=post_limit,
                    post_comments="yes",
                    post_reactions="no"
                )
                min_credits, max_credits = calculate_credits(job_type, request)
                # Base cost + 1 credit per post for comments
                expected = math.ceil(post_limit / TEST_BATCH_SIZE) + post_limit
                self.assertEqual(min_credits, expected)
                self.assertEqual(max_credits, expected)
                
    def test_posts_with_reactions(self):
        """Test credit calculation for fetching posts with reactions."""
        post_limit = 10
        reaction_limit = 30  # Fits in 1 batch
        for job_type in self.job_types:
            with self.subTest(job_type=job_type):
                request = PostsRequest(
                    username="testuser",
                    post_limit=post_limit,
                    post_comments="no",
                    post_reactions="yes",
                    reaction_limit=reaction_limit
                )
                min_credits, max_credits = calculate_credits(job_type, request)
                # Base cost + reaction cost per post
                reaction_batches = math.ceil(reaction_limit / TEST_REACTION_BATCH_SIZE)
                expected = math.ceil(post_limit / TEST_BATCH_SIZE) + (post_limit * reaction_batches)
                self.assertEqual(min_credits, expected)
                self.assertEqual(max_credits, expected)
                
    def test_posts_with_comments_and_reactions(self):
        """Test credit calculation for fetching posts with both comments and reactions."""
        post_limit = 10
        reaction_limit = 100  # Multiple batches
        for job_type in self.job_types:
            with self.subTest(job_type=job_type):
                request = PostsRequest(
                    username="testuser",
                    post_limit=post_limit,
                    post_comments="yes",
                    post_reactions="yes",
                    reaction_limit=reaction_limit
                )
                min_credits, max_credits = calculate_credits(job_type, request)
                # Base cost + (comment cost + reaction cost) per post
                reaction_batches = math.ceil(reaction_limit / TEST_REACTION_BATCH_SIZE)
                per_post_cost = 1 + reaction_batches  # 1 for comments + reaction batches
                expected = math.ceil(post_limit / TEST_BATCH_SIZE) + (post_limit * per_post_cost)
                self.assertEqual(min_credits, expected)
                self.assertEqual(max_credits, expected)
                
    def test_wrong_request_type(self):
        """Test that using the wrong request type raises TypeError."""
        for job_type in self.job_types:
            with self.subTest(job_type=job_type):
                request = ProfileRequest(username="testuser")
                with self.assertRaises(TypeError):
                    calculate_credits(job_type, request)
                    
    def test_large_post_limit(self):
        """Test with a large post limit that requires multiple batches."""
        post_limit = 150
        for job_type in self.job_types:
            with self.subTest(job_type=job_type):
                request = PostsRequest(username="testuser", post_limit=post_limit)
                min_credits, max_credits = calculate_credits(job_type, request)
                expected = math.ceil(post_limit / TEST_BATCH_SIZE)
                self.assertEqual(min_credits, expected)
                self.assertEqual(max_credits, expected)


class TestUserActivityCreditCalculator(unittest.TestCase):
    """Tests for user activity credit calculation (comments made by user)."""
    
    def setUp(self):
        """Set up test environment."""
        self.settings_patcher = patch('scraper_service.credit_calculator.rapid_api_settings', 
                                      setup_test_settings())
        self.mock_settings = self.settings_patcher.start()
        
    def tearDown(self):
        """Clean up test environment."""
        self.settings_patcher.stop()
        
    def test_user_comments_activity_credits(self):
        """Test fetching user comments activity costs 1 credit."""
        request = ProfileRequest(username="testuser")
        min_credits, max_credits = calculate_credits(JobType.FETCH_USER_COMMENTS_ACTIVITY, request)
        self.assertEqual(min_credits, 1)
        self.assertEqual(max_credits, 1)
        
    def test_wrong_request_type(self):
        """Test that using the wrong request type raises TypeError."""
        request = PostsRequest(username="testuser")
        with self.assertRaises(TypeError):
            calculate_credits(JobType.FETCH_USER_COMMENTS_ACTIVITY, request)


class TestSinglePostDetailsCreditCalculator(unittest.TestCase):
    """Tests for credit calculation when fetching details for a single post."""
    
    def setUp(self):
        """Set up test environment."""
        self.settings_patcher = patch('scraper_service.credit_calculator.rapid_api_settings', 
                                      setup_test_settings())
        self.mock_settings = self.settings_patcher.start()
        
    def tearDown(self):
        """Clean up test environment."""
        self.settings_patcher.stop()
        
    def test_post_reactions_credits(self):
        """Test credit calculation for fetching reactions for a single post."""
        request = PostReactionsRequest(post_url="http://some.url")
        min_credits, max_credits = calculate_credits(JobType.FETCH_POST_REACTIONS, request)
        # Uses default reaction limit from settings
        reaction_batches = math.ceil(TEST_REACTION_BATCH_SIZE / TEST_REACTION_BATCH_SIZE)
        self.assertEqual(min_credits, reaction_batches)
        self.assertEqual(max_credits, reaction_batches)
        
    def test_post_comments_profile_credits(self):
        """Test credit calculation for fetching comments for a profile post."""
        request = ProfilePostCommentsRequest(post_urn="urn:li:activity:123")
        min_credits, max_credits = calculate_credits(JobType.FETCH_POST_COMMENTS, request)
        self.assertEqual(min_credits, 1)
        self.assertEqual(max_credits, 1)
        
    def test_post_comments_company_credits(self):
        """Test credit calculation for fetching comments for a company post."""
        request = CompanyPostCommentsRequest(post_urn="urn:li:share:456")
        min_credits, max_credits = calculate_credits(JobType.FETCH_POST_COMMENTS, request)
        self.assertEqual(min_credits, 1)
        self.assertEqual(max_credits, 1)
        
    def test_wrong_request_type_reactions(self):
        """Test that using the wrong request type for post reactions raises TypeError."""
        request = ProfileRequest(username="testuser")
        with self.assertRaises(TypeError):
            calculate_credits(JobType.FETCH_POST_REACTIONS, request)
            
    def test_wrong_request_type_comments(self):
        """Test that using the wrong request type for post comments raises TypeError."""
        request = PostsRequest(username="testuser")
        with self.assertRaises(TypeError):
            calculate_credits(JobType.FETCH_POST_COMMENTS, request)


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and error handling in credit calculation."""
    
    def setUp(self):
        """Set up test environment."""
        self.settings_patcher = patch('scraper_service.credit_calculator.rapid_api_settings', 
                                      setup_test_settings())
        self.mock_settings = self.settings_patcher.start()
        
        # Create a mock logger to prevent actual logging during tests
        self.logger_patcher = patch('scraper_service.credit_calculator.logger')
        self.mock_logger = self.logger_patcher.start()
        
    def tearDown(self):
        """Clean up test environment."""
        self.settings_patcher.stop()
        self.logger_patcher.stop()
        
    def test_unknown_job_type(self):
        """Test handling an unknown job type."""
        # Create a mock job type that doesn't exist in the real enum, here i am testing that only specific job types are allowed
        mock_job_type = MagicMock()
        mock_job_type.value = "unknown_job_type"
        
        request = ProfileRequest(username="testuser")
        # Should log a warning and return 0 credits, here i am testing that only specific job types are allowed
        min_credits, max_credits = calculate_credits(mock_job_type, request)
        
        # Verify warning was logged
        self.mock_logger.warning.assert_called_once()
        
        # Verify zero credits returned
        self.assertEqual(min_credits, 0)
        self.assertEqual(max_credits, 0)


if __name__ == "__main__":
    unittest.main()
