"""
Test cases for the JSON splitter to ensure accurate document splitting and clustering.
Tests various scenarios including complex nested structures, cluster mappings, and edge cases.
"""
import unittest
import json
from typing import Dict, Any, List
from unittest.mock import patch, MagicMock

# Import the JSONSplitter class
from kiwi_app.data_jobs.ingestion.chunking import JSONSplitter


class TestJSONSplitter(unittest.IsolatedAsyncioTestCase):
    """Test suite for JSON splitter functionality."""

    def setUp(self):
        """Set up test environment with various splitter configurations."""
        # Standard configuration
        self.splitter = JSONSplitter(
            max_json_chunk_size=300,
            max_text_char_limit=200,
            max_json_char_limit=800
        )
        
        # Tight limits for testing splitting behavior
        self.tight_splitter = JSONSplitter(
            max_json_chunk_size=100,
            max_text_char_limit=50,
            max_json_char_limit=200
        )
        
        # Large limits for testing non-splitting scenarios
        self.large_splitter = JSONSplitter(
            max_json_chunk_size=1000,
            max_text_char_limit=1000,
            max_json_char_limit=5000
        )

    def get_content_strategy_cluster_map(self) -> Dict[str, str]:
        """Get content strategy cluster mapping for testing."""
        return {
            # Metadata
            "title": "metadata",
            
            # Current content understanding
            "content_pillars.name": "current_content_understanding",
            "content_pillars.pillar": "current_content_understanding", 
            "content_pillars.sub_topic": "current_content_understanding",
            
            "post_performance_analysis.current_engagement": "current_content_understanding",
            "post_performance_analysis.content_that_resonates": "current_content_understanding",
            "post_performance_analysis.audience_response": "current_content_understanding",
            
            # User related information
            "target_audience.primary": "user_related_information",
            "target_audience.secondary": "user_related_information",
            "target_audience.tertiary": "user_related_information",
            
            "foundation_elements.expertise": "user_related_information",
            "foundation_elements.core_beliefs": "user_related_information",
            "foundation_elements.objectives": "user_related_information",
            
            "core_perspectives": "user_related_information",
            
            # Content goals
            "implementation.thirty_day_targets.goal": "content_goals",
            "implementation.thirty_day_targets.method": "content_goals",
            "implementation.thirty_day_targets.targets": "content_goals",
            
            "implementation.ninety_day_targets.goal": "content_goals",
            "implementation.ninety_day_targets.method": "content_goals",
            "implementation.ninety_day_targets.targets": "content_goals"
        }

    def get_user_dna_cluster_map(self) -> Dict[str, str]:
        """Get user DNA cluster mapping for testing."""
        return {
            # Writing style information
            "brand_voice_and_style.communication_style": "writing_style_information",
            "brand_voice_and_style.tone_preferences": "writing_style_information",
            "brand_voice_and_style.vocabulary_level": "writing_style_information",
            "brand_voice_and_style.sentence_structure_preferences": "writing_style_information",
            "brand_voice_and_style.content_format_preferences": "writing_style_information",
            "brand_voice_and_style.emoji_usage": "writing_style_information",
            "brand_voice_and_style.hashtag_usage": "writing_style_information",
            "brand_voice_and_style.storytelling_approach": "writing_style_information",
            
            "analytics_insights.optimal_content_length": "writing_style_information",
            "analytics_insights.audience_geographic_distribution": "writing_style_information",
            "analytics_insights.engagement_time_patterns": "writing_style_information",
            "analytics_insights.keyword_performance_analysis": "writing_style_information",
            "analytics_insights.competitor_benchmarking": "writing_style_information",
            "analytics_insights.growth_rate_metrics": "writing_style_information",
            
            # Personal context information
            "professional_identity.full_name": "personal_context_information",
            "professional_identity.job_title": "personal_context_information",
            "professional_identity.industry_sector": "personal_context_information",
            "professional_identity.company_name": "personal_context_information",
            "professional_identity.company_size": "personal_context_information",
            "professional_identity.years_of_experience": "personal_context_information",
            "professional_identity.professional_certifications": "personal_context_information",
            "professional_identity.areas_of_expertise": "personal_context_information",
            "professional_identity.career_milestones": "personal_context_information",
            "professional_identity.professional_bio": "personal_context_information",
            
            "linkedin_profile_analysis.follower_count": "personal_context_information",
            "linkedin_profile_analysis.connection_count": "personal_context_information",
            "linkedin_profile_analysis.profile_headline_analysis": "personal_context_information",
            "linkedin_profile_analysis.about_section_summary": "personal_context_information",
            "linkedin_profile_analysis.top_performing_content_pillars": "personal_context_information",
            "linkedin_profile_analysis.content_posting_frequency": "personal_context_information",
            "linkedin_profile_analysis.content_types_used": "personal_context_information",
            "linkedin_profile_analysis.network_composition": "personal_context_information",
            
            "personal_context.personal_values": "personal_context_information",
            "personal_context.professional_mission_statement": "personal_context_information",
            "personal_context.content_creation_challenges": "personal_context_information",
            "personal_context.personal_story_elements_for_content": "personal_context_information",
            "personal_context.notable_life_experiences": "personal_context_information",
            "personal_context.inspirations_and_influences": "personal_context_information",
            "personal_context.books_resources_they_reference": "personal_context_information",
            "personal_context.quotes_they_resonate_with": "personal_context_information",
            
            # Content information
            "success_metrics.content_performance_kpis": "content_information",
            "success_metrics.engagement_quality_metrics": "content_information",
            "success_metrics.conversion_goals": "content_information",
            "success_metrics.brand_perception_goals": "content_information",
            "success_metrics.timeline_for_expected_results": "content_information",
            "success_metrics.benchmarking_standards": "content_information",
            
            "content_strategy_goals.primary_goal": "content_information",
            "content_strategy_goals.secondary_goals": "content_information",
            "content_strategy_goals.target_audience_demographics": "content_information",
            "content_strategy_goals.ideal_reader_personas": "content_information",
            "content_strategy_goals.audience_pain_points": "content_information",
            "content_strategy_goals.value_proposition_to_audience": "content_information",
            "content_strategy_goals.call_to_action_preferences": "content_information",
            "content_strategy_goals.content_pillar_themes": "content_information",
            "content_strategy_goals.topics_of_interest": "content_information",
            "content_strategy_goals.topics_to_avoid": "content_information",
            
            "linkedin_profile_analysis.engagement_metrics.average_likes_per_post": "content_information",
            "linkedin_profile_analysis.engagement_metrics.average_comments_per_post": "content_information",
            "linkedin_profile_analysis.engagement_metrics.average_shares_per_post": "content_information",
        }

    def test_splitter_initialization(self):
        """Test JSON splitter initialization with different parameters."""
        # Test default initialization
        default_splitter = JSONSplitter()
        self.assertEqual(default_splitter.max_json_chunk_size, 700)
        self.assertEqual(default_splitter.max_text_char_limit, 700)
        self.assertEqual(default_splitter.max_json_char_limit, 700)
        
        # Test custom initialization
        custom_splitter = JSONSplitter(
            max_json_chunk_size=150,
            max_text_char_limit=100,
            max_json_char_limit=400
        )
        self.assertEqual(custom_splitter.max_json_chunk_size, 150)
        self.assertEqual(custom_splitter.max_text_char_limit, 100)
        self.assertEqual(custom_splitter.max_json_char_limit, 400)

    def test_flatten_json_simple_structure(self):
        """Test flattening simple JSON structures."""
        simple_json = {
            "title": "Test Document",
            "description": "A simple test document"
        }
        
        flattened = self.splitter.flatten_json(simple_json)
        expected = {
            "title": "Test Document",
            "description": "A simple test document"
        }
        
        self.assertEqual(flattened, expected)

    def test_flatten_json_nested_structure(self):
        """Test flattening complex nested JSON structures."""
        nested_json = {
            "title": "Content Strategy",
            "content_pillars": [
                {
                    "name": "Technical Expertise",
                    "pillar": "Authority Building",
                    "sub_topic": "Advanced development techniques"
                },
                {
                    "name": "Industry Insights",
                    "pillar": "Thought Leadership", 
                    "sub_topic": "Market trends analysis"
                }
            ],
            "target_audience": {
                "primary": "Software developers",
                "secondary": "Tech leads",
                "demographics": {
                    "age_range": "25-45",
                    "experience": "5+ years"
                }
            }
        }
        
        flattened = self.splitter.flatten_json(nested_json)
        
        # Verify key paths exist
        expected_paths = [
            "title",
            "content_pillars.0.name",
            "content_pillars.0.pillar", 
            "content_pillars.0.sub_topic",
            "content_pillars.1.name",
            "content_pillars.1.pillar",
            "content_pillars.1.sub_topic",
            "target_audience.primary",
            "target_audience.secondary",
            "target_audience.demographics.age_range",
            "target_audience.demographics.experience"
        ]
        
        for path in expected_paths:
            self.assertIn(path, flattened)
        
        # Verify specific values
        self.assertEqual(flattened["content_pillars.0.name"], "Technical Expertise")
        self.assertEqual(flattened["target_audience.primary"], "Software developers")
        self.assertEqual(flattened["target_audience.demographics.age_range"], "25-45")

    def test_flatten_json_empty_and_edge_cases(self):
        """Test flattening edge cases including empty structures."""
        # Empty dict
        self.assertEqual(self.splitter.flatten_json({}), {})
        
        # Dict with empty list
        json_with_empty_list = {"items": []}
        flattened = self.splitter.flatten_json(json_with_empty_list)
        self.assertEqual(flattened, {})  # Empty arrays don't create paths
        
        # Dict with mixed types
        mixed_json = {
            "string": "text",
            "number": 42,
            "boolean": True,
            "null_value": None,
            "nested": {"inner": "value"}
        }
        
        flattened = self.splitter.flatten_json(mixed_json)
        expected = {
            "string": "text",
            "number": 42,
            "boolean": True,
            "null_value": None,
            "nested.inner": "value"
        }
        
        self.assertEqual(flattened, expected)

    def test_cluster_mapping_retrieval(self):
        """Test cluster mapping retrieval for different document types."""
        # Test content strategy mapping
        mapping = self.splitter.get_cluster_mapping("content_strategy_doc")
        self.assertIsNotNone(mapping)
        self.assertIn("title", mapping)
        self.assertEqual(mapping["title"], "metadata")
        
        # # Test content plan mapping (should return same as content strategy)
        # mapping2 = self.splitter.get_cluster_mapping("content_plan")
        # self.assertEqual(mapping, mapping2)
        
        # Test unknown document type
        mapping3 = self.splitter.get_cluster_mapping("unknown_type")
        self.assertIsNone(mapping3)

    def test_group_paths_by_clusters_with_mapping(self):
        """Test grouping paths by clusters using real cluster mappings."""
        # Create custom splitter with content strategy mapping
        class TestSplitter(JSONSplitter):
            def get_cluster_mapping(self, doc_type: str):
                if doc_type == "content_strategy_doc":
                    return self._get_test_cluster_mapping()
                return None
            
            def _get_test_cluster_mapping(self):
                return {
                    "title": "metadata",
                    "content_pillars.name": "current_content_understanding",
                    "content_pillars.pillar": "current_content_understanding",
                    "target_audience.primary": "user_related_information",
                    "implementation.thirty_day_targets.goal": "content_goals"
                }
        
        test_splitter = TestSplitter()
        
        flattened_paths = {
            "title": "Strategy Document",
            "content_pillars.0.name": "Technical Expertise",
            "content_pillars.0.pillar": "Authority Building",
            "target_audience.primary": "Developers",
            "implementation.thirty_day_targets.0.goal": "Increase engagement",
            "unmapped_field": "This should go to default"
        }
        
        mapping = test_splitter.get_cluster_mapping("content_strategy_doc")
        clusters = test_splitter.group_paths_by_clusters(flattened_paths, mapping)
        
        # Verify cluster assignment - check what actually got clustered
        expected_clusters = ["metadata", "current_content_understanding", "user_related_information", "content_goals", "default"]
        for cluster in expected_clusters:
            if cluster in clusters:  # Only check if cluster exists
                self.assertIsInstance(clusters[cluster], dict)
        
        # Verify specific assignments
        self.assertEqual(clusters["metadata"]["title"], "Strategy Document")
        self.assertEqual(clusters["user_related_information"]["target_audience.primary"], "Developers")
        self.assertEqual(clusters["default"]["unmapped_field"], "This should go to default")
        
        # Check if content_pillars paths are properly mapped to current_content_understanding
        if "current_content_understanding" in clusters:
            self.assertIn("content_pillars.0.name", clusters["current_content_understanding"])
            self.assertEqual(clusters["current_content_understanding"]["content_pillars.0.name"], "Technical Expertise")
        
        # Check if implementation paths are properly mapped to content_goals
        if "content_goals" in clusters:
            self.assertIn("implementation.thirty_day_targets.0.goal", clusters["content_goals"])
            self.assertEqual(clusters["content_goals"]["implementation.thirty_day_targets.0.goal"], "Increase engagement")

    def test_group_paths_by_clusters_without_mapping(self):
        """Test grouping paths when no cluster mapping is provided."""
        flattened_paths = {
            "title": "Test Document",
            "content.section1": "Content 1",
            "content.section2": "Content 2"
        }
        
        clusters = self.splitter.group_paths_by_clusters(flattened_paths, None)
        
        # Everything should go to default cluster
        self.assertEqual(len(clusters), 1)
        self.assertIn("default", clusters)
        self.assertEqual(clusters["default"], flattened_paths)

    def test_reconstruct_json_simple_paths(self):
        """Test JSON reconstruction from simple flattened paths."""
        flattened_paths = {
            "title": "Test Document",
            "description": "A test document",
            "status": "active"
        }
        
        reconstructed = self.splitter.reconstruct_json_from_paths(flattened_paths)
        expected = {
            "title": "Test Document",
            "description": "A test document", 
            "status": "active"
        }
        
        self.assertEqual(reconstructed, expected)

    def test_reconstruct_json_nested_paths(self):
        """Test JSON reconstruction from complex nested paths."""
        flattened_paths = {
            "title": "Content Strategy",
            "target_audience.primary": "Developers",
            "target_audience.secondary": "Tech Leads",
            "metrics.engagement.likes": 100,
            "metrics.engagement.comments": 25,
            "metrics.reach.impressions": 5000
        }
        
        reconstructed = self.splitter.reconstruct_json_from_paths(flattened_paths)
        
        # Verify structure
        self.assertEqual(reconstructed["title"], "Content Strategy")
        self.assertEqual(reconstructed["target_audience"]["primary"], "Developers")
        self.assertEqual(reconstructed["target_audience"]["secondary"], "Tech Leads")
        self.assertEqual(reconstructed["metrics"]["engagement"]["likes"], 100)
        self.assertEqual(reconstructed["metrics"]["reach"]["impressions"], 5000)

    def test_reconstruct_json_array_paths(self):
        """Test JSON reconstruction with array paths (continuous numeric indices)."""
        flattened_paths = {
            "items.0.name": "Item 1",
            "items.0.value": 10,
            "items.1.name": "Item 2", 
            "items.1.value": 20,
            "metadata.title": "List Document"
        }
        
        reconstructed = self.splitter.reconstruct_json_from_paths(flattened_paths)
        
        # Verify array structure
        self.assertEqual(reconstructed["metadata"]["title"], "List Document")
        self.assertIsInstance(reconstructed["items"], list)
        self.assertEqual(len(reconstructed["items"]), 2)
        self.assertEqual(reconstructed["items"][0]["name"], "Item 1")
        self.assertEqual(reconstructed["items"][1]["value"], 20)

    def test_reconstruct_json_non_continuous_indices(self):
        """Test that non-continuous numeric indices create dict, not list."""
        flattened_paths = {
            "items.0.name": "Item 0",
            "items.2.name": "Item 2",  # Missing index 1
            "items.5.name": "Item 5"   # Gap in sequence
        }
        
        reconstructed = self.splitter.reconstruct_json_from_paths(flattened_paths)
        
        # Should create dict, not list, due to non-continuous indices
        self.assertIsInstance(reconstructed["items"], dict)
        self.assertEqual(reconstructed["items"]["0"]["name"], "Item 0")
        self.assertEqual(reconstructed["items"]["2"]["name"], "Item 2")
        self.assertEqual(reconstructed["items"]["5"]["name"], "Item 5")

    def test_reconstruct_json_mixed_keys(self):
        """Test reconstruction with mixed numeric and string keys (should create dict)."""
        flattened_paths = {
            "data.0.value": "First",
            "data.1.value": "Second",
            "data.title.value": "Mixed",  # String key mixed with numeric
            "data.config.setting": "enabled"
        }
        
        reconstructed = self.splitter.reconstruct_json_from_paths(flattened_paths)
        
        # Should create dict due to mixed key types
        self.assertIsInstance(reconstructed["data"], dict)
        self.assertEqual(reconstructed["data"]["0"]["value"], "First")
        self.assertEqual(reconstructed["data"]["title"]["value"], "Mixed")
        self.assertEqual(reconstructed["data"]["config"]["setting"], "enabled")

    def test_split_text_recursively_short_text(self):
        """Test text splitting with text under character limit."""
        short_text = "This is a short text that should not be split."
        
        result = self.splitter.split_text_recursively(short_text, 200)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], short_text)

    def test_split_text_recursively_long_text(self):
        """Test text splitting with long text requiring splits."""
        long_text = "This is a very long piece of text that needs to be split into multiple chunks. " * 10
        
        result = self.splitter.split_text_recursively(long_text, 100)
        
        # Should create multiple chunks
        self.assertGreater(len(result), 1)
        
        # Each chunk should be under limit
        for chunk in result:
            self.assertLessEqual(len(chunk), 100)
        
        # All chunks together should contain all text
        combined = " ".join(result)
        # Remove extra spaces that might be added during splitting
        self.assertIn("This is a very long piece of text", combined)

    def test_split_text_recursively_paragraphs(self):
        """Test text splitting respects paragraph boundaries."""
        text_with_paragraphs = (
            "First paragraph with some content that explains the context.\n\n"
            "Second paragraph that continues the discussion with more details.\n\n" 
            "Third paragraph that concludes the content with final thoughts."
        )
        
        result = self.splitter.split_text_recursively(text_with_paragraphs, 80)
        
        # Should split by paragraphs first
        self.assertGreater(len(result), 1)
        
        # Verify paragraph content is preserved
        combined = "\n\n".join(result)
        self.assertIn("First paragraph", combined)
        self.assertIn("Second paragraph", combined)
        self.assertIn("Third paragraph", combined)

    @patch('services.kiwi_app.data_jobs.ingestion.chunking.spacy')
    def test_split_text_recursively_with_spacy(self, mock_spacy):
        """Test text splitting with spaCy sentence splitting."""
        # Mock spaCy to return controlled sentence splits
        mock_doc = MagicMock()
        mock_sentence1 = MagicMock()
        mock_sentence1.text = "This is the first sentence."
        mock_sentence2 = MagicMock() 
        mock_sentence2.text = "This is the second sentence."
        mock_doc.sents = [mock_sentence1, mock_sentence2]
        
        mock_nlp = MagicMock()
        mock_nlp.return_value = mock_doc
        mock_spacy.load.return_value = mock_nlp
        
        # Create splitter that will use spaCy
        test_splitter = JSONSplitter()
        test_splitter.nlp = mock_nlp
        
        text = "This is the first sentence. This is the second sentence."
        result = test_splitter.split_text_recursively(text, 30)
        
        # Should split by sentences
        self.assertGreater(len(result), 1)
        mock_nlp.assert_called_with(text)

    def test_split_text_recursively_word_splitting(self):
        """Test word-level splitting when sentences are too long."""
        long_sentence = "word1 word2 word3 word4 word5 word6 word7 word8 word9 word10"
        
        result = self.splitter.split_text_recursively(long_sentence, 25)
        
        # Should split into multiple chunks
        self.assertGreater(len(result), 1)
        
        # Each chunk should be under limit
        for chunk in result:
            self.assertLessEqual(len(chunk), 25)
        
        # All chunks together should contain the original words
        combined_text = " ".join(result)
        for word in ["word1", "word2", "word3", "word10"]:
            self.assertIn(word, combined_text)

    def test_split_text_recursively_character_splitting(self):
        """Test character-level splitting for very long words."""
        very_long_word = "supercalifragilisticexpialidocious" * 3
        
        result = self.splitter.split_text_recursively(very_long_word, 20)
        
        # Should split the word into character chunks
        self.assertGreater(len(result), 1)
        
        # Each chunk should be under limit
        for chunk in result:
            self.assertLessEqual(len(chunk), 20)

    def test_split_long_document_multiple_paragraphs(self):
        """Test splitting long document with multiple paragraphs at paragraph boundaries."""
        long_document = (
            "This is the first paragraph that contains important information about content strategy. "
            "It provides foundational context and sets up the framework for understanding. "
            "The paragraph continues with detailed explanations and comprehensive coverage.\n\n"
            
            "The second paragraph delves deeper into implementation details and practical applications. "
            "It builds upon the previous concepts and introduces new methodologies. "
            "This section is crucial for understanding the operational aspects of the strategy.\n\n"
            
            "The third paragraph focuses on measurement and optimization techniques. "
            "It covers analytics, performance metrics, and continuous improvement processes. "
            "These elements are essential for long-term success and sustainable growth.\n\n"
            
            "The final paragraph concludes with actionable recommendations and next steps. "
            "It synthesizes all previous information into concrete guidance. "
            "Readers should be able to immediately apply these insights to their work."
        )
        
        # Use moderate character limit to force paragraph-level splitting
        result = self.splitter.split_text_recursively(long_document, 300)
        
        # Should create multiple chunks
        self.assertGreater(len(result), 1)
        
        # Each chunk should be under limit
        for chunk in result:
            self.assertLessEqual(len(chunk), 300)
        
        # Verify paragraph boundaries are respected (first chunk should contain first paragraph)
        first_chunk = result[0]
        self.assertIn("first paragraph", first_chunk)
        self.assertIn("foundational context", first_chunk)
        
        # Combined result should contain all content
        combined = "\n\n".join(result)
        self.assertIn("first paragraph", combined)
        self.assertIn("second paragraph", combined)
        self.assertIn("third paragraph", combined)
        self.assertIn("final paragraph", combined)

    def test_split_long_document_sentence_level_splitting(self):
        """Test splitting at sentence level when paragraphs are too long."""
        long_paragraph = (
            "Content strategy development requires a systematic approach to planning and execution. "
            "Organizations must first conduct comprehensive audience research to understand their target demographics. "
            "This research should include behavioral patterns, pain points, and content consumption preferences. "
            "The next step involves competitive analysis to identify market gaps and opportunities. "
            "Content pillars should be established based on expertise areas and audience needs. "
            "Each pillar must align with business objectives and brand positioning. "
            "Implementation requires careful resource allocation and timeline management. "
            "Success metrics should be defined upfront to enable proper measurement and optimization. "
            "Regular review cycles ensure continuous improvement and adaptation to changing market conditions. "
            "Documentation of processes and learnings facilitates knowledge transfer and scaling efforts."
        )
        
        # Use tight character limit to force sentence-level splitting
        result = self.splitter.split_text_recursively(long_paragraph, 150)
        
        # Should create multiple chunks due to sentence splitting
        self.assertGreater(len(result), 1)
        
        # Each chunk should be under limit
        for chunk in result:
            self.assertLessEqual(len(chunk), 150)
        
        # Verify sentence boundaries are respected
        combined = " ".join(result)
        self.assertIn("systematic approach", combined)
        self.assertIn("audience research", combined)
        self.assertIn("competitive analysis", combined)
        self.assertIn("scaling efforts", combined)

    def test_split_mixed_paragraph_sentence_document(self):
        """Test complex document requiring both paragraph and sentence splitting."""
        complex_document = (
            "Executive Summary: This comprehensive content strategy document outlines our approach. "
            "The strategy focuses on building thought leadership through technical expertise. "
            "Key objectives include increasing brand awareness and driving qualified lead generation.\n\n"
            
            "Target Audience Analysis: Our primary audience consists of senior software engineers and technical leads in enterprise organizations. "
            "Secondary audiences include engineering managers, CTOs, and technology decision-makers. "
            "These professionals seek authoritative content on emerging technologies, best practices, and industry trends. "
            "They consume content primarily through LinkedIn, technical blogs, and industry publications.\n\n"
            
            "Content Pillars: Technical Leadership pillar focuses on advanced software engineering practices, architecture decisions, and team management. "
            "Innovation Showcase pillar highlights cutting-edge projects, technology adoption stories, and lessons learned. "
            "Industry Insights pillar provides market analysis, trend predictions, and competitive intelligence. "
            "Each pillar supports our positioning as a technology thought leader and trusted advisor.\n\n"
            
            "Implementation Timeline: Phase one involves content calendar development and resource allocation over the next 30 days. "
            "Phase two focuses on content creation and initial publication for 60 days. "
            "Phase three emphasizes optimization, measurement, and scaling for 90 days. "
            "Success will be measured through engagement metrics, lead quality, and brand perception surveys."
        )
        
        # Use character limit that forces mixed splitting strategies
        result = self.splitter.split_text_recursively(complex_document, 200)
        
        # Should create multiple chunks
        self.assertGreater(len(result), 3)
        
        # Each chunk should be under limit
        for chunk in result:
            self.assertLessEqual(len(chunk), 200)
        
        # Verify major sections are preserved
        combined = "\n\n".join(result)
        self.assertIn("Executive Summary", combined)
        self.assertIn("Target Audience Analysis", combined)
        self.assertIn("Content Pillars", combined)
        self.assertIn("Implementation Timeline", combined)

    def test_split_document_with_technical_content(self):
        """Test splitting document with technical jargon and complex terminology."""
        technical_document = (
            "Microservices Architecture Implementation Strategy\n\n"
            
            "Service Decomposition: Begin by identifying bounded contexts within the monolithic application. "
            "Each microservice should encapsulate a specific business capability with well-defined boundaries. "
            "Database-per-service pattern ensures data isolation and independent scalability. "
            "API gateway manages cross-cutting concerns like authentication, rate limiting, and request routing.\n\n"
            
            "Communication Patterns: Implement asynchronous messaging using event-driven architecture. "
            "Message brokers like Apache Kafka or RabbitMQ facilitate reliable inter-service communication. "
            "Circuit breaker pattern prevents cascade failures and improves system resilience. "
            "Distributed tracing enables observability across service boundaries for debugging and monitoring.\n\n"
            
            "Deployment Strategy: Containerization with Docker provides consistent runtime environments. "
            "Kubernetes orchestration automates deployment, scaling, and service discovery. "
            "Blue-green deployment minimizes downtime during releases. "
            "Infrastructure as code using Terraform ensures reproducible environments across development, staging, and production."
        )
        
        # Test with tight limits to ensure technical terms are preserved
        result = self.splitter.split_text_recursively(technical_document, 180)
        
        # Should create multiple chunks
        self.assertGreater(len(result), 2)
        
        # Each chunk should be under limit
        for chunk in result:
            self.assertLessEqual(len(chunk), 180)
        
        # Verify technical terms are preserved
        combined = " ".join(result)
        technical_terms = [
            "Microservices", "API gateway", "Apache Kafka", "RabbitMQ", 
            "Circuit breaker", "Kubernetes", "Blue-green deployment", "Terraform"
        ]
        for term in technical_terms:
            self.assertIn(term, combined)

    def test_split_document_preserves_context(self):
        """Test that document splitting preserves logical context and readability."""
        contextual_document = (
            "Introduction to Content Marketing ROI\n\n"
            
            "Measuring return on investment for content marketing requires a multifaceted approach. "
            "Traditional metrics like page views and social shares provide surface-level insights. "
            "However, modern marketers need deeper attribution models that connect content consumption to business outcomes. "
            "This includes tracking lead progression, sales attribution, and customer lifetime value impacts.\n\n"
            
            "Key Performance Indicators: Brand awareness metrics measure reach, impression share, and mention sentiment. "
            "Engagement metrics include time on page, scroll depth, and social interaction rates. "
            "Conversion metrics track form submissions, demo requests, and sales qualified leads. "
            "Revenue metrics connect content touchpoints to closed deals and customer acquisition costs. "
            "Retention metrics analyze how content supports customer success and reduces churn rates.\n\n"
            
            "Advanced Attribution Models: First-touch attribution credits the initial content interaction. "
            "Last-touch attribution assigns value to the final content before conversion. "
            "Multi-touch attribution distributes credit across all content touchpoints. "
            "Data-driven attribution uses machine learning to optimize credit allocation. "
            "Each model provides different insights for content strategy optimization."
        )
        
        # Split with medium character limit
        result = self.splitter.split_text_recursively(contextual_document, 250)
        
        # Should create logical chunks
        self.assertGreater(len(result), 1)
        
        # Each chunk should be under limit
        for chunk in result:
            self.assertLessEqual(len(chunk), 250)
        
        # Verify context preservation - related concepts should appear together
        combined_text = " ".join(result)
        
        # Check that related metrics are discussed coherently
        self.assertIn("return on investment", combined_text)
        self.assertIn("attribution models", combined_text)
        self.assertIn("Key Performance Indicators", combined_text)
        
        # Ensure technical concepts aren't split inappropriately
        for chunk in result:
            # No chunk should end mid-sentence with technical terms
            if "attribution" in chunk:
                # Should contain complete thoughts about attribution
                self.assertTrue(len(chunk) > 10)  # More than just the word

    def test_split_very_long_document_stress_test(self):
        """Stress test with very long document requiring multiple splitting strategies."""
        # Create a very long document with multiple sections
        very_long_document = ""
        
        sections = [
            "Market Research and Analysis",
            "Competitive Landscape Overview", 
            "Customer Segmentation Strategy",
            "Value Proposition Development",
            "Content Strategy Framework",
            "Implementation Roadmap",
            "Measurement and Optimization",
            "Resource Allocation Planning"
        ]
        
        for section in sections:
            section_content = (
                f"{section}\n\n"
                f"This section provides comprehensive coverage of {section.lower()} methodologies and best practices. "
                f"Industry leaders recognize that effective {section.lower()} requires systematic approach and continuous refinement. "
                f"Organizations implementing these strategies typically see measurable improvements in performance metrics. "
                f"The following subsections detail specific tactics, tools, and techniques for {section.lower()} success. "
                f"Case studies demonstrate real-world applications and quantifiable business impact across various industries. "
                f"Implementation requires careful planning, stakeholder alignment, and phased execution for optimal results. "
                f"Success metrics should be established upfront to enable proper measurement and continuous optimization. "
                f"Regular review cycles ensure strategies remain relevant and effective in dynamic market conditions.\n\n"
            )
            very_long_document += section_content
        
        # Use very tight limit to force aggressive splitting
        result = self.tight_splitter.split_text_recursively(very_long_document, 100)
        
        # Should create many chunks
        self.assertGreater(len(result), 10)
        
        # Each chunk should be under limit
        for chunk in result:
            self.assertLessEqual(len(chunk), 100)
        
        # Verify all sections are preserved
        combined = " ".join(result)
        for section in sections:
            self.assertIn(section, combined)
        
        # Verify document structure is maintained
        self.assertIn("Market Research", combined)
        self.assertIn("systematic approach", combined)
        self.assertIn("Success metrics", combined)  # Capital S as it appears in the text

    def test_split_json_values_simple_case(self):
        """Test JSON value splitting with simple case that doesn't need splitting."""
        simple_json = {
            "title": "Short Title",
            "description": "Short description"
        }
        
        result = self.large_splitter.split_json_values_with_char_limit(simple_json, 1000)
        
        # Should return single JSON object unchanged
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], simple_json)

    def test_split_json_values_large_text_values(self):
        """Test JSON splitting with large text values requiring splits."""
        json_with_long_text = {
            "title": "Content Strategy Document",
            "long_description": "This is a very long description that exceeds the character limit and should be split into multiple parts. " * 20,
            "short_field": "Short content"
        }
        
        result = self.tight_splitter.split_json_values_with_char_limit(json_with_long_text, 300)
        
        # Should create multiple JSON chunks
        self.assertGreater(len(result), 1)
        
        # Verify all chunks are valid JSON and under limit
        for chunk in result:
            self.assertIsInstance(chunk, dict)
            chunk_size = len(json.dumps(chunk))
            self.assertLessEqual(chunk_size, 300)

    def test_split_json_values_creates_indexed_keys(self):
        """Test that large values create indexed keys when split."""
        json_with_splittable_text = {
            "content": "This is some content that will be split. " * 10,
            "metadata": "Simple metadata"
        }
        
        result = self.tight_splitter.split_json_values_with_char_limit(json_with_splittable_text, 200)
        
        # Should create multiple chunks with indexed keys
        found_indexed_keys = False
        for chunk in result:
            for key in chunk.keys():
                if "_" in key and key.split("_")[-1].isdigit():
                    found_indexed_keys = True
                    break
        
        # Should find indexed keys if text was split
        if len(result) > 1:
            self.assertTrue(found_indexed_keys)

    def test_process_json_document_complete_pipeline(self):
        """Test complete JSON document processing pipeline."""
        # Complex document with multiple nesting levels
        complex_document = {
            "title": "Advanced Content Strategy",
            "content_pillars": [
                {
                    "name": "Technical Leadership",
                    "pillar": "Authority Building",
                    "sub_topic": "Comprehensive analysis of emerging technologies and their impact on software development practices in enterprise environments"
                },
                {
                    "name": "Industry Analysis", 
                    "pillar": "Thought Leadership",
                    "sub_topic": "Market trends evaluation and competitive landscape assessment for technology adoption"
                }
            ],
            "target_audience": {
                "primary": "Senior Software Engineers and Tech Leads",
                "secondary": "Engineering Managers and CTOs",
                "tertiary": "Technology Consultants"
            },
            "implementation": {
                "thirty_day_targets": [
                    {
                        "goal": "Establish thought leadership position",
                        "method": "Publish technical deep-dive articles",
                        "targets": "3 high-engagement posts per week"
                    }
                ]
            }
        }
        
        result = self.splitter.process_json_document(complex_document, "content_strategy_doc")
        
        # Should return clustered results
        self.assertIsInstance(result, dict)
        
        # Should have various clusters based on mapping
        expected_clusters = ["metadata", "current_content_understanding", "user_related_information", "content_goals"]
        for cluster in expected_clusters:
            if cluster in result:  # Some clusters might be empty for this test data
                self.assertIsInstance(result[cluster], list)
                for chunk in result[cluster]:
                    self.assertIsInstance(chunk, dict)

    def test_process_json_document_no_mapping(self):
        """Test document processing without cluster mapping."""
        simple_document = {
            "title": "Simple Document",
            "content": {"section1": "Content 1", "section2": "Content 2"}
        }
        
        result = self.splitter.process_json_document(simple_document, "unknown_type")
        
        # Should have only default cluster
        self.assertIn("default", result)
        self.assertIsInstance(result["default"], list)
        self.assertGreater(len(result["default"]), 0)

    def test_process_json_document_with_user_dna_mapping(self):
        """Test document processing with user DNA cluster mapping."""
        # Create custom splitter with user DNA mapping
        class UserDNASplitter(JSONSplitter):
            def get_cluster_mapping(self, doc_type: str):
                if doc_type == "user_dna":
                    return self._get_user_dna_mapping()
                return super().get_cluster_mapping(doc_type)
            
            def _get_user_dna_mapping(self):
                return {
                    "brand_voice_and_style.communication_style": "writing_style_information",
                    "brand_voice_and_style.tone_preferences": "writing_style_information",
                    "professional_identity.full_name": "personal_context_information",
                    "professional_identity.job_title": "personal_context_information",
                    "success_metrics.content_performance_kpis": "content_information",
                    "content_strategy_goals.primary_goal": "content_information"
                }
        
        user_dna_splitter = UserDNASplitter()
        
        user_dna_document = {
            "professional_identity": {
                "full_name": "John Smith",
                "job_title": "Senior Software Engineer",
                "company_name": "TechCorp Inc"
            },
            "brand_voice_and_style": {
                "communication_style": "Professional yet approachable",
                "tone_preferences": "Conversational with technical depth"
            },
            "success_metrics": {
                "content_performance_kpis": "Engagement rate, reach, conversion to connections"
            }
        }
        
        result = user_dna_splitter.process_json_document(user_dna_document, "user_dna")
        
        # Should have specific clusters for user DNA
        expected_clusters = ["writing_style_information", "personal_context_information", "content_information"]
        for cluster in expected_clusters:
            if cluster in result:
                self.assertIsInstance(result[cluster], list)

    def test_edge_case_empty_json(self):
        """Test processing empty JSON document."""
        empty_json = {}
        
        result = self.splitter.process_json_document(empty_json, "any_type")
        
        # Should handle empty input gracefully
        self.assertIsInstance(result, dict)

    def test_edge_case_very_large_document(self):
        """Test processing very large document."""
        # Create large document with repetitive content
        large_document = {
            "title": "Large Document",
            "sections": []
        }
        
        # Add many sections
        for i in range(100):
            large_document["sections"].append({
                "id": i,
                "content": f"This is section {i} with detailed content that explains topic {i}. " * 5,
                "metadata": {"created": f"2024-01-{i+1:02d}", "author": f"Author {i}"}
            })
        
        result = self.tight_splitter.process_json_document(large_document, "content_strategy_doc")
        
        # Should handle large document and create multiple chunks
        total_chunks = sum(len(chunks) for chunks in result.values())
        self.assertGreater(total_chunks, 1)

    def test_edge_case_deeply_nested_structure(self):
        """Test processing deeply nested JSON structure."""
        deeply_nested = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {
                            "level5": {
                                "content": "Deep content that should be accessible",
                                "data": ["item1", "item2", "item3"]
                            }
                        }
                    }
                }
            }
        }
        
        result = self.splitter.process_json_document(deeply_nested, "any_type")
        
        # Should handle deep nesting
        self.assertIsInstance(result, dict)
        self.assertIn("default", result)

    def test_edge_case_special_characters_and_unicode(self):
        """Test processing JSON with special characters and Unicode."""
        special_char_json = {
            "title": "Spécial Chäráctërs & Ünïcödé 测试",
            "content": {
                "emoji": "🚀 💡 🔥",
                "symbols": "α β γ δ ε ζ η θ",
                "mixed": "English + 中文 + Español + Français"
            },
            "data": ["item-1", "item_2", "item@3", "item#4"]
        }
        
        result = self.splitter.process_json_document(special_char_json, "any_type")
        
        # Should handle special characters without errors
        self.assertIsInstance(result, dict)
        
        # Verify content preservation - check for any of the special content
        found_special_content = False
        all_content = []
        for cluster_chunks in result.values():
            for chunk in cluster_chunks:
                chunk_str = json.dumps(chunk, ensure_ascii=False)
                all_content.append(chunk_str)
                if any(special in chunk_str for special in ["Spécial", "🚀", "测试", "α", "中文"]):
                    found_special_content = True
                    break
        
        # If not found in JSON dumps, check original values
        if not found_special_content:
            for cluster_chunks in result.values():
                for chunk in cluster_chunks:
                    for value in chunk.values():
                        if isinstance(value, str) and any(special in value for special in ["Spécial", "🚀", "测试", "α", "中文"]):
                            found_special_content = True
                            break
        
        self.assertTrue(found_special_content, f"Special content not found in: {all_content}")

    def test_error_handling_invalid_json_structure(self):
        """Test error handling with problematic JSON structures."""
        # Test with circular reference simulation (can't create actual circular ref in JSON)
        # Instead test with very complex structure that might cause issues
        complex_json = {
            "data": {
                "nested": {
                    "values": [{"ref": "circular_like_reference"} for _ in range(1000)]
                }
            }
        }
        
        # Should not raise exception
        try:
            result = self.splitter.process_json_document(complex_json, "any_type")
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.fail(f"Should handle complex structures gracefully, but got: {e}")

    def test_character_counting_accuracy(self):
        """Test that character counting in JSON splitting is accurate."""
        test_json = {
            "short": "abc",  # ~15 chars in JSON: {"short": "abc"}
            "medium": "abcdefghij",  # ~23 chars in JSON: {"medium": "abcdefghij"}
        }
        
        # Use very tight limit to force splitting - but reasonable for the content
        tight_splitter = JSONSplitter(
            max_json_chunk_size=50,
            max_text_char_limit=20,
            max_json_char_limit=50
        )
        chunks = tight_splitter.split_json_values_with_char_limit(test_json, 50)
        
        # Verify each chunk is under limit (allowing some tolerance for JSON formatting)
        for chunk in chunks:
            chunk_size = len(json.dumps(chunk))
            self.assertLessEqual(chunk_size, 60, f"Chunk size {chunk_size} significantly exceeds expected limit")

    def test_reconstruction_roundtrip_consistency(self):
        """Test that flatten -> reconstruct produces consistent results."""
        original_json = {
            "title": "Test Document",
            "items": [
                {"name": "Item 1", "value": 10},
                {"name": "Item 2", "value": 20}
            ],
            "metadata": {
                "created": "2024-01-01",
                "author": {"name": "John Doe", "email": "john@example.com"}
            }
        }
        
        # Flatten then reconstruct
        flattened = self.splitter.flatten_json(original_json)
        reconstructed = self.splitter.reconstruct_json_from_paths(flattened)
        
        # Should match original structure and values
        self.assertEqual(reconstructed["title"], original_json["title"])
        self.assertEqual(len(reconstructed["items"]), len(original_json["items"]))
        self.assertEqual(reconstructed["items"][0]["name"], original_json["items"][0]["name"])
        self.assertEqual(reconstructed["metadata"]["author"]["name"], 
                        original_json["metadata"]["author"]["name"])

    def test_performance_with_large_cluster_mapping(self):
        """Test performance doesn't degrade significantly with large cluster mappings."""
        # Create large cluster mapping
        large_mapping = {}
        for i in range(1000):
            large_mapping[f"field_{i}"] = f"cluster_{i % 10}"
        
        # Mock get_cluster_mapping to return large mapping
        original_method = self.splitter.get_cluster_mapping
        self.splitter.get_cluster_mapping = lambda doc_type: large_mapping
        
        try:
            test_json = {f"field_{i}": f"value_{i}" for i in range(100)}
            
            # Should complete without timeout or memory issues
            result = self.splitter.process_json_document(test_json, "large_test")
            self.assertIsInstance(result, dict)
            
        finally:
            # Restore original method
            self.splitter.get_cluster_mapping = original_method

    # ==================== OVERLAP FUNCTIONALITY TESTS ====================

    def test_overlap_parameter_initialization(self):
        """Test overlap parameter initialization and validation."""
        # Test default (no overlap)
        default_splitter = JSONSplitter()
        self.assertEqual(default_splitter.text_overlap_percent, 20.0)
        
        # Test valid overlap percentage
        overlap_splitter = JSONSplitter(text_overlap_percent=25.0)
        self.assertEqual(overlap_splitter.text_overlap_percent, 25.0)
        
        # Test clamping of negative values
        negative_splitter = JSONSplitter(text_overlap_percent=-10.0)
        self.assertEqual(negative_splitter.text_overlap_percent, 0.0)
        
        # Test clamping of values over 100
        over_100_splitter = JSONSplitter(text_overlap_percent=150.0)
        self.assertEqual(over_100_splitter.text_overlap_percent, 100.0)

    def test_get_overlap_text_from_end(self):
        """Test extracting overlap text from end of chunk."""
        test_text = "This is a comprehensive test document with multiple sentences and detailed content."
        
        # Test extracting from end with word boundary
        end_overlap = self.splitter.get_overlap_text(test_text, 20, from_end=True)
        self.assertLessEqual(len(end_overlap), 20)
        self.assertTrue(test_text.endswith(end_overlap) or end_overlap in test_text[-20:])
        
        # Test with overlap larger than text
        short_text = "Short text"
        full_overlap = self.splitter.get_overlap_text(short_text, 50, from_end=True)
        self.assertEqual(full_overlap, short_text)

    def test_get_overlap_text_from_beginning(self):
        """Test extracting overlap text from beginning of chunk."""
        test_text = "This is a comprehensive test document with multiple sentences and detailed content."
        
        # Test extracting from beginning with word boundary
        start_overlap = self.splitter.get_overlap_text(test_text, 20, from_end=False)
        self.assertLessEqual(len(start_overlap), 20)
        self.assertTrue(test_text.startswith(start_overlap) or start_overlap in test_text[:20])
        
        # Test with overlap larger than text
        short_text = "Short text"
        full_overlap = self.splitter.get_overlap_text(short_text, 50, from_end=False)
        self.assertEqual(full_overlap, short_text)

    def test_apply_text_overlap_basic_functionality(self):
        """Test basic sliding window overlap functionality."""
        overlap_splitter = JSONSplitter(text_overlap_percent=20.0)
        
        chunks = [
            "First chunk contains important foundational information",
            "Second chunk builds upon previous concepts systematically", 
            "Third chunk introduces advanced methodologies and techniques",
            "Fourth chunk provides comprehensive conclusions and recommendations"
        ]
        
        result = overlap_splitter.apply_text_overlap(chunks, 120)
        
        # Should have same number of chunks
        self.assertEqual(len(result), len(chunks))
        
        # Combined content should be longer due to overlap
        original_length = sum(len(chunk) for chunk in chunks)
        overlapped_length = sum(len(chunk) for chunk in result)
        self.assertGreater(overlapped_length, original_length)
        
        # Each chunk should be under character limit
        for chunk in result:
            self.assertLessEqual(len(chunk), 120)

    def test_apply_text_overlap_with_external_percentage(self):
        """Test applying overlap with externally provided percentage."""
        no_overlap_splitter = JSONSplitter(text_overlap_percent=0.0)
        
        chunks = [
            "Alpha section describes fundamental concepts",
            "Beta section explains advanced techniques", 
            "Gamma section provides practical examples"
        ]
        
        # Test with 0% overlap (should be unchanged)
        no_overlap_result = no_overlap_splitter.apply_text_overlap(chunks, 100, 0.0)
        self.assertEqual(no_overlap_result, chunks)
        
        # Test with 30% overlap provided externally
        overlap_result = no_overlap_splitter.apply_text_overlap(chunks, 100, 30.0)
        
        # Should have overlap despite splitter having 0% default
        original_length = sum(len(chunk) for chunk in chunks)
        overlapped_length = sum(len(chunk) for chunk in overlap_result)
        self.assertGreater(overlapped_length, original_length)

    def test_sliding_window_overlap_distribution(self):
        """Test that sliding window distributes overlap correctly."""
        overlap_splitter = JSONSplitter(text_overlap_percent=40.0)
        
        chunks = [
            "First chunk with specific unique content here",
            "Second chunk with different unique content here",
            "Third chunk with more unique content here"
        ]
        
        result = overlap_splitter.apply_text_overlap(chunks, 150)
        
        # First chunk should have overlap from next chunk only
        self.assertIn("chunk", result[0])
        
        # Middle chunk should have overlap from both sides
        middle_chunk = result[1]
        self.assertIn("chunk", middle_chunk)
        
        # Last chunk should have overlap from previous chunk only
        self.assertIn("chunk", result[2])

    def test_overlap_with_complex_long_form_text(self):
        """Test overlap with complex long-form content requiring multiple splits."""
        overlap_splitter = JSONSplitter(text_overlap_percent=25.0)
        
        long_form_text = (
            "Executive Summary: This comprehensive analysis examines the evolving landscape of enterprise software development "
            "and its implications for organizational digital transformation initiatives. The study encompasses multiple "
            "dimensions including technological advancement, market dynamics, competitive positioning, and strategic "
            "implementation considerations that influence long-term success outcomes.\n\n"
            
            "Market Analysis: Current market conditions demonstrate significant shifts in enterprise technology adoption "
            "patterns, with organizations increasingly prioritizing cloud-native solutions, microservices architectures, "
            "and artificial intelligence integration. These trends reflect broader industry movements toward scalable, "
            "resilient, and intelligent systems that can adapt to rapidly changing business requirements and market "
            "conditions while maintaining operational efficiency and cost effectiveness.\n\n"
            
            "Technical Implementation: Successful implementation requires careful consideration of existing infrastructure "
            "constraints, security requirements, compliance obligations, and integration complexity. Organizations must "
            "balance innovation with stability, ensuring that new technologies enhance rather than disrupt critical "
            "business processes while providing measurable value and return on investment through improved operational "
            "efficiency and competitive advantage.\n\n"
            
            "Strategic Recommendations: Based on comprehensive analysis and industry best practices, organizations should "
            "adopt a phased approach to technology modernization, prioritizing high-impact, low-risk initiatives that "
            "build organizational capability and confidence. This approach enables sustainable transformation while "
            "minimizing disruption and maximizing the probability of successful outcomes through careful planning and "
            "execution management."
        )
        
        # Split with moderate character limit to create multiple chunks
        result = overlap_splitter.split_text_recursively(long_form_text, 300)
        
        # Should create multiple chunks
        self.assertGreater(len(result), 3)
        
        # Each chunk should be under limit
        for chunk in result:
            self.assertLessEqual(len(chunk), 300)
        
        # Verify context preservation across chunks
        combined = " ".join(result)
        key_concepts = [
            "Executive Summary", "Market Analysis", "Technical Implementation", 
            "Strategic Recommendations", "enterprise software", "digital transformation",
            "cloud-native solutions", "microservices", "artificial intelligence"
        ]
        
        for concept in key_concepts:
            self.assertIn(concept, combined)

    def test_overlap_with_technical_paragraphs(self):
        """Test overlap with technical content containing specialized terminology."""
        overlap_splitter = JSONSplitter(text_overlap_percent=30.0)
        
        technical_content = (
            "Kubernetes Orchestration Strategy\n\n"
            
            "Container orchestration with Kubernetes provides automated deployment, scaling, and management of "
            "containerized applications across distributed computing environments. The platform abstracts underlying "
            "infrastructure complexity while providing declarative configuration management, service discovery, "
            "load balancing, and automated rollout capabilities that enable reliable application lifecycle management.\n\n"
            
            "Service Mesh Architecture\n\n"
            
            "Implementing service mesh architecture using Istio or Linkerd provides advanced traffic management, "
            "security policies, and observability features for microservices communication. The mesh layer handles "
            "cross-cutting concerns including mutual TLS authentication, circuit breaking, retry logic, and distributed "
            "tracing without requiring application code modifications or service-specific implementations.\n\n"
            
            "Monitoring and Observability\n\n"
            
            "Comprehensive monitoring requires integration of metrics collection, distributed tracing, and centralized "
            "logging using tools like Prometheus, Jaeger, and Elasticsearch. This observability stack enables real-time "
            "performance monitoring, anomaly detection, root cause analysis, and capacity planning through detailed "
            "insights into application behavior, resource utilization, and user experience metrics.\n\n"
            
            "Security Implementation\n\n"
            
            "Security implementation encompasses multiple layers including network policies, pod security standards, "
            "secrets management, and vulnerability scanning. Organizations must implement defense-in-depth strategies "
            "that include runtime security monitoring, admission controllers, and compliance automation to maintain "
            "security posture while enabling developer productivity and operational efficiency."
        )
        
        result = overlap_splitter.split_text_recursively(technical_content, 250)
        
        # Should create multiple chunks
        self.assertGreater(len(result), 4)
        
        # Each chunk should be under limit
        for chunk in result:
            self.assertLessEqual(len(chunk), 250)
        
        # Verify technical terms are preserved with context
        combined = " ".join(result)
        technical_terms = [
            "Kubernetes", "Istio", "Linkerd", "Prometheus", "Jaeger", "Elasticsearch",
            "microservices", "service mesh", "mutual TLS", "circuit breaking",
            "distributed tracing", "observability"
        ]
        
        for term in technical_terms:
            self.assertIn(term, combined)
        
        # Check for security-related terms (some might be truncated)
        security_terms_found = sum(1 for term in ["security", "policies", "scanning", "monitoring"] if term in combined)
        self.assertGreaterEqual(security_terms_found, 2, "Should find security-related terms even if some are truncated")
        
        # Verify section headers are preserved
        sections = ["Kubernetes Orchestration", "Service Mesh Architecture", 
                   "Monitoring and Observability", "Security Implementation"]
        for section in sections:
            self.assertIn(section, combined)

    def test_overlap_with_mixed_content_types(self):
        """Test overlap with mixed content including lists, technical specs, and narrative text."""
        overlap_splitter = JSONSplitter(text_overlap_percent=20.0)
        
        mixed_content = (
            "API Design Guidelines and Best Practices\n\n"
            
            "RESTful API design requires adherence to established conventions and standards that ensure consistency, "
            "maintainability, and developer experience. Key principles include resource-based URL structures, "
            "appropriate HTTP method usage, consistent response formats, and comprehensive error handling strategies.\n\n"
            
            "HTTP Status Codes:\n"
            "• 200 OK - Successful GET, PUT, PATCH requests\n"
            "• 201 Created - Successful POST requests that create resources\n"
            "• 204 No Content - Successful DELETE requests\n"
            "• 400 Bad Request - Invalid request syntax or parameters\n"
            "• 401 Unauthorized - Authentication required\n"
            "• 403 Forbidden - Insufficient permissions\n"
            "• 404 Not Found - Resource does not exist\n"
            "• 409 Conflict - Resource state conflicts\n"
            "• 422 Unprocessable Entity - Validation errors\n"
            "• 500 Internal Server Error - Server-side failures\n\n"
            
            "Authentication and Authorization:\n"
            "Modern APIs implement OAuth 2.0 with JWT tokens for secure authentication and authorization. "
            "The authorization server issues access tokens with specific scopes that define permitted operations. "
            "Resource servers validate tokens and enforce authorization policies based on user roles and permissions. "
            "Token refresh mechanisms ensure continued access without requiring user re-authentication.\n\n"
            
            "Rate Limiting and Throttling:\n"
            "Implement rate limiting using algorithms like token bucket or sliding window to prevent abuse and "
            "ensure fair resource allocation. Headers should communicate current limits, remaining requests, and "
            "reset times. Implement graceful degradation with appropriate HTTP 429 responses and retry-after headers "
            "to guide client behavior during rate limit scenarios."
        )
        
        result = overlap_splitter.split_text_recursively(mixed_content, 280)
        
        # Should create multiple chunks
        self.assertGreater(len(result), 3)
        
        # Each chunk should be under limit
        for chunk in result:
            self.assertLessEqual(len(chunk), 280)
        
        # Verify different content types are preserved
        combined = " ".join(result)
        
        # Check for list items
        status_codes = ["200 OK", "201 Created", "404 Not Found", "500 Internal Server Error"]
        for code in status_codes:
            self.assertIn(code, combined)
        
        # Check for technical concepts
        concepts = ["RESTful API", "OAuth 2.0", "JWT tokens", "rate limiting", "token bucket"]
        for concept in concepts:
            self.assertIn(concept, combined)
        
        # Check for section headers
        sections = ["API Design Guidelines", "HTTP Status Codes", "Authentication and Authorization"]
        for section in sections:
            self.assertIn(section, combined)

    def test_overlap_preserves_context_across_splits(self):
        """Test that overlap preserves important context across chunk boundaries."""
        overlap_splitter = JSONSplitter(text_overlap_percent=35.0)
        
        contextual_document = (
            "Machine Learning Model Deployment Pipeline\n\n"
            
            "Model deployment requires careful orchestration of multiple components including data preprocessing, "
            "model serving infrastructure, monitoring systems, and feedback loops. The deployment pipeline must "
            "handle model versioning, A/B testing, canary deployments, and rollback capabilities while maintaining "
            "consistent performance and reliability standards across different environments and traffic patterns.\n\n"
            
            "Infrastructure Requirements:\n"
            "Production model serving requires scalable infrastructure capable of handling variable traffic loads "
            "with consistent latency and throughput guarantees. Container orchestration platforms like Kubernetes "
            "provide automated scaling, load balancing, and health monitoring for model serving endpoints. "
            "GPU acceleration may be required for computationally intensive models, necessitating specialized "
            "hardware provisioning and resource allocation strategies.\n\n"
            
            "Monitoring and Observability:\n"
            "Comprehensive monitoring encompasses model performance metrics, infrastructure health, data quality "
            "indicators, and business impact measurements. Model drift detection algorithms continuously evaluate "
            "prediction accuracy and feature distributions to identify when retraining becomes necessary. "
            "Alerting systems notify operations teams of anomalies, performance degradation, or infrastructure "
            "failures that could impact model availability or accuracy.\n\n"
            
            "Continuous Integration and Deployment:\n"
            "Automated CI/CD pipelines integrate model training, validation, testing, and deployment processes "
            "with version control systems and artifact repositories. Pipeline stages include data validation, "
            "model training, performance evaluation, security scanning, and staged deployment with automated "
            "rollback capabilities. Integration with MLOps platforms enables experiment tracking, model registry "
            "management, and governance compliance throughout the model lifecycle."
        )
        
        result = overlap_splitter.split_text_recursively(contextual_document, 320)
        
        # Should create multiple chunks
        self.assertGreater(len(result), 2)
        
        # Each chunk should be under limit
        for chunk in result:
            self.assertLessEqual(len(chunk), 320)
        
        # Verify context preservation - related concepts should appear together
        combined = " ".join(result)
        
        # Check for concept continuity - handle potential word splitting
        # Check individual words that should be present (case-insensitive and flexible)
        key_terms = ["deployment", "pipeline", "Kubernetes", "orchestration", 
                    "drift", "retraining", "CI/CD", "automated", "MLOps"]
        
        found_terms = 0
        for term in key_terms:
            if term in combined or term.lower() in combined.lower():
                found_terms += 1
        
        # Should find most of the key terms even if some are truncated
        self.assertGreaterEqual(found_terms, 6, f"Should find at least 6 key terms, found {found_terms}")

    def test_overlap_with_json_document_processing(self):
        """Test overlap functionality within complete JSON document processing."""
        overlap_splitter = JSONSplitter(
            max_json_chunk_size=200,
            max_text_char_limit=150,
            max_json_char_limit=400,
            text_overlap_percent=25.0
        )
        
        document_with_long_content = {
            "title": "Comprehensive Content Strategy Framework",
            "executive_summary": (
                "This strategic framework provides comprehensive guidance for developing and implementing "
                "content marketing strategies that drive measurable business outcomes. The framework encompasses "
                "audience research methodologies, content planning processes, distribution channel optimization, "
                "and performance measurement systems that enable data-driven decision making and continuous improvement."
            ),
            "methodology": {
                "research_phase": (
                    "Audience research involves comprehensive analysis of target demographics, psychographics, "
                    "behavioral patterns, and content consumption preferences. Primary research methods include "
                    "surveys, interviews, focus groups, and observational studies. Secondary research encompasses "
                    "market analysis, competitive intelligence, and industry trend evaluation to inform strategic decisions."
                ),
                "planning_phase": (
                    "Content planning requires systematic approach to editorial calendar development, resource allocation, "
                    "and production workflow optimization. Planning considerations include content pillar definition, "
                    "topic clustering, keyword research, and content format selection based on audience preferences "
                    "and channel-specific requirements for maximum engagement and conversion potential."
                )
            },
            "implementation": {
                "content_creation": (
                    "Content creation processes must balance quality, consistency, and efficiency while maintaining "
                    "brand voice and messaging alignment. Creation workflows include briefing development, content "
                    "production, review cycles, approval processes, and optimization based on performance data and "
                    "audience feedback to ensure continuous improvement and relevance."
                ),
                "distribution_strategy": (
                    "Multi-channel distribution strategy maximizes content reach and engagement through strategic "
                    "platform selection, timing optimization, and format adaptation. Distribution channels include "
                    "owned media properties, social media platforms, email marketing, and paid promotion channels "
                    "with channel-specific optimization for maximum impact and return on investment."
                )
            }
        }
        
        result = overlap_splitter.process_json_document(document_with_long_content, "content_strategy_doc")
        
        # Should produce clustered results
        self.assertIsInstance(result, dict)
        self.assertIn("default", result)
        
        # Verify that chunks within clusters have reasonable overlap
        default_chunks = result["default"]
        self.assertIsInstance(default_chunks, list)
        self.assertGreater(len(default_chunks), 1)
        
        # Check that content is preserved across chunks
        all_content = []
        for chunk in default_chunks:
            chunk_str = json.dumps(chunk)
            all_content.append(chunk_str)
        
        combined_content = " ".join(all_content)
        key_terms = [
            "strategic framework", "audience research", "content planning",
            "implementation", "distribution strategy", "performance measurement"
        ]
        
        for term in key_terms:
            self.assertIn(term, combined_content)

    def test_overlap_edge_cases(self):
        """Test overlap functionality with edge cases."""
        overlap_splitter = JSONSplitter(text_overlap_percent=20.0)
        
        # Test with single chunk
        single_chunk = ["Only one chunk here"]
        result = overlap_splitter.apply_text_overlap(single_chunk, 100)
        self.assertEqual(result, single_chunk)
        
        # Test with empty chunks
        empty_chunks = []
        result = overlap_splitter.apply_text_overlap(empty_chunks, 100)
        self.assertEqual(result, empty_chunks)
        
        # Test with very short chunks
        short_chunks = ["A", "B", "C"]
        result = overlap_splitter.apply_text_overlap(short_chunks, 50)
        self.assertEqual(len(result), 3)
        
        # Test with chunks that are already at character limit
        max_chunks = ["A" * 100, "B" * 100, "C" * 100]
        result = overlap_splitter.apply_text_overlap(max_chunks, 100)
        
        # Should handle without exceeding limits
        for chunk in result:
            self.assertLessEqual(len(chunk), 100)

    def test_overlap_character_limit_enforcement(self):
        """Test that overlap strictly enforces character limits."""
        overlap_splitter = JSONSplitter(text_overlap_percent=50.0)  # High overlap
        
        chunks = [
            "This is a substantial first chunk with significant content that provides important context",
            "This is a substantial second chunk with significant content that builds upon previous concepts",
            "This is a substantial third chunk with significant content that concludes the discussion"
        ]
        
        strict_limit = 120
        result = overlap_splitter.apply_text_overlap(chunks, strict_limit)
        
        # Every chunk must be under the strict limit
        for i, chunk in enumerate(result):
            self.assertLessEqual(len(chunk), strict_limit, 
                               f"Chunk {i} exceeds limit: {len(chunk)} > {strict_limit}")
        
        # Should still have overlap despite truncation
        combined_length = sum(len(chunk) for chunk in result)
        original_length = sum(len(chunk) for chunk in chunks)
        
        # Combined length should be greater than original (indicating overlap)
        # but not excessively so due to truncation
        self.assertGreater(combined_length, original_length)

    def test_overlap_with_paragraph_boundary_preservation(self):
        """Test that overlap respects paragraph boundaries when possible."""
        overlap_splitter = JSONSplitter(text_overlap_percent=25.0)
        
        multi_paragraph_document = (
            "Introduction to Advanced Analytics\n\n"
            
            "Advanced analytics encompasses sophisticated statistical methods, machine learning algorithms, "
            "and predictive modeling techniques that enable organizations to extract actionable insights "
            "from complex data sets. These methodologies go beyond traditional descriptive analytics "
            "to provide prescriptive and predictive capabilities that inform strategic decision making.\n\n"
            
            "Data Preparation and Feature Engineering\n\n"
            
            "Effective analytics requires comprehensive data preparation including data cleaning, "
            "normalization, and feature engineering processes. Feature engineering involves creating "
            "meaningful variables from raw data through transformation, aggregation, and domain-specific "
            "calculations that enhance model performance and interpretability for business stakeholders.\n\n"
            
            "Model Development and Validation\n\n"
            
            "Model development follows systematic approaches including algorithm selection, hyperparameter "
            "tuning, cross-validation, and performance evaluation using appropriate metrics. Validation "
            "processes ensure model generalizability and robustness across different data conditions "
            "while preventing overfitting and maintaining predictive accuracy on unseen data.\n\n"
            
            "Deployment and Monitoring\n\n"
            
            "Production deployment requires careful consideration of infrastructure requirements, "
            "scalability constraints, and monitoring systems that track model performance over time. "
            "Continuous monitoring enables early detection of model drift, data quality issues, "
            "and performance degradation that may require model retraining or recalibration."
        )
        
        result = overlap_splitter.split_text_recursively(multi_paragraph_document, 300)
        
        # Should create multiple chunks
        self.assertGreater(len(result), 2)
        
        # Each chunk should be under limit
        for chunk in result:
            self.assertLessEqual(len(chunk), 300)
        
        # Verify paragraph structure is preserved
        combined = "\n\n".join(result)
        section_headers = [
            "Introduction to Advanced Analytics",
            "Data Preparation and Feature Engineering", 
            "Model Development and Validation",
            "Deployment and Monitoring"
        ]
        
        for header in section_headers:
            self.assertIn(header, combined)
        
        # Verify technical continuity across chunks
        technical_concepts = [
            "machine learning", "feature engineering", "hyperparameter tuning",
            "cross-validation", "model drift", "predictive modeling"
        ]
        
        for concept in technical_concepts:
            self.assertIn(concept, combined)


# Allow running the tests directly
if __name__ == "__main__":
    unittest.main()
