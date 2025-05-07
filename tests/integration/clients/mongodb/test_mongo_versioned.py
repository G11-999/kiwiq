import unittest
import asyncio
import uuid
import logging
from typing import Dict, Any, List, Optional
from bson import ObjectId
import copy

# Import the clients
from mongo_client import AsyncMongoDBClient, AsyncMongoVersionedClient
import jsonpatch
from global_config.logger import get_logger
from jsonschema.exceptions import ValidationError

logger = get_logger(__name__)

class TestMongoVersionedClient(unittest.IsolatedAsyncioTestCase):
    """Comprehensive test case for the AsyncMongoVersionedClient."""

    client: AsyncMongoDBClient
    versioned_client: AsyncMongoVersionedClient
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
            self.fail("Failed to set up underlying MongoDB client and indexes.")
        
        # Verify connection with ping
        is_connected = await self.client.ping()
        if not is_connected:
            await self.client.close()
            self.fail("Could not connect to MongoDB. Check connection URI and server status.")
            
        # Initialize the versioned client
        self.versioned_client = AsyncMongoVersionedClient(
            client=self.client,
            segment_names=self.base_segment_names, # Pass only the base segments
            return_timestamp_metadata=False
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

def run_async_tests():
    unittest.main()

if __name__ == "__main__":
    run_async_tests()
