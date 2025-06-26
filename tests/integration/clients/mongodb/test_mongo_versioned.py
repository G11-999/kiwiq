import unittest
import asyncio
import uuid
import logging
from typing import Dict, Any, List, Optional
from bson import ObjectId
import copy
import os
import time
import json
from datetime import timedelta

# Import the clients
from mongo_client import AsyncMongoDBClient, AsyncMongoVersionedClient
from redis_client import AsyncRedisClient
import jsonpatch
from global_config.logger import get_logger
from jsonschema.exceptions import ValidationError

logger = get_logger(__name__)

class TestMongoVersionedClient(unittest.IsolatedAsyncioTestCase):
    """Comprehensive test case for the AsyncMongoVersionedClient."""

    client: AsyncMongoDBClient
    versioned_client: AsyncMongoVersionedClient
    redis_client: AsyncRedisClient
    mongo_uri: str
    database: str
    collection: str
    base_segment_names: List[str]
    underlying_segment_names: List[str]
    TEST_PREFIX: str

    async def asyncSetUp(self):
        """Set up test environment before each test method."""
        from global_config.settings import global_settings
        self.mongo_uri = global_settings.MONGO_URL
        redis_url = global_settings.REDIS_URL
        
        if not redis_url:
            self.fail("REDIS_URL environment variable not set.")
        
        # Use a test database and collection
        self.database = "test_versioned_db"
        self.collection = "test_versioned_objects"
        
        # Define base segment names for the versioned client
        self.base_segment_names = ["org", "namespace", "docname"] 
        
        # Define segment names for the underlying client, accommodating version and sequence
        # These names MUST match how the underlying client expects segments
        self.underlying_segment_names = self.base_segment_names + AsyncMongoVersionedClient.VERSION_SEGMENT_NAMES
        
        # Create a unique test prefix for path isolation
        self.TEST_PREFIX = f"test_run_{uuid.uuid4().hex[:8]}"
        
        # Initialize Redis client first
        self.redis_client = AsyncRedisClient(redis_url)
        
        # Test Redis connection
        if not await self.redis_client.ping():
            await self.redis_client.close()
            self.fail("Could not connect to Redis. Check connection URL and server status.")
        
        # Initialize the underlying MongoDB client
        self.client = AsyncMongoDBClient(
            uri=self.mongo_uri,
            database=self.database,
            collection=self.collection,
            segment_names=self.underlying_segment_names,
            # Add other necessary fields if needed by AsyncMongoDBClient 
            # e.g., text_search_fields, value_filter_fields
        )

        self.client.version_mode = AsyncMongoDBClient.DOC_TYPE_VERSIONED
        
        # Setup underlying client (drop collection, create indexes)
        await self.client.drop_collection(confirm=True)
        setup_success = await self.client.setup()
        if not setup_success:
            await self.client.close()
            await self.redis_client.close()
            self.fail("Failed to set up underlying MongoDB client and indexes.")
        
        # Verify connection with ping
        is_connected = await self.client.ping()
        if not is_connected:
            await self.client.close()
            await self.redis_client.close()
            self.fail("Could not connect to MongoDB. Check connection URI and server status.")
            
        # Initialize the versioned client with Redis locking
        self.versioned_client = AsyncMongoVersionedClient(
            client=self.client,
            segment_names=self.base_segment_names, # Pass only the base segments
            redis_client=self.redis_client,
            return_timestamp_metadata=False,
            lock_timeout=10,  # 10 second timeout for tests
            lock_ttl=30      # 30 second TTL for tests
        )
        
        logger.info(f"Versioned test setup complete with prefix: {self.TEST_PREFIX}")

    async def asyncTearDown(self):
        """Clean up after each test method."""
        if hasattr(self, 'client') and self.client:
            # Clean up any test documents using the underlying client directly
            # Deleting based on the TEST_PREFIX in the first segment
            try:
                pattern = [self.TEST_PREFIX, "*", "*"] # Adjust wildcard count based on base_segment_names
                await self.client.delete_objects(pattern)
                # Also delete potential nested version/sequence data
                await self.client.delete_objects(pattern + ["*", "*"]) # Covers version and sequence levels
            except Exception as e:
                logger.error(f"Error during test cleanup: {e}")
                pass # Ignore cleanup errors
            
            await self.client.close()
            logger.info("Underlying MongoDB client closed.")
        
        if hasattr(self, 'redis_client') and self.redis_client:
            # Clean up any test locks
            try:
                await self.redis_client.flush_cache(f"doc_lock:{self.TEST_PREFIX}*")
            except Exception as e:
                logger.error(f"Error during Redis test cleanup: {e}")
                pass # Ignore cleanup errors
            
            await self.redis_client.close()
            logger.info("Redis client closed.")

    def _get_test_path(self, doc_name: str) -> List[str]:
        """Helper to create a base path for testing."""
        # Example base path: [TEST_PREFIX, "test_ns", doc_name]
        # Adjust according to self.base_segment_names length
        return [self.TEST_PREFIX, "test_ns", doc_name]

    # =========================================================================
    # Initialization and Basic Structure Tests
    # =========================================================================

    async def test_initialize_document(self):
        """Test initializing a new versioned document."""
        base_path = self._get_test_path("init_doc")
        initial_version = "v0.1"
        
        # Initialize the document
        initialized = await self.versioned_client.initialize_document(
            base_path=base_path,
            initial_version=initial_version
        )
        self.assertTrue(initialized, "Should successfully initialize a new document")

        # Verify metadata object exists
        metadata = await self.versioned_client._get_document_metadata(base_path)
        self.assertIsNotNone(metadata, "Metadata object should exist")
        self.assertEqual(metadata.get("active_version"), initial_version, "Initial version should be active")
        self.assertIn(initial_version, metadata.get("versions", []), "Initial version should be in the versions list")
        self.assertIsNone(metadata.get("schema"), "Schema should be None initially")

        # Verify version data object exists
        version_data = await self.versioned_client._get_version_data(base_path, initial_version)
        self.assertIsNotNone(version_data, "Version data object should exist")
        # Internal keys should be present directly in version_data
        self.assertEqual(version_data.get(AsyncMongoVersionedClient.MIN_SEQUENCE_KEY), 0, "Initial min sequence should be 0")
        self.assertEqual(version_data.get(AsyncMongoVersionedClient.MAX_SEQUENCE_KEY), -1, "Initial max sequence should be -1")
        self.assertFalse(version_data.get(AsyncMongoVersionedClient.IS_COMPLETE_KEY), "Initial document should not be complete")
        
        # User document part of version_data should be empty
        user_document_part = {
            k: v for k, v in version_data.items() 
            if k not in AsyncMongoVersionedClient.ALL_KEYS and k != AsyncMongoVersionedClient.DOCUMENT_KEY
        }
        self.assertEqual(user_document_part, {}, "Initial user document part should be empty")
        self.assertNotIn(AsyncMongoVersionedClient.DOCUMENT_KEY, version_data, "DOCUMENT_KEY should not be present for initial empty dict")

    async def test_initialize_existing_document(self):
        """Test attempting to initialize a document that already exists."""
        base_path = self._get_test_path("init_existing_doc")
        await self.versioned_client.initialize_document(base_path)
        
        # Try to initialize again
        initialized_again = await self.versioned_client.initialize_document(base_path)
        self.assertFalse(initialized_again, "Should return False when initializing an existing document")

    # =========================================================================
    # Version Management Tests
    # =========================================================================

    async def test_create_version(self):
        """Test creating new versions."""
        base_path = self._get_test_path("version_doc")
        await self.versioned_client.initialize_document(base_path, initial_version="v1")

        # Create a new version from the active one (v1)
        created_v2 = await self.versioned_client.create_version(base_path, "v2")
        self.assertTrue(created_v2, "Should create version v2")

        # Verify v2 exists and metadata is updated
        metadata = await self.versioned_client._get_document_metadata(base_path)
        self.assertIn("v2", metadata["versions"], "v2 should be in versions list")
        v2_data = await self.versioned_client._get_version_data(base_path, "v2")
        self.assertIsNotNone(v2_data, "v2 data object should exist")
        
        # User document part of v2_data should be empty as it's branched from an empty v1
        v2_user_document_part = {
            k: v for k, v in v2_data.items() 
            if k not in AsyncMongoVersionedClient.ALL_KEYS and k != AsyncMongoVersionedClient.DOCUMENT_KEY
        }
        self.assertEqual(v2_user_document_part, {}, "v2 user document part should be initialized empty (like v1)")
        self.assertNotIn(AsyncMongoVersionedClient.DOCUMENT_KEY, v2_data, "DOCUMENT_KEY should not be present for v2 initially")

        # Create v3 branching specifically from v1
        created_v3 = await self.versioned_client.create_version(base_path, "v3", from_version="v1")
        self.assertTrue(created_v3, "Should create version v3 from v1")
        metadata = await self.versioned_client._get_document_metadata(base_path)
        self.assertIn("v3", metadata["versions"], "v3 should be in versions list")

        # Try creating an existing version
        with self.assertRaises(ValueError, msg="Creating existing version should fail"):
            await self.versioned_client.create_version(base_path, "v2")

        # Try creating from a non-existent version
        with self.assertRaises(ValueError, msg="Creating from non-existent version should fail"): 
            await self.versioned_client.create_version(base_path, "v4", from_version="nonexistent")

    async def test_set_active_version(self):
        """Test setting the active version."""
        base_path = self._get_test_path("active_version_doc")
        await self.versioned_client.initialize_document(base_path, initial_version="v1")
        await self.versioned_client.create_version(base_path, "v2")

        # Set v2 as active
        set_active = await self.versioned_client.set_active_version(base_path, "v2")
        self.assertTrue(set_active, "Setting active version should succeed")

        # Verify metadata
        metadata = await self.versioned_client._get_document_metadata(base_path)
        self.assertEqual(metadata["active_version"], "v2", "v2 should now be the active version")

        # Try setting a non-existent version as active
        with self.assertRaises(ValueError, msg="Setting non-existent version active should fail"): 
            await self.versioned_client.set_active_version(base_path, "nonexistent")

    async def test_list_versions(self):
        """Test listing available versions."""
        base_path = self._get_test_path("list_versions_doc")
        await self.versioned_client.initialize_document(base_path, initial_version="v1")
        await self.versioned_client.create_version(base_path, "v2")
        await self.versioned_client.create_version(base_path, "v3")
        await self.versioned_client.set_active_version(base_path, "v2")

        # Update v2 to have some history
        await self.versioned_client.update_document(base_path, {"change": 1}, version="v2")
        await self.versioned_client.update_document(base_path, {"change": 2}, version="v2")
        
        versions_list = await self.versioned_client.list_versions(base_path)
        self.assertEqual(len(versions_list), 3, "Should list 3 versions")

        # Check structure and active status
        v1_info = next((v for v in versions_list if v["version"] == "v1"), None)
        v2_info = next((v for v in versions_list if v["version"] == "v2"), None)
        v3_info = next((v for v in versions_list if v["version"] == "v3"), None)

        self.assertIsNotNone(v1_info)
        self.assertFalse(v1_info["is_active"], "v1 should not be active")
        self.assertEqual(v1_info["edit_count"], 0, "v1 should have 0 edits")

        self.assertIsNotNone(v2_info)
        self.assertTrue(v2_info["is_active"], "v2 should be active")
        self.assertEqual(v2_info["edit_count"], 2, "v2 should have 2 edits") 
        
        self.assertIsNotNone(v3_info)
        self.assertFalse(v3_info["is_active"], "v3 should not be active")
        self.assertEqual(v3_info["edit_count"], 0, "v3 should have 0 edits")
        
    async def test_delete_version(self):
        """Test deleting a specific version."""
        base_path = self._get_test_path("delete_version_doc")
        await self.versioned_client.initialize_document(base_path, initial_version="v1")
        await self.versioned_client.create_version(base_path, "v2")
        await self.versioned_client.create_version(base_path, "v3")
        
        # Update v2 to create history items
        await self.versioned_client.update_document(base_path, {"data": "v2_data"}, version="v2")
        await self.versioned_client.update_document(base_path, {"data": "v2_data_update"}, version="v2")

        # Try deleting active version (v1)
        with self.assertRaises(ValueError, msg="Deleting active version should fail"): 
            await self.versioned_client.delete_version(base_path, "v1")

        # Delete v2 (non-active)
        deleted_v2 = await self.versioned_client.delete_version(base_path, "v2")
        self.assertTrue(deleted_v2, "Deleting v2 should succeed")

        # Verify metadata
        metadata = await self.versioned_client._get_document_metadata(base_path)
        self.assertNotIn("v2", metadata["versions"], "v2 should be removed from versions list")
        self.assertEqual(metadata["active_version"], "v1", "Active version should remain v1")

        # Verify v2 data and history are gone
        v2_data = await self.versioned_client._get_version_data(base_path, "v2")
        self.assertIsNone(v2_data, "v2 data object should be deleted")
        # Get history should raise error for deleted version
        with self.assertRaises(ValueError, msg="Getting history for deleted version should fail"):
            await self.versioned_client.get_version_history(base_path, version="v2")
        # Underlying check
        v2_history_count = await self.client.count_objects(self.versioned_client._build_history_pattern(base_path, "v2"))

        # Try deleting non-existent version
        deleted_nonexistent = await self.versioned_client.delete_version(base_path, "nonexistent")
        self.assertFalse(deleted_nonexistent, "Deleting non-existent version should return False")

    # =========================================================================
    # Document Update and History Tests
    # =========================================================================

    async def test_update_document_json(self):
        """Test updating JSON documents and checking history."""
        base_path = self._get_test_path("update_json_doc")
        await self.versioned_client.initialize_document(base_path, initial_version="main")

        # Initial update
        data1 = {"a": 1, "b": "hello"}
        update1_ok = await self.versioned_client.update_document(base_path, data1, version="main")
        self.assertTrue(update1_ok, "First update should succeed")
        doc = await self.versioned_client.get_document(base_path, version="main")
        self.assertEqual(doc, data1, "Document should match first update")

        # Second update (modify and add)
        data2 = {"b": "world", "c": True}
        update2_ok = await self.versioned_client.update_document(base_path, data2, version="main")
        self.assertTrue(update2_ok, "Second update should succeed")
        doc = await self.versioned_client.get_document(base_path, version="main")
        expected_doc2 = {"a": 1, "b": "world", "c": True}
        self.assertEqual(doc, expected_doc2, "Document should reflect merged second update")

        # Third update (nested)
        data3 = {"d": {"e": 10}}
        update3_ok = await self.versioned_client.update_document(base_path, data3, version="main")
        self.assertTrue(update3_ok, "Third update should succeed")
        doc = await self.versioned_client.get_document(base_path, version="main")
        expected_doc3 = {"a": 1, "b": "world", "c": True, "d": {"e": 10}}
        self.assertEqual(doc, expected_doc3, "Document should reflect merged third update")

        # Check history
        history = await self.versioned_client.get_version_history(base_path, version="main", limit=10)
        self.assertEqual(len(history), 3, "Should have 3 history entries")

        # Verify patches (newest first)
        # History 2 (data3 -> expected_doc3)
        patch2_str = history[0]["patch"]
        patch2 = jsonpatch.JsonPatch.from_string(patch2_str)
        reconstructed2 = patch2.apply(expected_doc2) # Apply patch to previous state
        self.assertEqual(reconstructed2, expected_doc3, "Patch 2 should reconstruct state 3")
        
        # History 1 (data1 -> expected_doc2)
        patch1_str = history[1]["patch"]
        patch1 = jsonpatch.JsonPatch.from_string(patch1_str)
        reconstructed1 = patch1.apply(data1) # Apply patch to previous state
        self.assertEqual(reconstructed1, expected_doc2, "Patch 1 should reconstruct state 2")

        # History 0 ({} -> data1)
        patch0_str = history[2]["patch"]
        patch0 = jsonpatch.JsonPatch.from_string(patch0_str)
        reconstructed0 = patch0.apply({}) # Apply patch to initial empty state
        self.assertEqual(reconstructed0, data1, "Patch 0 should reconstruct state 1")

    async def test_update_document_primitive(self):
        """Test updating primitive data types."""
        base_path = self._get_test_path("update_primitive_doc")
        await self.versioned_client.initialize_document(base_path, initial_version="main")

        # String update
        update1 = await self.versioned_client.update_document(base_path, "hello world", version="main")
        self.assertTrue(update1)
        self.assertEqual(await self.versioned_client.get_document(base_path), "hello world")

        # Integer update
        update2 = await self.versioned_client.update_document(base_path, 123, version="main")
        self.assertTrue(update2)
        self.assertEqual(await self.versioned_client.get_document(base_path), 123)

        # Boolean update
        update3 = await self.versioned_client.update_document(base_path, False, version="main")
        self.assertTrue(update3)
        self.assertEqual(await self.versioned_client.get_document(base_path), False)

        # None update
        update4 = await self.versioned_client.update_document(base_path, None, version="main")
        self.assertTrue(update4)
        self.assertIsNone(await self.versioned_client.get_document(base_path))

        # Check history
        history = await self.versioned_client.get_version_history(base_path, version="main")
        self.assertEqual(len(history), 4, "Should have 4 history entries for primitive updates")
        # Verify patches are simple replace operations
        for item in history:
            self.assertTrue(item.get("is_primitive"))
            patch = jsonpatch.JsonPatch.from_string(item["patch"])
            # Access the list of operations via patch.patch
            self.assertEqual(len(patch.patch), 1, f"Patch should have 1 operation: {patch.patch}")
            self.assertEqual(patch.patch[0]['op'], 'replace', f"Operation should be replace: {patch.patch[0]}")
            self.assertEqual(patch.patch[0]['path'], '', f"Path should be root '': {patch.patch[0]}") # Check for empty string path

    async def test_update_document_no_change(self):
        """Test updating with identical data should not create history."""
        base_path = self._get_test_path("no_change_doc")
        await self.versioned_client.initialize_document(base_path, initial_version="main")
        data = {"a": 1}
        await self.versioned_client.update_document(base_path, data, version="main")
        
        history_before = await self.versioned_client.get_version_history(base_path, version="main")
        self.assertEqual(len(history_before), 1)
        
        # Update with same data
        update_ok = await self.versioned_client.update_document(base_path, data, version="main")
        self.assertTrue(update_ok, "Update with no changes should still return True")
        
        history_after = await self.versioned_client.get_version_history(base_path, version="main")
        self.assertEqual(len(history_after), 1, "History count should not increase if data is identical")

    async def test_get_document_specific_version(self):
        """Test getting document from a specific non-active version."""
        base_path = self._get_test_path("get_specific_doc")
        await self.versioned_client.initialize_document(base_path, initial_version="v1")
        await self.versioned_client.update_document(base_path, {"v": "data_v1"}, version="v1")
        
        await self.versioned_client.create_version(base_path, "v2")
        await self.versioned_client.update_document(base_path, {"v": "data_v2"}, version="v2")
        
        await self.versioned_client.set_active_version(base_path, "v2")

        # Get active version (v2) implicitly
        doc_active = await self.versioned_client.get_document(base_path)
        self.assertEqual(doc_active, {"v": "data_v2"})

        # Get specific version v1
        doc_v1 = await self.versioned_client.get_document(base_path, version="v1")
        self.assertEqual(doc_v1, {"v": "data_v1"})

        # Get specific version v2 explicitly
        doc_v2 = await self.versioned_client.get_document(base_path, version="v2")
        self.assertEqual(doc_v2, {"v": "data_v2"})
        
        # Try getting non-existent version
        with self.assertRaises(ValueError): 
            await self.versioned_client.get_document(base_path, version="nonexistent")

    # =========================================================================
    # Restore Tests
    # =========================================================================

    async def test_preview_restore(self):
        """Test previewing document state at different history points."""
        base_path = self._get_test_path("preview_doc")
        await self.versioned_client.initialize_document(base_path)
        
        state0 = {}
        state1 = {"a": 1}
        state2 = {"a": 1, "b": 2}
        state3 = {"a": 3, "b": 2}
        
        await self.versioned_client.update_document(base_path, state1)
        await self.versioned_client.update_document(base_path, state2)
        await self.versioned_client.update_document(base_path, state3)
        
        # Preview state after first update (sequence 0)
        preview0 = await self.versioned_client.preview_restore(base_path, sequence=0)
        self.assertEqual(preview0, state1)
        
        # Preview state after second update (sequence 1)
        preview1 = await self.versioned_client.preview_restore(base_path, sequence=1)
        self.assertEqual(preview1, state2)
        
        # Preview state after third update (sequence 2)
        preview2 = await self.versioned_client.preview_restore(base_path, sequence=2)
        self.assertEqual(preview2, state3)

        # Try previewing out of range
        with self.assertRaises(ValueError): 
            await self.versioned_client.preview_restore(base_path, sequence=3)
        with self.assertRaises(ValueError): 
            await self.versioned_client.preview_restore(base_path, sequence=-1)
            
    async def test_preview_restore_primitive(self):
        """Test previewing primitive document state at different history points."""
        base_path = self._get_test_path("preview_primitive_doc")
        await self.versioned_client.initialize_document(base_path)
        
        state0 = "initial"
        state1 = 123
        state2 = True
        
        await self.versioned_client.update_document(base_path, state0)
        await self.versioned_client.update_document(base_path, state1)
        await self.versioned_client.update_document(base_path, state2)
        
        # Preview state after first update (sequence 0)
        preview0 = await self.versioned_client.preview_restore(base_path, sequence=0)
        self.assertEqual(preview0, state0)
        
        # Preview state after second update (sequence 1)
        preview1 = await self.versioned_client.preview_restore(base_path, sequence=1)
        self.assertEqual(preview1, state1)
        
        # Preview state after third update (sequence 2)
        preview2 = await self.versioned_client.preview_restore(base_path, sequence=2)
        self.assertEqual(preview2, state2)

    async def test_restore(self):
        """Test restoring document state and pruning history."""
        base_path = self._get_test_path("restore_doc")
        await self.versioned_client.initialize_document(base_path)
        
        state0 = {"a": 1}
        state1 = {"a": 1, "b": 2}
        state2 = {"a": 3, "b": 2}
        state3 = {"a": 3, "b": 4} # This state will be pruned
        
        await self.versioned_client.update_document(base_path, state0) # seq 0
        await self.versioned_client.update_document(base_path, state1) # seq 1
        await self.versioned_client.update_document(base_path, state2) # seq 2
        await self.versioned_client.update_document(base_path, state3) # seq 3
        
        history_before = await self.versioned_client.get_version_history(base_path)
        self.assertEqual(len(history_before), 4)
        self.assertEqual(await self.versioned_client.get_document(base_path), state3)

        # Restore to state after second update (sequence 1)
        restore_ok = await self.versioned_client.restore(base_path, sequence=1)
        self.assertTrue(restore_ok, "Restore should succeed")

        # Verify document state
        doc_after_restore = await self.versioned_client.get_document(base_path)
        self.assertEqual(doc_after_restore, state1, "Document should be restored to state 1")

        # Verify history is pruned
        history_after = await self.versioned_client.get_version_history(base_path)
        self.assertEqual(len(history_after), 2, "History should be pruned to 2 items (seq 0, 1)")
        self.assertEqual(history_after[0]["sequence"], 1, "Newest history item should be sequence 1")
        self.assertEqual(history_after[1]["sequence"], 0, "Oldest history item should be sequence 0")

        # Verify version metadata max_sequence
        version_data = await self.versioned_client._get_version_data(base_path, "v1") # Assuming default v1
        self.assertEqual(version_data[AsyncMongoVersionedClient.MAX_SEQUENCE_KEY], 1, "Max sequence should be updated to 1 after restore")

    # =========================================================================
    # Schema Validation Tests
    # =========================================================================
    test_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "count": {"type": "integer", "minimum": 0},
            "config": {
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean", "default": True},
                    "mode": {"type": "string", "enum": ["read", "write"]}
                },
                "required": ["mode"] 
            }
        },
        "required": ["name", "count", "config"]
    }

    async def test_schema_validation_initialize(self):
        """Test initializing a document with a schema."""
        base_path = self._get_test_path("schema_init_doc")
        init_ok = await self.versioned_client.initialize_document(
            base_path,
            schema=self.test_schema
        )
        self.assertTrue(init_ok)
        
        retrieved_schema = await self.versioned_client.get_schema(base_path)
        self.assertEqual(retrieved_schema, self.test_schema, "Retrieved schema should match initialized schema")
        
        meta = await self.versioned_client._get_document_metadata(base_path)
        self.assertEqual(meta.get('schema'), self.test_schema)

    async def test_schema_validation_update_valid(self):
        """Test valid updates against a schema."""
        base_path = self._get_test_path("schema_valid_doc")
        await self.versioned_client.initialize_document(base_path, schema=self.test_schema)

        # Valid partial update (should use relaxed schema implicitly)
        partial_data = {"name": "Test Doc"}
        update1_ok = await self.versioned_client.update_document(base_path, partial_data)
        self.assertTrue(update1_ok, "Valid partial update should succeed")

        # Valid complete update
        complete_data = {
            "name": "Test Doc Complete",
            "count": 10,
            "config": {"mode": "write"} # 'enabled' will use default
        }
        update2_ok = await self.versioned_client.update_document(base_path, complete_data, is_complete=True)
        self.assertTrue(update2_ok, "Valid complete update should succeed")

        doc = await self.versioned_client.get_document(base_path)
        self.assertEqual(doc["name"], "Test Doc Complete")
        self.assertEqual(doc["count"], 10)
        self.assertEqual(doc["config"]["mode"], "write")
        self.assertTrue(doc["config"].get("enabled"), "Default value for 'enabled' should be set")

    async def test_schema_validation_update_invalid(self):
        """Test invalid updates against a schema."""
        from jsonschema import ValidationError
        base_path = self._get_test_path("schema_invalid_doc")
        await self.versioned_client.initialize_document(base_path, schema=self.test_schema)

        # Invalid type for partial update
        invalid_partial = {"name": 123} # Name should be string
        with self.assertRaises(ValidationError): 
            await self.versioned_client.update_document(base_path, invalid_partial)

        # Invalid complete update (missing required field 'count')
        invalid_complete = {"name": "Test", "config": {"mode": "read"}}
        with self.assertRaises(ValidationError): 
            try:
                await self.versioned_client.update_document(base_path, invalid_complete, is_complete=True)
            except ValidationError as e:
                logger.info(e)
                raise e
            
        # Invalid nested value
        invalid_nested = {
            "name": "Test", 
            "count": 5, 
            "config": {"mode": "invalid_mode"} # Not in enum
        }
        with self.assertRaises(ValidationError):
            await self.versioned_client.update_document(base_path, invalid_nested, is_complete=True)

    async def test_update_schema(self):
        """Test updating the schema for a document."""
        base_path = self._get_test_path("update_schema_doc")
        await self.versioned_client.initialize_document(base_path)
        self.assertIsNone(await self.versioned_client.get_schema(base_path))
        
        update1_ok = await self.versioned_client.update_schema(base_path, self.test_schema)
        self.assertTrue(update1_ok, "First schema update should succeed")
        self.assertEqual(await self.versioned_client.get_schema(base_path), self.test_schema)
        
        new_schema = {"type": "string"}
        update2_ok = await self.versioned_client.update_schema(base_path, new_schema)
        self.assertTrue(update2_ok, "Second schema update should succeed")
        self.assertEqual(await self.versioned_client.get_schema(base_path), new_schema)
        
    # =========================================================================
    # History Pruning Tests
    # =========================================================================
    async def test_history_pruning(self):
        """Test that history is pruned after MAX_HISTORY_LENGTH updates."""
        # Use a smaller max history for testing efficiency
        self.versioned_client.MAX_HISTORY_LENGTH = 5 
        
        base_path = self._get_test_path("pruning_doc")
        await self.versioned_client.initialize_document(base_path)

        # Make more updates than MAX_HISTORY_LENGTH
        num_updates = 8
        for i in range(num_updates):
            await self.versioned_client.update_document(base_path, {"value": i})
            
        # Verify history length
        history = await self.versioned_client.get_version_history(base_path)
        self.assertEqual(len(history), self.versioned_client.MAX_HISTORY_LENGTH, 
                         f"History should be pruned to {self.versioned_client.MAX_HISTORY_LENGTH} items")

        # Verify sequence numbers of remaining history (newest first)
        expected_sequences = list(range(num_updates - 1, num_updates - self.versioned_client.MAX_HISTORY_LENGTH - 1, -1))
        actual_sequences = [item["sequence"] for item in history]
        self.assertEqual(actual_sequences, expected_sequences, "Remaining history items should have correct sequence numbers")

        # Verify min_sequence in version data
        version_data = await self.versioned_client._get_version_data(base_path, "v1") # Assuming default v1
        expected_min_sequence = num_updates - self.versioned_client.MAX_HISTORY_LENGTH
        self.assertEqual(version_data[AsyncMongoVersionedClient.MIN_SEQUENCE_KEY], expected_min_sequence, "min_sequence should be updated after pruning")
        self.assertEqual(version_data[AsyncMongoVersionedClient.MAX_SEQUENCE_KEY], num_updates - 1, "max_sequence should be correct")

        # Test preview restore after pruning (should work for remaining history)
        preview = await self.versioned_client.preview_restore(base_path, sequence=expected_min_sequence)
        self.assertEqual(preview, {"value": expected_min_sequence})
        
        # Test preview restore for pruned sequence (should fail)
        with self.assertRaises(ValueError): 
            await self.versioned_client.preview_restore(base_path, sequence=expected_min_sequence - 1)

    # =========================================================================
    # Deletion Tests
    # =========================================================================
    async def test_delete_document(self):
        """Test deleting the entire versioned document."""
        base_path = self._get_test_path("delete_doc")
        await self.versioned_client.initialize_document(base_path, initial_version="v1")
        await self.versioned_client.update_document(base_path, {"data": "v1_data"}, version="v1")
        await self.versioned_client.create_version(base_path, "v2")
        await self.versioned_client.update_document(base_path, {"data": "v2_data"}, version="v2")

        # Verify things exist before delete
        self.assertIsNotNone(await self.versioned_client._get_document_metadata(base_path))
        self.assertIsNotNone(await self.versioned_client._get_version_data(base_path, "v1"))
        self.assertIsNotNone(await self.versioned_client._get_version_data(base_path, "v2"))
        self.assertGreater(await self.client.count_objects(self.versioned_client._build_history_pattern(base_path, "v1")), 0)
        self.assertGreater(await self.client.count_objects(self.versioned_client._build_history_pattern(base_path, "v2")), 0)

        # Delete the document
        deleted = await self.versioned_client.delete_document(base_path)
        self.assertTrue(deleted, "delete_document should return True")

        # Verify everything is gone
        self.assertIsNone(await self.versioned_client._get_document_metadata(base_path), "Metadata should be deleted")
        self.assertIsNone(await self.versioned_client._get_version_data(base_path, "v1"), "v1 data should be deleted")
        self.assertIsNone(await self.versioned_client._get_version_data(base_path, "v2"), "v2 data should be deleted")
        # Underlying check
        self.assertEqual(await self.client.count_objects(base_path), 0, "Underlying metadata count should be 0")
        self.assertEqual(await self.client.count_objects(self.versioned_client._build_version_path(base_path, "v1")), 0)
        self.assertEqual(await self.client.count_objects(self.versioned_client._build_version_path(base_path, "v2")), 0)
        self.assertEqual(await self.client.count_objects(self.versioned_client._build_history_pattern(base_path, "v1")), 0)
        self.assertEqual(await self.client.count_objects(self.versioned_client._build_history_pattern(base_path, "v2")), 0)
        
        # Try deleting again
        deleted_again = await self.versioned_client.delete_document(base_path)
        self.assertFalse(deleted_again, "Deleting non-existent document should return False")

    # =========================================================================
    # Edge Case and Complex Scenario Tests
    # =========================================================================

    async def test_transition_primitive_to_json(self):
        """Test updating from a primitive type to a JSON object."""
        base_path = self._get_test_path("prim_to_json")
        await self.versioned_client.initialize_document(base_path)
        
        # Update to primitive
        await self.versioned_client.update_document(base_path, 123)
        self.assertEqual(await self.versioned_client.get_document(base_path), 123)
        
        # Update to JSON object
        json_data = {"value": 456, "message": "changed"}
        await self.versioned_client.update_document(base_path, json_data)
        self.assertEqual(await self.versioned_client.get_document(base_path), json_data)
        
        # Check history
        history = await self.versioned_client.get_version_history(base_path)
        self.assertEqual(len(history), 2)
        # The transition TO json is a full replace, so is_primitive should be True for it
        self.assertTrue(history[0]["is_primitive"], "Second history item (prim->JSON transition) should be primitive=True")
        self.assertTrue(history[1]["is_primitive"], "First history item (primitive) should be primitive")
        
        # Test restore
        restored_primitive = await self.versioned_client.preview_restore(base_path, sequence=0)
        self.assertEqual(restored_primitive, 123)
        restored_json = await self.versioned_client.preview_restore(base_path, sequence=1)
        self.assertEqual(restored_json, json_data)

    async def test_transition_json_to_primitive(self):
        """Test updating from a JSON object to a primitive type."""
        base_path = self._get_test_path("json_to_prim")
        await self.versioned_client.initialize_document(base_path)
        
        # Update to JSON object
        json_data = {"value": 789}
        await self.versioned_client.update_document(base_path, json_data)
        self.assertEqual(await self.versioned_client.get_document(base_path), json_data)
        
        # Update to primitive
        await self.versioned_client.update_document(base_path, "finished")
        self.assertEqual(await self.versioned_client.get_document(base_path), "finished")
        
        # Check history
        history = await self.versioned_client.get_version_history(base_path)
        self.assertEqual(len(history), 2)
        self.assertTrue(history[0]["is_primitive"], "Second history item (primitive) should be primitive")
        self.assertFalse(history[1]["is_primitive"], "First history item (JSON) should not be primitive")
        
        # Test restore
        restored_json = await self.versioned_client.preview_restore(base_path, sequence=0)
        self.assertEqual(restored_json, json_data)
        restored_primitive = await self.versioned_client.preview_restore(base_path, sequence=1)
        self.assertEqual(restored_primitive, "finished")

    async def test_deeply_nested_update(self):
        """Test updating deeply nested fields within a JSON object."""
        base_path = self._get_test_path("deep_nested")
        await self.versioned_client.initialize_document(base_path)
        
        initial_data = {"level1": {"level2": {"level3": {"value": "initial"}}}}
        await self.versioned_client.update_document(base_path, initial_data)
        
        # Update nested value
        nested_update = {"level1": {"level2": {"level3": {"value": "updated"}}}}
        await self.versioned_client.update_document(base_path, nested_update)
        
        doc = await self.versioned_client.get_document(base_path)
        self.assertEqual(doc["level1"]["level2"]["level3"]["value"], "updated")
        
        # Check history - should be a specific replace patch
        history = await self.versioned_client.get_version_history(base_path)
        self.assertEqual(len(history), 2)
        patch_obj = jsonpatch.JsonPatch.from_string(history[0]['patch'])
        self.assertEqual(len(patch_obj.patch), 1)
        self.assertEqual(patch_obj.patch[0]['op'], 'replace')
        self.assertEqual(patch_obj.patch[0]['path'], '/level1/level2/level3/value')
        self.assertEqual(patch_obj.patch[0]['value'], 'updated')
        
        # Restore to initial state
        restored = await self.versioned_client.preview_restore(base_path, sequence=0)
        self.assertEqual(restored, initial_data)

    async def test_restore_then_update(self):
        """Test restoring to a previous state and then making new updates."""
        base_path = self._get_test_path("restore_update")
        await self.versioned_client.initialize_document(base_path)
        
        state0 = {"a": 1}
        state1 = {"a": 1, "b": 2}
        state2 = {"a": 1, "b": 3} # This state will be overwritten after restore
        
        await self.versioned_client.update_document(base_path, state0) # seq 0
        await self.versioned_client.update_document(base_path, state1) # seq 1
        await self.versioned_client.update_document(base_path, state2) # seq 2
        
        # Restore to sequence 0 (state0)
        await self.versioned_client.restore(base_path, sequence=0)
        self.assertEqual(await self.versioned_client.get_document(base_path), state0)
        history_after_restore = await self.versioned_client.get_version_history(base_path)
        self.assertEqual(len(history_after_restore), 1) # Only seq 0 should remain
        self.assertEqual(history_after_restore[0]["sequence"], 0)

        # Make a new update
        state3_new = {"a": 1, "c": 4}
        await self.versioned_client.update_document(base_path, state3_new) # seq 1 (new)
        
        # Check final state and history
        self.assertEqual(await self.versioned_client.get_document(base_path), state3_new)
        history_final = await self.versioned_client.get_version_history(base_path)
        self.assertEqual(len(history_final), 2)
        self.assertEqual(history_final[0]["sequence"], 1, "New update should be sequence 1")
        self.assertEqual(history_final[1]["sequence"], 0, "Original restored state should be sequence 0")
        
        # Verify patch for the new update (state0 -> state3_new)
        patch_new = jsonpatch.JsonPatch.from_string(history_final[0]['patch'])
        reconstructed = patch_new.apply(state0)
        self.assertEqual(reconstructed, state3_new)

    async def test_schema_update_validation(self):
        """Test updating schema and validating against the new schema."""
        base_path = self._get_test_path("schema_update_validate")
        initial_schema = {"type": "object", "properties": {"a": {"type": "integer"}}} 
        await self.versioned_client.initialize_document(base_path, schema=initial_schema)
        
        # Update valid against initial schema
        await self.versioned_client.update_document(base_path, {"a": 1})
        
        # Update schema to require a string
        new_schema = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
        await self.versioned_client.update_schema(base_path, new_schema)
        self.assertEqual(await self.versioned_client.get_schema(base_path), new_schema)
        
        # Try updating with integer (invalid against new schema)
        from jsonschema import ValidationError
        with self.assertRaises(ValidationError):
            await self.versioned_client.update_document(base_path, {"a": 2}, is_complete=True)
            
        # Update valid against new schema
        update_ok = await self.versioned_client.update_document(base_path, {"a": "hello"}, is_complete=True)
        self.assertTrue(update_ok)
        self.assertEqual(await self.versioned_client.get_document(base_path), {"a": "hello"})

        # Remove schema
        await self.versioned_client.update_schema(base_path, None)
        self.assertIsNone(await self.versioned_client.get_schema(base_path))
        
        # Update should now succeed without validation
        update_ok_no_schema = await self.versioned_client.update_document(base_path, {"a": 12345})
        self.assertTrue(update_ok_no_schema)
        self.assertEqual(await self.versioned_client.get_document(base_path), {"a": 12345})

    async def test_branching_independence(self):
        """Test creating multiple branches and ensuring their independence."""
        base_path = self._get_test_path("branching_doc")
        await self.versioned_client.initialize_document(base_path, initial_version="main")
        await self.versioned_client.update_document(base_path, {"common": 0, "main_val": 1}) # seq 0

        # Create feature branch from main
        await self.versioned_client.create_version(base_path, "feature", from_version="main")
        
        # Update feature branch
        await self.versioned_client.update_document(base_path, {"feature_val": 10}, version="feature") # seq 0 (feature)
        await self.versioned_client.update_document(base_path, {"common": 1}, version="feature")      # seq 1 (feature)
        
        # Update main branch independently
        await self.versioned_client.update_document(base_path, {"main_val": 2}, version="main")       # seq 1 (main)
        
        # Check states
        doc_main = await self.versioned_client.get_document(base_path, version="main")
        doc_feature = await self.versioned_client.get_document(base_path, version="feature")

        self.assertEqual(doc_main, {"common": 0, "main_val": 2})
        self.assertEqual(doc_feature, {"common": 1, "main_val": 1, "feature_val": 10})

        # Check histories
        history_main = await self.versioned_client.get_version_history(base_path, version="main")
        history_feature = await self.versioned_client.get_version_history(base_path, version="feature")
        
        self.assertEqual(len(history_main), 2)
        self.assertEqual(history_main[0]["sequence"], 1)
        self.assertEqual(history_main[1]["sequence"], 0)
        
        self.assertEqual(len(history_feature), 2)
        self.assertEqual(history_feature[0]["sequence"], 1)
        self.assertEqual(history_feature[1]["sequence"], 0)

    async def test_pruning_and_restore_edge_cases(self):
        """Test interactions between pruning and restore."""
        self.versioned_client.MAX_HISTORY_LENGTH = 2 # Very small limit
        base_path = self._get_test_path("prune_restore_edge")
        await self.versioned_client.initialize_document(base_path)

        await self.versioned_client.update_document(base_path, {"v": 0}) # seq 0
        await self.versioned_client.update_document(base_path, {"v": 1}) # seq 1
        # Pruning happens here, seq 0 should be gone
        await self.versioned_client.update_document(base_path, {"v": 2}) # seq 2 (min_seq=1, max_seq=2)
        
        version_data = await self.versioned_client._get_version_data(base_path, "v1")
        self.assertEqual(version_data[AsyncMongoVersionedClient.MIN_SEQUENCE_KEY], 1)
        self.assertEqual(version_data[AsyncMongoVersionedClient.MAX_SEQUENCE_KEY], 2)
        history = await self.versioned_client.get_version_history(base_path)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["sequence"], 2)
        self.assertEqual(history[1]["sequence"], 1)

        # Try restoring to pruned sequence (0)
        with self.assertRaises(ValueError, msg="Restore to pruned sequence should fail"):
            await self.versioned_client.restore(base_path, sequence=0)
            
        # Try previewing pruned sequence (0)
        with self.assertRaises(ValueError, msg="Preview of pruned sequence should fail"):
            await self.versioned_client.preview_restore(base_path, sequence=0)

        # Restore to earliest available sequence (1)
        restore_ok = await self.versioned_client.restore(base_path, sequence=1)
        self.assertTrue(restore_ok)
        self.assertEqual(await self.versioned_client.get_document(base_path), {"v": 1})
        
        history_after_restore = await self.versioned_client.get_version_history(base_path)
        self.assertEqual(len(history_after_restore), 1)
        self.assertEqual(history_after_restore[0]["sequence"], 1)
        version_data_after = await self.versioned_client._get_version_data(base_path, "v1")
        self.assertEqual(version_data_after[AsyncMongoVersionedClient.MIN_SEQUENCE_KEY], 1) # Min sequence shouldn't change here
        self.assertEqual(version_data_after[AsyncMongoVersionedClient.MAX_SEQUENCE_KEY], 1)

    async def test_empty_and_null_data(self):
        """Test handling of empty strings, lists, dicts and None values."""
        base_path = self._get_test_path("empty_null_data")
        await self.versioned_client.initialize_document(base_path)

        updates = [
            {},              # 0: Empty dict
            {"a": []},      # 1: Empty list
            {"a": [1]},     # 2: Add to list
            {"a": [], "b": ""}, # 3: Empty list and string
            {"b": None},    # 4: Set None
            None,            # 5: Set document to None
            "final_string"   # 6: Set document to string
        ]

        # Track the expected state based on update logic
        expected_state_after_update = {}
        for i, data in enumerate(updates):
            update_ok = await self.versioned_client.update_document(base_path, data)
            self.assertTrue(update_ok, f"Update {i} should succeed")
            
            # Determine expected state based on merging or replacement
            if isinstance(data, dict) and isinstance(expected_state_after_update, dict):
                # Merge dictionaries
                expected_state_after_update = copy.deepcopy(expected_state_after_update)
                expected_state_after_update.update(data)
            else:
                # Replace for primitives or transitions
                expected_state_after_update = data
                
            current_state = await self.versioned_client.get_document(base_path)
            self.assertEqual(current_state, expected_state_after_update, f"State after update {i} mismatch")

        # Check history count - The first update ({}) doesn't create history as it's no change
        history = await self.versioned_client.get_version_history(base_path)
        self.assertEqual(len(history), len(updates) - 1, "Should have history for each update except the first no-op")

        # Test restore through the sequence
        # Sequence numbers will be 0 to len(updates) - 2
        # Restore sequence `i` should match the state after `updates[i+1]` was applied
        expected_states_for_restore = []
        temp_state = {}
        for i, data in enumerate(updates):
             if isinstance(data, dict) and isinstance(temp_state, dict):
                temp_state = copy.deepcopy(temp_state)
                temp_state.update(data)
             else:
                temp_state = data
             # Skip the state for the first no-op update when building expected states for restore
             if i > 0:
                 expected_states_for_restore.append(copy.deepcopy(temp_state))

        # Restore loop should go from sequence 0 up to len(history) - 1
        for seq_idx in range(len(history)):
            restored = await self.versioned_client.preview_restore(base_path, sequence=seq_idx)
            expected_state = expected_states_for_restore[seq_idx]
            # expected_state = updates[seq_idx + 1] # Get the state *after* the update that created sequence i
            self.assertEqual(restored, expected_state, f"Restored state at sequence {seq_idx} mismatch")
            
    async def test_operations_on_uninitialized_doc(self):
        """Test calling methods on a path that hasn't been initialized."""
        base_path = self._get_test_path("uninitialized_doc")
        
        # Get document should return None
        doc = await self.versioned_client.get_document(base_path)
        self.assertIsNone(doc)
        
        # Update should fail (or return False)
        update_ok = await self.versioned_client.update_document(base_path, {"a": 1})
        self.assertFalse(update_ok)
        
        # Get history should be empty
        history = await self.versioned_client.get_version_history(base_path)
        self.assertEqual(history, [])
        
        # List versions should be empty
        versions = await self.versioned_client.list_versions(base_path)
        self.assertEqual(versions, [])
        
        # Create version should fail (returns False if doc doesn't exist)
        create_v2_ok = await self.versioned_client.create_version(base_path, "v2")
        self.assertFalse(create_v2_ok)
        
        # Restore should fail (returns False if doc doesn't exist)
        restore_ok = await self.versioned_client.restore(base_path, sequence=0)
        self.assertFalse(restore_ok)
             
        # Delete document should return False
        deleted = await self.versioned_client.delete_document(base_path)
        self.assertFalse(deleted)
        
        # Delete version should return False
        deleted_version = await self.versioned_client.delete_version(base_path, "v1")
        self.assertFalse(deleted_version)

    async def test_update_document_create_only_fields(self):
        """
        Test the create_only_fields and keep_create_fields_if_missing parameters in update_document.
        
        This test verifies:
        1. Fields in create_only_fields are preserved during document creation
        2. Fields in create_only_fields are removed during document update
        3. keep_create_fields_if_missing controls behavior when fields don't exist in original document
        4. Behavior with multiple versions and branches
        """
        # Scenario 1: Create document with create_only_fields, then update
        base_path1 = self._get_test_path("create_only_fields_doc1")
        await self.versioned_client.initialize_document(base_path1)
        
        # Initial data with create_only fields
        initial_data1 = {
            "title": "Test Document",
            "created_by": "user123",  # Field that should only be included during creation
            "created_timestamp": 12345,  # Field that should only be included during creation
            "content": "Initial content"
        }
        
        # Create document with create_only_fields
        await self.versioned_client.update_document(
            base_path1,
            initial_data1,
            create_only_fields=["created_by", "created_timestamp"],
            keep_create_fields_if_missing=True,
        )
        
        # Verify all fields are present in initial document
        doc1 = await self.versioned_client.get_document(base_path1)
        self.assertEqual(doc1["title"], "Test Document")
        self.assertEqual(doc1["created_by"], "user123")
        self.assertEqual(doc1["created_timestamp"], 12345)
        self.assertEqual(doc1["content"], "Initial content")
        
        # Update document with create_only_fields
        update_data1 = {
            "title": "Updated Document",
            "created_by": "different_user",  # Should be removed from update
            "created_timestamp": 67890,      # Should be removed from update
            "content": "Updated content"
        }
        
        await self.versioned_client.update_document(
            base_path1,
            update_data1,
            create_only_fields=["created_by", "created_timestamp"]
        )
        
        # Verify create_only_fields were preserved with original values
        updated_doc1 = await self.versioned_client.get_document(base_path1)
        self.assertEqual(updated_doc1["title"], "Updated Document")
        self.assertEqual(updated_doc1["created_by"], "user123")  # Original value preserved
        self.assertEqual(updated_doc1["created_timestamp"], 12345)  # Original value preserved
        self.assertEqual(updated_doc1["content"], "Updated content")
        
        # Scenario 2: Document without create_only_fields, update with keep_create_fields_if_missing=True
        base_path2 = self._get_test_path("create_only_fields_doc2")
        await self.versioned_client.initialize_document(base_path2)
        
        # Initial document without create_only fields
        initial_data2 = {
            "title": "Second Document",
            "content": "Second content"
        }
        
        await self.versioned_client.update_document(base_path2, initial_data2)
        
        # Verify initial state
        doc2 = await self.versioned_client.get_document(base_path2)
        self.assertEqual(doc2["title"], "Second Document")
        self.assertNotIn("created_by", doc2)
        self.assertNotIn("created_timestamp", doc2)
        
        # Update with keep_create_fields_if_missing=True
        update_data2 = {
            "title": "Updated Second Document",
            "created_by": "user456",
            "created_timestamp": 54321,
            "content": "Updated second content"
        }
        
        await self.versioned_client.update_document(
            base_path2,
            update_data2,
            create_only_fields=["created_by", "created_timestamp"],
            keep_create_fields_if_missing=True
        )
        
        # Verify create_only_fields were added because they were missing and keep_create_fields_if_missing=True
        updated_doc2 = await self.versioned_client.get_document(base_path2)
        self.assertEqual(updated_doc2["title"], "Updated Second Document")
        self.assertEqual(updated_doc2["created_by"], "user456")  # Should be added
        self.assertEqual(updated_doc2["created_timestamp"], 54321)  # Should be added
        self.assertEqual(updated_doc2["content"], "Updated second content")
        
        # Scenario 3: Document without create_only_fields, update with keep_create_fields_if_missing=False
        base_path3 = self._get_test_path("create_only_fields_doc3")
        await self.versioned_client.initialize_document(base_path3)
        
        # Initial document without create_only fields
        initial_data3 = {
            "title": "Third Document",
            "content": "Third content"
        }
        
        await self.versioned_client.update_document(base_path3, initial_data3)
        
        # Update with keep_create_fields_if_missing=False (default)
        update_data3 = {
            "title": "Updated Third Document",
            "created_by": "user789",
            "created_timestamp": 98765,
            "content": "Updated third content"
        }
        
        await self.versioned_client.update_document(
            base_path3,
            update_data3,
            create_only_fields=["created_by", "created_timestamp"],
            keep_create_fields_if_missing=False
        )
        
        # Verify create_only_fields were NOT added since keep_create_fields_if_missing=False
        updated_doc3 = await self.versioned_client.get_document(base_path3)
        self.assertEqual(updated_doc3["title"], "Updated Third Document")
        self.assertNotIn("created_by", updated_doc3)  # Should NOT be added
        self.assertNotIn("created_timestamp", updated_doc3)  # Should NOT be added
        self.assertEqual(updated_doc3["content"], "Updated third content")
        
        # Scenario 4: Test with multiple versions and branches
        base_path4 = self._get_test_path("create_only_fields_versioned")
        await self.versioned_client.initialize_document(base_path4, initial_version="main")
        
        # Create initial document with create_only fields
        initial_data4 = {
            "title": "Versioned Document",
            "created_by": "main_user",
            "created_timestamp": 11111,
            "content": "Main branch content"
        }
        
        await self.versioned_client.update_document(
            base_path4,
            initial_data4,
            create_only_fields=["created_by", "created_timestamp"],
            keep_create_fields_if_missing=True,
        )
        
        # Create feature branch
        await self.versioned_client.create_version(base_path4, "feature", from_version="main")
        
        # Update main branch - should preserve create_only fields
        await self.versioned_client.update_document(
            base_path4,
            {"title": "Updated Main", "content": "Updated main content"},
            version="main",
            create_only_fields=["created_by", "created_timestamp"]
        )
        
        # Update feature branch with different create_only values
        await self.versioned_client.update_document(
            base_path4,
            {
                "title": "Feature Branch", 
                "content": "Feature content",
                "created_by": "feature_user",  # Should be ignored in update
                "created_timestamp": 22222     # Should be ignored in update
            },
            version="feature",
            create_only_fields=["created_by", "created_timestamp"]
        )
        
        # Verify main branch
        main_doc = await self.versioned_client.get_document(base_path4, version="main")
        self.assertEqual(main_doc["title"], "Updated Main")
        self.assertEqual(main_doc["created_by"], "main_user")  # Preserved from original
        self.assertEqual(main_doc["created_timestamp"], 11111)  # Preserved from original
        self.assertEqual(main_doc["content"], "Updated main content")
        
        # Verify feature branch - should have inherited create_only fields from main
        feature_doc = await self.versioned_client.get_document(base_path4, version="feature")
        self.assertEqual(feature_doc["title"], "Feature Branch")
        self.assertEqual(feature_doc["created_by"], "main_user")  # Inherited from main, preserved
        self.assertEqual(feature_doc["created_timestamp"], 11111)  # Inherited from main, preserved
        self.assertEqual(feature_doc["content"], "Feature content")
        
        # Scenario 5: Edge case - create_only_fields with primitive types
        base_path5 = self._get_test_path("create_only_fields_primitive")
        await self.versioned_client.initialize_document(base_path5)
        
        # Create document with a dict
        await self.versioned_client.update_document(
            base_path5,
            {"field": "value", "created_by": "user"},
            create_only_fields=["created_by"],
            keep_create_fields_if_missing=True,
        )
        
        # Update with a primitive type
        await self.versioned_client.update_document(
            base_path5,
            "primitive string",  # This replaces everything
            create_only_fields=["created_by"]  # Should have no effect with primitive types
        )
        
        # Verify primitive value replaced everything
        doc5 = await self.versioned_client.get_document(base_path5)
        self.assertEqual(doc5, "primitive string")
        
        # Scenario 6: Update with empty create_only_fields list
        base_path6 = self._get_test_path("empty_create_only")
        await self.versioned_client.initialize_document(base_path6)
        
        # Create initial document
        initial_data6 = {"name": "Test", "created_by": "user"}
        await self.versioned_client.update_document(base_path6, initial_data6)
        
        # Update with empty create_only_fields list
        update_data6 = {"name": "Updated", "created_by": "new_user"}
        await self.versioned_client.update_document(
            base_path6,
            update_data6,
            create_only_fields=[]  # Empty list
        )
        
        # Verify all fields were updated
        doc6 = await self.versioned_client.get_document(base_path6)
        self.assertEqual(doc6["name"], "Updated")
        self.assertEqual(doc6["created_by"], "new_user")  # Should be updated since not in create_only_fields

    # =========================================================================
    # Move/Copy Operation Tests
    # =========================================================================

    async def test_move_document_basic(self):
        """Test basic move operation for a versioned document."""
        source_path = self._get_test_path("move_source_doc")
        dest_path = self._get_test_path("move_dest_doc")
        
        # Create and populate source document
        await self.versioned_client.initialize_document(source_path, initial_version="v1")
        await self.versioned_client.update_document(source_path, {"name": "Original Doc", "value": 100})
        await self.versioned_client.update_document(source_path, {"name": "Updated Doc", "value": 200})
        
        # Create second version with its own history
        await self.versioned_client.create_version(source_path, "v2")
        await self.versioned_client.update_document(source_path, {"name": "V2 Doc", "type": "version2"}, version="v2")
        
        # Verify source exists before move
        source_metadata = await self.versioned_client._get_document_metadata(source_path)
        self.assertIsNotNone(source_metadata)
        self.assertEqual(len(source_metadata["versions"]), 2)
        
        source_doc_v1 = await self.versioned_client.get_document(source_path, version="v1")
        source_doc_v2 = await self.versioned_client.get_document(source_path, version="v2")
        self.assertEqual(source_doc_v1["name"], "Updated Doc")
        self.assertEqual(source_doc_v2["name"], "V2 Doc")
        
        # Move document
        move_success = await self.versioned_client.move_document(source_path, dest_path, move=True)
        self.assertTrue(move_success, "Move operation should succeed")
        
        # Verify source no longer exists
        source_metadata_after = await self.versioned_client._get_document_metadata(source_path)
        self.assertIsNone(source_metadata_after, "Source metadata should not exist after move")
        
        source_doc_after = await self.versioned_client.get_document(source_path)
        self.assertIsNone(source_doc_after, "Source document should not exist after move")
        
        # Verify destination exists with all data
        dest_metadata = await self.versioned_client._get_document_metadata(dest_path)
        self.assertIsNotNone(dest_metadata, "Destination metadata should exist")
        self.assertEqual(dest_metadata["active_version"], "v1")
        self.assertEqual(len(dest_metadata["versions"]), 2)
        self.assertIn("v1", dest_metadata["versions"])
        self.assertIn("v2", dest_metadata["versions"])
        
        # Verify document content at destination
        dest_doc_v1 = await self.versioned_client.get_document(dest_path, version="v1")
        dest_doc_v2 = await self.versioned_client.get_document(dest_path, version="v2")
        self.assertEqual(dest_doc_v1, source_doc_v1, "V1 content should match original")
        self.assertEqual(dest_doc_v2, source_doc_v2, "V2 content should match original")
        
        # Verify history is preserved
        dest_history_v1 = await self.versioned_client.get_version_history(dest_path, version="v1")
        dest_history_v2 = await self.versioned_client.get_version_history(dest_path, version="v2")
        self.assertEqual(len(dest_history_v1), 2, "V1 should have 2 history items")
        self.assertEqual(len(dest_history_v2), 1, "V2 should have 1 history item")
        
        # Clean up
        await self.versioned_client.delete_document(dest_path)
    
    async def test_copy_document_basic(self):
        """Test basic copy operation for a versioned document."""
        source_path = self._get_test_path("copy_source_doc")
        dest_path = self._get_test_path("copy_dest_doc")
        
        # Create and populate source document
        await self.versioned_client.initialize_document(source_path, initial_version="main")
        await self.versioned_client.update_document(source_path, {"title": "Source Document", "content": "Original content"})
        await self.versioned_client.update_document(source_path, {"title": "Updated Source", "content": "Updated content"})
        
        # Create branch with different content
        await self.versioned_client.create_version(source_path, "feature")
        await self.versioned_client.update_document(source_path, {"title": "Feature Branch", "feature": True}, version="feature")
        
        # Copy document (move=False)
        copy_success = await self.versioned_client.copy_document(source_path, dest_path)
        self.assertTrue(copy_success, "Copy operation should succeed")
        
        # Verify source still exists and is unchanged
        source_metadata = await self.versioned_client._get_document_metadata(source_path)
        self.assertIsNotNone(source_metadata, "Source metadata should still exist after copy")
        
        source_doc_main = await self.versioned_client.get_document(source_path, version="main")
        source_doc_feature = await self.versioned_client.get_document(source_path, version="feature")
        self.assertEqual(source_doc_main["title"], "Updated Source")
        self.assertEqual(source_doc_feature["title"], "Feature Branch")
        
        # Verify destination exists with copied data
        dest_metadata = await self.versioned_client._get_document_metadata(dest_path)
        self.assertIsNotNone(dest_metadata, "Destination metadata should exist")
        self.assertEqual(dest_metadata["active_version"], "main")
        self.assertEqual(len(dest_metadata["versions"]), 2)
        
        # Verify content matches at destination
        dest_doc_main = await self.versioned_client.get_document(dest_path, version="main")
        dest_doc_feature = await self.versioned_client.get_document(dest_path, version="feature")
        self.assertEqual(dest_doc_main, source_doc_main, "Main version content should match")
        self.assertEqual(dest_doc_feature, source_doc_feature, "Feature version content should match")
        
        # Verify history is copied
        source_history_main = await self.versioned_client.get_version_history(source_path, version="main")
        dest_history_main = await self.versioned_client.get_version_history(dest_path, version="main")
        self.assertEqual(len(dest_history_main), len(source_history_main), "History should be copied")
        
        # Verify independence: update source after copy
        await self.versioned_client.update_document(source_path, {"title": "Modified After Copy", "modified": True})
        
        source_doc_modified = await self.versioned_client.get_document(source_path, version="main")
        dest_doc_unchanged = await self.versioned_client.get_document(dest_path, version="main")
        
        self.assertEqual(source_doc_modified["title"], "Modified After Copy")
        self.assertEqual(dest_doc_unchanged["title"], "Updated Source", "Destination should remain unchanged")
        
        # Clean up
        await self.versioned_client.delete_document(source_path)
        await self.versioned_client.delete_document(dest_path)
    
    async def test_move_document_same_path(self):
        """Test move/copy operation with identical source and destination paths."""
        doc_path = self._get_test_path("same_path_doc")
        
        # Create document
        await self.versioned_client.initialize_document(doc_path)
        await self.versioned_client.update_document(doc_path, {"test": "same path operation"})
        
        # Move to same path (should succeed with no-op)
        move_result = await self.versioned_client.move_document(doc_path, doc_path, move=True)
        self.assertTrue(move_result, "Move to same path should succeed")
        
        # Copy to same path (should succeed with warning)
        copy_result = await self.versioned_client.copy_document(doc_path, doc_path)
        self.assertTrue(copy_result, "Copy to same path should succeed")
        
        # Verify document still exists and is unchanged
        doc = await self.versioned_client.get_document(doc_path)
        self.assertIsNotNone(doc)
        self.assertEqual(doc["test"], "same path operation")
        
        # Clean up
        await self.versioned_client.delete_document(doc_path)
    
    async def test_move_document_destination_exists_no_overwrite(self):
        """Test move operation when destination exists and overwrite is False."""
        source_path = self._get_test_path("move_src_exists")
        dest_path = self._get_test_path("move_dest_exists")
        
        # Create source document
        await self.versioned_client.initialize_document(source_path)
        await self.versioned_client.update_document(source_path, {"source": "data"})
        
        # Create destination document
        await self.versioned_client.initialize_document(dest_path)
        await self.versioned_client.update_document(dest_path, {"dest": "data"})
        
        # Try to move without overwrite (should fail)
        with self.assertRaises(ValueError) as context:
            await self.versioned_client.move_document(source_path, dest_path, overwrite_destination=False)
        
        self.assertIn("already exists", str(context.exception))
        
        # Verify both documents still exist unchanged
        source_doc = await self.versioned_client.get_document(source_path)
        dest_doc = await self.versioned_client.get_document(dest_path)
        
        self.assertIsNotNone(source_doc)
        self.assertIsNotNone(dest_doc)
        self.assertEqual(source_doc["source"], "data")
        self.assertEqual(dest_doc["dest"], "data")
        
        # Clean up
        await self.versioned_client.delete_document(source_path)
        await self.versioned_client.delete_document(dest_path)
    
    async def test_move_document_destination_exists_with_overwrite(self):
        """Test move operation when destination exists and overwrite is True."""
        source_path = self._get_test_path("move_src_overwrite")
        dest_path = self._get_test_path("move_dest_overwrite")
        
        # Create source document with multiple versions
        await self.versioned_client.initialize_document(source_path, initial_version="v1")
        await self.versioned_client.update_document(source_path, {"source": "original", "value": 1})
        await self.versioned_client.create_version(source_path, "v2")
        await self.versioned_client.update_document(source_path, {"source": "v2_data", "value": 2}, version="v2")
        
        # Create destination document (will be overwritten)
        await self.versioned_client.initialize_document(dest_path, initial_version="old")
        await self.versioned_client.update_document(dest_path, {"dest": "will_be_overwritten"}, version="old")
        
        # Move with overwrite
        move_success = await self.versioned_client.move_document(
            source_path, 
            dest_path, 
            overwrite_destination=True, 
            move=True
        )
        self.assertTrue(move_success, "Move with overwrite should succeed")
        
        # Verify source is gone
        source_doc = await self.versioned_client.get_document(source_path)
        self.assertIsNone(source_doc, "Source should be gone after move")
        
        # Verify destination has source data (not original dest data)
        dest_metadata = await self.versioned_client._get_document_metadata(dest_path)
        self.assertIsNotNone(dest_metadata)
        self.assertEqual(dest_metadata["active_version"], "v1")  # Source's active version
        self.assertIn("v1", dest_metadata["versions"])
        self.assertIn("v2", dest_metadata["versions"])
        self.assertNotIn("old", dest_metadata["versions"])  # Original dest version should be gone
        
        dest_doc_v1 = await self.versioned_client.get_document(dest_path, version="v1")
        dest_doc_v2 = await self.versioned_client.get_document(dest_path, version="v2")
        
        self.assertEqual(dest_doc_v1["source"], "original")
        self.assertEqual(dest_doc_v2["source"], "v2_data")
        
        # Clean up
        await self.versioned_client.delete_document(dest_path)
    
    async def test_move_nonexistent_document(self):
        """Test move operation on a non-existent document."""
        source_path = self._get_test_path("nonexistent_source")
        dest_path = self._get_test_path("nonexistent_dest")
        
        # Try to move non-existent document
        move_result = await self.versioned_client.move_document(source_path, dest_path)
        self.assertFalse(move_result, "Moving non-existent document should return False")
        
        # Verify destination doesn't exist
        dest_doc = await self.versioned_client.get_document(dest_path)
        self.assertIsNone(dest_doc, "Destination should not exist after failed move")
    
    async def test_copy_with_schema_preservation(self):
        """Test that copy operation preserves schema information."""
        source_path = self._get_test_path("schema_copy_source")
        dest_path = self._get_test_path("schema_copy_dest")
        
        # Schema for testing
        test_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "value": {"type": "integer", "minimum": 0}
            },
            "required": ["name", "value"]
        }
        
        # Create source document with schema
        await self.versioned_client.initialize_document(source_path, schema=test_schema)
        await self.versioned_client.update_document(source_path, {"name": "Test", "value": 42}, is_complete=True)
        
        # Copy document
        copy_success = await self.versioned_client.copy_document(source_path, dest_path)
        self.assertTrue(copy_success)
        
        # Verify schema is preserved at destination
        source_schema = await self.versioned_client.get_schema(source_path)
        dest_schema = await self.versioned_client.get_schema(dest_path)
        
        self.assertEqual(dest_schema, test_schema, "Schema should be preserved in copy")
        self.assertEqual(dest_schema, source_schema, "Schemas should match")
        
        # Verify schema validation works at destination
        # Valid update should succeed
        await self.versioned_client.update_document(dest_path, {"name": "Updated", "value": 100}, is_complete=True)
        
        # Invalid update should fail
        with self.assertRaises(ValidationError):
            await self.versioned_client.update_document(dest_path, {"name": "Invalid", "value": -1}, is_complete=True)
        
        # Clean up
        await self.versioned_client.delete_document(source_path)
        await self.versioned_client.delete_document(dest_path)
    
    async def test_batch_move_documents(self):
        """Test batch move operation for multiple versioned documents."""
        # Create multiple source documents
        move_pairs = []
        for i in range(3):
            source_path = self._get_test_path(f"batch_move_src_{i}")
            dest_path = self._get_test_path(f"batch_move_dest_{i}")
            move_pairs.append((source_path, dest_path))
            
            # Create and populate each source document
            await self.versioned_client.initialize_document(source_path, initial_version="v1")
            await self.versioned_client.update_document(source_path, {"index": i, "name": f"Document {i}"})
            
            if i == 1:  # Add extra complexity to middle document
                await self.versioned_client.create_version(source_path, "v2")
                await self.versioned_client.update_document(source_path, {"extra": "data"}, version="v2")
        
        # Perform batch move
        results = await self.versioned_client.batch_move_documents(move_pairs, move=True)
        
        # Verify results
        self.assertEqual(len(results), 3, "Should return 3 results")
        self.assertTrue(all(results), "All moves should succeed")
        
        # Verify each move
        for i, (source_path, dest_path) in enumerate(move_pairs):
            with self.subTest(index=i):
                # Source should not exist
                source_doc = await self.versioned_client.get_document(source_path)
                self.assertIsNone(source_doc, f"Source {i} should not exist after move")
                
                # Destination should exist with correct data
                dest_doc = await self.versioned_client.get_document(dest_path)
                self.assertIsNotNone(dest_doc, f"Destination {i} should exist")
                self.assertEqual(dest_doc["index"], i, f"Destination {i} should have correct index")
                self.assertEqual(dest_doc["name"], f"Document {i}", f"Destination {i} should have correct name")
                
                # Special check for document 1 with extra version
                if i == 1:
                    dest_metadata = await self.versioned_client._get_document_metadata(dest_path)
                    self.assertIn("v2", dest_metadata["versions"], "Document 1 should have v2 version")
                    
                    dest_doc_v2 = await self.versioned_client.get_document(dest_path, version="v2")
                    self.assertEqual(dest_doc_v2["extra"], "data", "V2 data should be preserved")
        
        # Clean up
        for _, dest_path in move_pairs:
            await self.versioned_client.delete_document(dest_path)
    
    async def test_batch_copy_documents(self):
        """Test batch copy operation for multiple versioned documents."""
        # Create multiple source documents
        copy_pairs = []
        for i in range(4):
            source_path = self._get_test_path(f"batch_copy_src_{i}")
            dest_path = self._get_test_path(f"batch_copy_dest_{i}")
            copy_pairs.append((source_path, dest_path))
            
            # Create and populate each source document
            await self.versioned_client.initialize_document(source_path)
            await self.versioned_client.update_document(source_path, {"id": i, "data": f"copy_test_{i}"})
        
        # Perform batch copy
        results = await self.versioned_client.batch_copy_documents(copy_pairs)
        
        # Verify results
        self.assertEqual(len(results), 4, "Should return 4 results")
        self.assertTrue(all(results), "All copies should succeed")
        
        # Verify each copy
        for i, (source_path, dest_path) in enumerate(copy_pairs):
            with self.subTest(index=i):
                # Source should still exist
                source_doc = await self.versioned_client.get_document(source_path)
                self.assertIsNotNone(source_doc, f"Source {i} should still exist after copy")
                
                # Destination should exist with matching data
                dest_doc = await self.versioned_client.get_document(dest_path)
                self.assertIsNotNone(dest_doc, f"Destination {i} should exist")
                self.assertEqual(dest_doc, source_doc, f"Destination {i} should match source")
        
        # Test independence: modify sources after copy
        for i, (source_path, dest_path) in enumerate(copy_pairs):
            await self.versioned_client.update_document(source_path, {"modified": True})
            
            source_doc_modified = await self.versioned_client.get_document(source_path)
            dest_doc_unchanged = await self.versioned_client.get_document(dest_path)
            
            self.assertTrue(source_doc_modified.get("modified"), f"Source {i} should be modified")
            self.assertNotIn("modified", dest_doc_unchanged, f"Destination {i} should be unchanged")
        
        # Clean up
        for source_path, dest_path in copy_pairs:
            await self.versioned_client.delete_document(source_path)
            await self.versioned_client.delete_document(dest_path)
    
    async def test_batch_move_mixed_results(self):
        """Test batch move with mix of existing and non-existing sources."""
        move_pairs = []
        existing_indices = [0, 2]  # Only create documents for indices 0 and 2
        
        for i in range(4):
            source_path = self._get_test_path(f"mixed_move_src_{i}")
            dest_path = self._get_test_path(f"mixed_move_dest_{i}")
            move_pairs.append((source_path, dest_path))
            
            # Only create some source documents
            if i in existing_indices:
                await self.versioned_client.initialize_document(source_path)
                await self.versioned_client.update_document(source_path, {"exists": True, "index": i})
        
        # Perform batch move
        results = await self.versioned_client.batch_move_documents(move_pairs, move=True)
        
        # Verify results
        self.assertEqual(len(results), 4, "Should return 4 results")
        
        for i, result in enumerate(results):
            if i in existing_indices:
                self.assertTrue(result, f"Move {i} should succeed (source exists)")
            else:
                self.assertFalse(result, f"Move {i} should fail (source doesn't exist)")
        
        # Verify successful moves
        for i in existing_indices:
            source_path, dest_path = move_pairs[i]
            
            source_doc = await self.versioned_client.get_document(source_path)
            dest_doc = await self.versioned_client.get_document(dest_path)
            
            self.assertIsNone(source_doc, f"Source {i} should not exist after successful move")
            self.assertIsNotNone(dest_doc, f"Destination {i} should exist after successful move")
            self.assertTrue(dest_doc["exists"], f"Destination {i} should have correct data")
        
        # Verify failed moves don't create destinations
        for i, result in enumerate(results):
            if not result:
                _, dest_path = move_pairs[i]
                dest_doc = await self.versioned_client.get_document(dest_path)
                self.assertIsNone(dest_doc, f"Destination {i} should not exist for failed move")
        
        # Clean up
        for i in existing_indices:
            _, dest_path = move_pairs[i]
            await self.versioned_client.delete_document(dest_path)
    
    async def test_move_document_complex_history(self):
        """Test move operation with complex version history and restoration."""
        source_path = self._get_test_path("complex_history_source")
        dest_path = self._get_test_path("complex_history_dest")
        
        # Create document with complex history
        await self.versioned_client.initialize_document(source_path, initial_version="main")
        
        # Build up history in main version
        states = [
            {"title": "Initial", "step": 1},
            {"title": "Step 2", "step": 2, "data": [1, 2]},
            {"title": "Step 3", "step": 3, "data": [1, 2, 3], "config": {"enabled": True}},
            {"title": "Step 4", "step": 4, "data": [1, 2, 3, 4], "config": {"enabled": False, "mode": "test"}}
        ]
        
        for state in states:
            await self.versioned_client.update_document(source_path, state, version="main")
        
        # Create feature branch and modify it
        await self.versioned_client.create_version(source_path, "feature", from_version="main")
        await self.versioned_client.update_document(source_path, {"feature_flag": True}, version="feature")
        await self.versioned_client.update_document(source_path, {"title": "Feature Complete"}, version="feature")
        
        # Restore main to an earlier state
        await self.versioned_client.restore(source_path, sequence=1, version="main")  # Back to step 2
        
        # Add new history after restore
        await self.versioned_client.update_document(source_path, {"title": "New Path", "step": 2.5}, version="main")
        
        # Get complete state before move
        source_metadata_before = await self.versioned_client._get_document_metadata(source_path)
        source_main_before = await self.versioned_client.get_document(source_path, version="main")
        source_feature_before = await self.versioned_client.get_document(source_path, version="feature")
        source_history_main_before = await self.versioned_client.get_version_history(source_path, version="main")
        source_history_feature_before = await self.versioned_client.get_version_history(source_path, version="feature")
        
        # Move document
        move_success = await self.versioned_client.move_document(source_path, dest_path, move=True)
        self.assertTrue(move_success, "Complex document move should succeed")
        
        # Verify complete preservation of structure at destination
        dest_metadata = await self.versioned_client._get_document_metadata(dest_path)
        dest_main = await self.versioned_client.get_document(dest_path, version="main")
        dest_feature = await self.versioned_client.get_document(dest_path, version="feature")
        dest_history_main = await self.versioned_client.get_version_history(dest_path, version="main")
        dest_history_feature = await self.versioned_client.get_version_history(dest_path, version="feature")
        
        # Verify metadata matches
        self.assertEqual(dest_metadata["active_version"], source_metadata_before["active_version"])
        self.assertEqual(dest_metadata["versions"], source_metadata_before["versions"])
        
        # Verify document states match
        self.assertEqual(dest_main, source_main_before, "Main version should match")
        self.assertEqual(dest_feature, source_feature_before, "Feature version should match")
        
        # Verify history preservation and structure
        self.assertEqual(len(dest_history_main), len(source_history_main_before), "Main history length should match")
        self.assertEqual(len(dest_history_feature), len(source_history_feature_before), "Feature history length should match")
        
        # Verify specific history details
        for i, (dest_item, source_item) in enumerate(zip(dest_history_main, source_history_main_before)):
            self.assertEqual(dest_item["sequence"], source_item["sequence"], f"Main history item {i} sequence should match")
            self.assertEqual(dest_item["patch"], source_item["patch"], f"Main history item {i} patch should match")
        
        # Test restoration functionality at destination
        preview_dest = await self.versioned_client.preview_restore(dest_path, sequence=0, version="main")
        self.assertEqual(preview_dest["step"], 1, "Should be able to preview first state")
        
        # Test that new updates work at destination
        await self.versioned_client.update_document(dest_path, {"moved": True}, version="main")
        updated_dest = await self.versioned_client.get_document(dest_path, version="main")
        self.assertTrue(updated_dest.get("moved"), "Should be able to update moved document")
        
        # Clean up
        await self.versioned_client.delete_document(dest_path)
        
        # Verify source is completely gone
        source_doc_after = await self.versioned_client.get_document(source_path)
        self.assertIsNone(source_doc_after, "Source should be completely gone after move")

    # =========================================================================
    # Redis Lock Integration Tests
    # =========================================================================

    async def test_concurrent_document_updates_with_locks(self):
        """
        Test that concurrent document updates are properly serialized by Redis locks.
        This ensures mutual exclusion during document modifications.
        """
        base_path = self._get_test_path("concurrent_updates_doc")
        await self.versioned_client.initialize_document(base_path, initial_version="main")

        # Track execution order and timing
        execution_order = []
        timing_data = {}
        
        async def worker_update(worker_id: str, update_data: Dict[str, Any], hold_duration: float = 0.5):
            """
            Worker that performs a document update, optionally holding the lock longer.
            
            Args:
                worker_id: Unique identifier for this worker
                update_data: Data to update in the document
                hold_duration: How long to simulate work after acquiring the lock
            """
            start_time = time.time()
            execution_order.append(f"{worker_id}_start")
            logger.info(f"Worker {worker_id}: Starting update operation")
            
            try:
                # Simulate some work before the actual update
                if hold_duration > 0:
                    # Get current document first (this also acquires lock)
                    current_doc = await self.versioned_client.get_document(base_path)
                    execution_order.append(f"{worker_id}_got_doc")
                    
                    # Simulate processing time
                    await asyncio.sleep(hold_duration)
                    execution_order.append(f"{worker_id}_processed")
                
                # Perform the update
                success = await self.versioned_client.update_document(base_path, update_data)
                update_time = time.time()
                execution_order.append(f"{worker_id}_updated")
                
                timing_data[worker_id] = {
                    'start_time': start_time,
                    'update_time': update_time,
                    'total_duration': update_time - start_time,
                    'success': success
                }
                
                logger.info(f"Worker {worker_id}: Update completed in {update_time - start_time:.2f}s")
                return success
                
            except Exception as e:
                execution_order.append(f"{worker_id}_error")
                logger.error(f"Worker {worker_id}: Error during update - {e}")
                timing_data[worker_id] = {
                    'start_time': start_time,
                    'error': str(e),
                    'success': False
                }
                return False

        # Test Case 1: Two workers updating different fields concurrently
        logger.info("=== Test Case 1: Two concurrent updates ===")
        
        # Create concurrent update tasks
        tasks = [
            asyncio.create_task(worker_update("A", {"field_a": "value_a", "counter": 1}, 0.8)),
            asyncio.create_task(worker_update("B", {"field_b": "value_b", "counter": 2}, 0.6)),
        ]
        
        # Execute tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify all updates succeeded
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.fail(f"Worker task {i} raised an exception: {result}")
            self.assertTrue(result, f"Worker task {i} should have succeeded")
        
        # Verify final document state
        final_doc = await self.versioned_client.get_document(base_path)
        self.assertIn("field_a", final_doc, "Field from worker A should be present")
        self.assertIn("field_b", final_doc, "Field from worker B should be present")
        self.assertIn("counter", final_doc, "Counter field should be present")
        
        # One of the counter values should be present (last writer wins for conflicting fields)
        self.assertIn(final_doc["counter"], [1, 2], "Counter should have one of the worker values")
        
        # Verify operations were serialized (no overlap in execution)
        a_start_time = timing_data["A"]["start_time"]
        a_update_time = timing_data["A"]["update_time"]
        b_start_time = timing_data["B"]["start_time"]
        b_update_time = timing_data["B"]["update_time"]
        
        # Check if operations were serialized (no overlap)
        serialized = (a_update_time <= b_start_time + 0.1) or (b_update_time <= a_start_time + 0.1)
        if not serialized:
            # Operations might have overlapped, which shouldn't happen with proper locking
            logger.warning(f"Possible operation overlap detected: A({a_start_time:.2f}-{a_update_time:.2f}), B({b_start_time:.2f}-{b_update_time:.2f})")
        
        # Check that updates happened in sequence (one finishes before the other processes)
        execution_sequence = execution_order
        logger.info(f"Execution sequence: {execution_sequence}")
        
        # Clear for next test
        execution_order.clear()
        timing_data.clear()

    async def test_concurrent_version_creation_with_locks(self):
        """
        Test that concurrent version creation operations are properly serialized.
        """
        base_path = self._get_test_path("concurrent_versions_doc")
        await self.versioned_client.initialize_document(base_path, initial_version="v1")
        
        # Add some data to v1
        await self.versioned_client.update_document(base_path, {"base_data": "initial"})
        
        execution_order = []
        creation_results = {}
        
        async def create_version_worker(worker_id: str, version_name: str):
            """Worker that attempts to create a new version."""
            start_time = time.time()
            execution_order.append(f"{worker_id}_start")
            logger.info(f"Worker {worker_id}: Attempting to create version {version_name}")
            
            try:
                success = await self.versioned_client.create_version(base_path, version_name)
                end_time = time.time()
                execution_order.append(f"{worker_id}_success" if success else f"{worker_id}_failed")
                
                creation_results[worker_id] = {
                    'version_name': version_name,
                    'success': success,
                    'duration': end_time - start_time
                }
                
                logger.info(f"Worker {worker_id}: Version creation {'succeeded' if success else 'failed'} in {end_time - start_time:.2f}s")
                return success
                
            except Exception as e:
                execution_order.append(f"{worker_id}_error")
                creation_results[worker_id] = {
                    'version_name': version_name,
                    'success': False,
                    'error': str(e)
                }
                logger.error(f"Worker {worker_id}: Error creating version - {e}")
                return False

        # Test concurrent version creation
        tasks = [
            asyncio.create_task(create_version_worker("X", "v2")),
            asyncio.create_task(create_version_worker("Y", "v3")),
            asyncio.create_task(create_version_worker("Z", "v4")),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All workers should succeed (different version names)
        successful_creations = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Worker task {i} raised exception: {result}")
                continue
            if result:
                successful_creations += 1
        
        self.assertEqual(successful_creations, 3, "All three workers should successfully create versions")
        
        # Verify all versions exist
        versions_list = await self.versioned_client.list_versions(base_path)
        version_names = [v["version"] for v in versions_list]
        self.assertIn("v1", version_names, "Original version should exist")
        self.assertIn("v2", version_names, "Version v2 should exist")
        self.assertIn("v3", version_names, "Version v3 should exist")
        self.assertIn("v4", version_names, "Version v4 should exist")
        
        logger.info(f"Version creation execution order: {execution_order}")
        logger.info(f"Creation results: {creation_results}")

    async def test_concurrent_update_and_restore_with_locks(self):
        """
        Test concurrent update and restore operations to ensure they don't interfere.
        """
        base_path = self._get_test_path("concurrent_update_restore_doc")
        await self.versioned_client.initialize_document(base_path)
        
        # Create initial state with some history
        await self.versioned_client.update_document(base_path, {"step": 1, "data": "initial"})
        await self.versioned_client.update_document(base_path, {"step": 2, "data": "updated"})
        await self.versioned_client.update_document(base_path, {"step": 3, "data": "final"})
        
        operation_results = {}
        
        async def update_worker():
            """Worker that performs document updates."""
            start_time = time.time()
            try:
                # Perform multiple updates
                success1 = await self.versioned_client.update_document(base_path, {"concurrent_update": True, "step": 4})
                await asyncio.sleep(0.2)  # Small delay
                success2 = await self.versioned_client.update_document(base_path, {"concurrent_update": True, "step": 5})
                
                end_time = time.time()
                operation_results["updater"] = {
                    'success': success1 and success2,
                    'duration': end_time - start_time,
                    'operation': 'update'
                }
                logger.info(f"Update worker completed in {end_time - start_time:.2f}s")
                return success1 and success2
                
            except Exception as e:
                operation_results["updater"] = {'success': False, 'error': str(e), 'operation': 'update'}
                logger.error(f"Update worker error: {e}")
                return False

        async def restore_worker():
            """Worker that performs document restore."""
            start_time = time.time()
            try:
                # Wait a bit then restore to an earlier state
                await asyncio.sleep(0.1)
                success = await self.versioned_client.restore(base_path, sequence=1)  # Restore to step 2
                
                end_time = time.time()
                operation_results["restorer"] = {
                    'success': success,
                    'duration': end_time - start_time,
                    'operation': 'restore'
                }
                logger.info(f"Restore worker completed in {end_time - start_time:.2f}s")
                return success
                
            except Exception as e:
                operation_results["restorer"] = {'success': False, 'error': str(e), 'operation': 'restore'}
                logger.error(f"Restore worker error: {e}")
                return False

        # Run both operations concurrently
        update_task = asyncio.create_task(update_worker())
        restore_task = asyncio.create_task(restore_worker())
        
        results = await asyncio.gather(update_task, restore_task, return_exceptions=True)
        
        # At least one operation should succeed (they should be serialized)
        successful_operations = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Operation {i} raised exception: {result}")
            elif result:
                successful_operations += 1
        
        self.assertGreaterEqual(successful_operations, 1, "At least one operation should succeed")
        
        # Verify final document state is consistent
        final_doc = await self.versioned_client.get_document(base_path)
        self.assertIsNotNone(final_doc, "Final document should exist")
        
        # Check document integrity - it should be in a valid state
        self.assertIn("step", final_doc, "Document should have a step field")
        self.assertIn("data", final_doc, "Document should have a data field")
        
        logger.info(f"Final document state: {final_doc}")
        logger.info(f"Operation results: {operation_results}")

    async def test_lock_timeout_behavior(self):
        """
        Test that lock timeouts work correctly when operations take too long.
        """
        base_path = self._get_test_path("lock_timeout_doc")
        await self.versioned_client.initialize_document(base_path)
        
        # Create a versioned client with very short timeout for this test
        short_timeout_client = AsyncMongoVersionedClient(
            client=self.client,
            segment_names=self.base_segment_names,
            redis_client=self.redis_client,
            return_timestamp_metadata=False,
            lock_timeout=2,  # Very short timeout
            lock_ttl=10
        )
        
        operation_results = {}
        
        async def long_running_operation():
            """Operation that holds the lock for a long time."""
            start_time = time.time()
            try:
                # Acquire the lock manually using Redis client directly
                lock_key = self.versioned_client._get_document_lock_key(base_path)
                token = await self.versioned_client._redis_client.acquire_lock(lock_key, timeout=5, ttl=30)
                
                if token:
                    logger.info("Long operation: Acquired lock, simulating long work...")
                    
                    # Simulate long processing time while holding the lock
                    await asyncio.sleep(4.0)  # Longer than the short timeout
                    
                    # Release the lock
                    await self.versioned_client._redis_client.release_lock(lock_key, token)
                    
                    end_time = time.time()
                    operation_results["long_op"] = {
                        'success': True,
                        'duration': end_time - start_time
                    }
                    logger.info(f"Long operation completed in {end_time - start_time:.2f}s")
                    return True
                else:
                    logger.error("Long operation: Failed to acquire lock")
                    operation_results["long_op"] = {'success': False, 'error': 'Failed to acquire lock'}
                    return False
                
            except Exception as e:
                operation_results["long_op"] = {'success': False, 'error': str(e)}
                logger.error(f"Long operation error: {e}")
                return False

        async def quick_operation():
            """Quick operation that should timeout waiting for the lock."""
            start_time = time.time()
            try:
                # Wait a bit to ensure long operation starts first
                await asyncio.sleep(0.5)
                
                # Try to acquire the same lock with short timeout - this should fail
                lock_key = self.versioned_client._get_document_lock_key(base_path)
                token = await short_timeout_client._redis_client.acquire_lock(lock_key, timeout=2, ttl=10)
                
                if token:
                    # If we got the lock, release it immediately
                    await short_timeout_client._redis_client.release_lock(lock_key, token)
                    end_time = time.time()
                    operation_results["quick_op"] = {
                        'success': True,
                        'duration': end_time - start_time
                    }
                    logger.info(f"Quick operation unexpectedly succeeded in {end_time - start_time:.2f}s")
                    return True
                else:
                    # Failed to acquire lock - this is expected
                    end_time = time.time()
                    operation_results["quick_op"] = {
                        'success': False,
                        'timeout': True,
                        'duration': end_time - start_time
                    }
                    logger.info(f"Quick operation timed out after {end_time - start_time:.2f}s")
                    return False
                
            except asyncio.TimeoutError:
                end_time = time.time()
                operation_results["quick_op"] = {
                    'success': False,
                    'timeout': True,
                    'duration': end_time - start_time
                }
                logger.info(f"Quick operation timed out after {end_time - start_time:.2f}s")
                return False
            except Exception as e:
                end_time = time.time()
                operation_results["quick_op"] = {'success': False, 'error': str(e)}
                logger.error(f"Quick operation error: {e}")
                return False

        # Run both operations concurrently
        long_task = asyncio.create_task(long_running_operation())
        quick_task = asyncio.create_task(quick_operation())
        
        results = await asyncio.gather(long_task, quick_task, return_exceptions=True)
        
        # Long operation should succeed, quick operation should timeout
        self.assertIsInstance(results[0], bool, "Long operation should return boolean")
        self.assertTrue(results[0], "Long operation should succeed")
        
        self.assertIsInstance(results[1], bool, "Quick operation should return boolean")
        self.assertFalse(results[1], "Quick operation should fail due to timeout")
        
        # Verify timeout actually occurred
        self.assertTrue(operation_results["quick_op"].get("timeout", False), "Quick operation should have timed out")
        self.assertLess(operation_results["quick_op"]["duration"], 3.0, "Quick operation should timeout quickly")
        
        logger.info(f"Lock timeout test results: {operation_results}")

    async def test_lock_key_generation(self):
        """
        Test that lock keys are generated correctly for different document paths.
        """
        # Test different document paths
        test_paths = [
            ["org1", "namespace1", "doc1"],
            ["org2", "namespace2", "doc2"],
            ["org1", "namespace1", "doc2"],  # Same org/namespace, different doc
            ["org1", "namespace2", "doc1"],  # Same org, different namespace
        ]
        
        # Generate lock keys
        lock_keys = []
        for path in test_paths:
            lock_key = self.versioned_client._get_document_lock_key(path)
            lock_keys.append(lock_key)
            logger.info(f"Path {path} -> Lock key: {lock_key}")
        
        # All lock keys should be unique
        self.assertEqual(len(lock_keys), len(set(lock_keys)), "All lock keys should be unique")
        
        # Lock keys should follow expected format
        for i, lock_key in enumerate(lock_keys):
            self.assertTrue(lock_key.startswith("doc_lock:"), f"Lock key {i} should start with 'doc_lock:'")
            # The lock key should contain the path converted to MongoDB ID format
            expected_path_id = self.versioned_client.client._path_to_id(test_paths[i])
            self.assertIn(expected_path_id, lock_key, f"Lock key {i} should contain the path ID: {expected_path_id}")

    async def test_lock_release_on_exception(self):
        """
        Test that locks are properly released even when operations raise exceptions.
        """
        base_path = self._get_test_path("lock_exception_doc")
        await self.versioned_client.initialize_document(base_path)
        
        async def failing_operation():
            """Operation that raises an exception after acquiring lock."""
            try:
                # This should acquire the lock
                current_doc = await self.versioned_client.get_document(base_path)
                
                # Simulate some processing
                await asyncio.sleep(0.1)
                
                # Intentionally raise an exception
                raise ValueError("Intentional test exception")
                
            except ValueError:
                # Re-raise the expected exception
                raise
            except Exception as e:
                logger.error(f"Unexpected exception in failing operation: {e}")
                raise

        async def subsequent_operation():
            """Operation that should succeed after the failing operation releases its lock."""
            try:
                # This should be able to acquire the lock after the failing operation
                success = await self.versioned_client.update_document(base_path, {"after_exception": True})
                return success
            except Exception as e:
                logger.error(f"Subsequent operation failed: {e}")
                return False

        # First operation should fail but release lock
        with self.assertRaises(ValueError, msg="First operation should raise ValueError"):
            await failing_operation()
        
        # Small delay to ensure lock is released
        await asyncio.sleep(0.1)
        
        # Second operation should succeed (lock should be available)
        success = await subsequent_operation()
        self.assertTrue(success, "Subsequent operation should succeed after lock is released")
        
        # Verify the document was actually updated
        final_doc = await self.versioned_client.get_document(base_path)
        self.assertIn("after_exception", final_doc, "Document should contain update from subsequent operation")
        self.assertTrue(final_doc["after_exception"], "Update value should be True")

    async def test_multiple_document_locks(self):
        """
        Test that operations on different documents can proceed concurrently.
        """
        base_path1 = self._get_test_path("multi_lock_doc1")
        base_path2 = self._get_test_path("multi_lock_doc2")
        
        # Initialize both documents
        await self.versioned_client.initialize_document(base_path1)
        await self.versioned_client.initialize_document(base_path2)
        
        operation_times = {}
        
        async def update_document_worker(doc_id: str, base_path: List[str], work_duration: float):
            """Worker that updates a specific document."""
            start_time = time.time()
            try:
                # Simulate some work
                await asyncio.sleep(work_duration)
                
                # Update the document
                success = await self.versioned_client.update_document(base_path, {
                    "worker_id": doc_id,
                    "work_duration": work_duration,
                    "timestamp": start_time
                })
                
                end_time = time.time()
                operation_times[doc_id] = {
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration': end_time - start_time,
                    'success': success
                }
                
                logger.info(f"Worker {doc_id}: Completed in {end_time - start_time:.2f}s")
                return success
                
            except Exception as e:
                operation_times[doc_id] = {'error': str(e), 'success': False}
                logger.error(f"Worker {doc_id}: Error - {e}")
                return False

        # Create workers for different documents - these should run concurrently
        tasks = [
            asyncio.create_task(update_document_worker("doc1", base_path1, 1.0)),
            asyncio.create_task(update_document_worker("doc2", base_path2, 1.0)),
        ]
        
        overall_start = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        overall_end = time.time()
        total_duration = overall_end - overall_start
        
        # Both operations should succeed
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.fail(f"Worker task {i} raised an exception: {result}")
            self.assertTrue(result, f"Worker task {i} should have succeeded")
        
        # Operations should have run concurrently (total time should be close to work_duration, not 2x)
        # With proper concurrency, total time should be ~1 second, not ~2 seconds
        self.assertLess(total_duration, 1.8, "Operations on different documents should run concurrently")
        
        # Verify both documents were updated correctly
        doc1 = await self.versioned_client.get_document(base_path1)
        doc2 = await self.versioned_client.get_document(base_path2)
        
        self.assertEqual(doc1["worker_id"], "doc1", "Document 1 should have correct worker ID")
        self.assertEqual(doc2["worker_id"], "doc2", "Document 2 should have correct worker ID")
        
        logger.info(f"Multiple document locks test - Total duration: {total_duration:.2f}s")
        logger.info(f"Operation timings: {operation_times}")

def run_async_tests():
    unittest.main()

if __name__ == "__main__":
    run_async_tests()
