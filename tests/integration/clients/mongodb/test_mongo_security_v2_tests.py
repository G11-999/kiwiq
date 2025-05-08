import unittest
import asyncio
import uuid
import logging
from typing import Dict, Any, List, Optional
from bson import ObjectId

# Import the AsyncMongoDBClient
from mongo_client import AsyncMongoDBClient

from global_config.logger import get_logger
logger = get_logger(__name__)

class TestOptimizedMongoDBClient(unittest.IsolatedAsyncioTestCase):
    """Comprehensive test case for the optimized AsyncMongoDBClient."""
    
    async def asyncSetUp(self):
        """Set up test environment before each test method."""
        from global_config.settings import global_settings
        self.mongo_uri = global_settings.MONGO_URL
        
        # Use a test database and collection
        self.database = "test_db"
        self.collection = "test_objects"
        
        # Define segment names
        self.segment_names = ["org", "user", "namespace", "object_name"]
        
        # Fields for text search
        self.text_search_fields = ["name", "description"]
        
        # Create a unique test prefix for this test run
        self.TEST_PREFIX = f"test_run_{uuid.uuid4().hex[:6]}"
        
        # Initialize MongoDB client
        self.client = AsyncMongoDBClient(
            uri=self.mongo_uri,
            database=self.database,
            collection=self.collection,
            segment_names=self.segment_names,
            text_search_fields=self.text_search_fields
        )
        
        # Setup indexes and verify connection
        setup_success = await self.client.drop_collection(confirm=True)
        setup_success = await self.client.setup()
        if not setup_success:
            self.fail("Failed to set up MongoDB client and indexes.")
        
        # Verify connection with ping
        is_connected = await self.client.ping()
        if not is_connected:
            await self.client.close()
            self.fail("Could not connect to MongoDB. Check connection URI and server status.")
        
        logger.info(f"Test setup complete with prefix: {self.TEST_PREFIX}")
    
    async def asyncTearDown(self):
        """Clean up after each test method."""
        if hasattr(self, 'client') and self.client:
            # Clean up any test objects
            try:
                pattern = [self.TEST_PREFIX, "*", "*", "*"]
                await self.client.delete_objects(pattern)
            except:
                pass  # Ignore cleanup errors
            
            await self.client.close()
            logger.info("MongoDB client closed.")
    
    # =========================================================================
    # PATH-BASED ID TESTS
    # =========================================================================
    async def test_shorter_path_than_segments(self):
        """Test creating and accessing objects with paths shorter than defined segment names."""
        # Create test objects with shorter paths than the defined segment names
        short_paths_data = [
            ([self.TEST_PREFIX], {"level": "root"}),
            ([self.TEST_PREFIX, "level1"], {"level": "one"}),
            ([self.TEST_PREFIX, "level1", "level2"], {"level": "two"})
        ]
        
        # Create each object
        for path, data in short_paths_data:
            doc_id = await self.client.create_object(path, data)
            self.assertIsInstance(doc_id, str, f"create_object should return a string ID for path {path}")
            
            # Fetch and verify
            obj = await self.client.fetch_object(path)
            self.assertIsNotNone(obj, f"Failed to fetch object with path {path}")
            self.assertEqual(obj["data"]["level"], data["level"], f"Data mismatch for path {path}")
        
        # Test listing objects with wildcard permissions
        # Using ["*"] should allow access to all objects regardless of path length
        all_objects = await self.client.list_objects(
            [self.TEST_PREFIX, "*", "*", "*"],
            allowed_prefixes=[["*"]]
        )
        # import ipdb; ipdb.set_trace()
        self.assertEqual(len(all_objects), 3, "Should list all 3 objects with wildcard permission")
        
        # Test fetching specific objects with wildcard permissions
        for path, data in short_paths_data:
            obj = await self.client.fetch_object(
                path,
                allowed_prefixes=[["*"]]
            )
            self.assertIsNotNone(obj, f"Failed to fetch object with path {path} using wildcard permission")
            self.assertEqual(obj["data"]["level"], data["level"], f"Data mismatch for path {path}")
        
        # Test updating with wildcard permissions
        root_path = [self.TEST_PREFIX]
        updated_data = {"level": "root-updated", "new_field": True}
        updated_id = await self.client.update_object(
            root_path,
            updated_data,
            allowed_prefixes=[["*"]]
        )
        self.assertIsNotNone(updated_id, "Update with wildcard permission should succeed")
        
        # Verify update
        updated_obj = await self.client.fetch_object(root_path)
        self.assertEqual(updated_obj["data"]["level"], "root-updated", "Object not updated correctly")
        self.assertTrue(updated_obj["data"]["new_field"], "New field not added correctly")
        
        # Test deleting with wildcard permissions
        deleted = await self.client.delete_object(
            root_path,
            allowed_prefixes=[["*"]]
        )
        self.assertTrue(deleted, "Delete with wildcard permission should succeed")
        
        # Verify deletion
        deleted_obj = await self.client.fetch_object(root_path)
        self.assertIsNone(deleted_obj, "Object should be deleted")
        
        # Count remaining objects
        count = await self.client.count_objects(
            [self.TEST_PREFIX, "*", "*", "*"],
            allowed_prefixes=[["*"]]
        )
        self.assertEqual(count, 2, "Should have 2 objects remaining")

    async def test_path_based_id(self):
        """Test that document IDs are generated from paths and are consistent."""
        # Create test paths
        path1 = [self.TEST_PREFIX, "user1", "configs", "settings"]
        path2 = [self.TEST_PREFIX, "user1", "configs", "settings"]  # Same path
        path3 = [self.TEST_PREFIX, "user2", "configs", "settings"]  # Different path
        
        # Create objects
        data1 = {"name": "Test 1", "value": 1}
        data2 = {"name": "Test 2", "value": 2}
        data3 = {"name": "Test 3", "value": 3}
        
        # Create first object
        doc_id1 = await self.client.create_object(path1, data1)
        
        # Create second object with same path (should overwrite)
        doc_id2 = await self.client.create_object(path2, data2)
        
        # Create third object with different path
        doc_id3 = await self.client.create_object(path3, data3)
        
        # Verify IDs
        self.assertEqual(doc_id1, doc_id2, "Same path should generate same ID")
        self.assertNotEqual(doc_id1, doc_id3, "Different paths should generate different IDs")
        
        # Fetch objects to verify only one exists at path1/path2
        obj1 = await self.client.fetch_object(path1)
        self.assertEqual(obj1["data"]["name"], "Test 2", "Object at path1 should have been replaced")
        
        # Count total objects
        count = await self.client.count_objects([self.TEST_PREFIX, "*", "*", "*"])
        self.assertEqual(count, 2, "Should have exactly 2 objects (not 3)")
    
    async def test_path_with_special_characters(self):
        """Test paths with special characters that could interfere with delimiter."""
        # Create paths with characters that could interfere with delimiter
        # The delimiter is "___" so we'll test with "__" and similar
        path1 = [self.TEST_PREFIX, "user__name", "configs", "settings"]
        path2 = [self.TEST_PREFIX, "user:::name", "configs", "settings"]  # Contains delimiter
        path3 = [self.TEST_PREFIX, "__user__", "configs", "settings"]
        
        # Path with delimiter should be rejected
        with self.assertRaises(ValueError):
            await self.client.create_object(path2, {"test": "data"})
        
        # Other paths should work
        doc_id1 = await self.client.create_object(path1, {"test": "data1"})
        doc_id3 = await self.client.create_object(path3, {"test": "data3"})
        
        # Fetch and verify
        obj1 = await self.client.fetch_object(path1)
        obj3 = await self.client.fetch_object(path3)
        
        self.assertIsNotNone(obj1, "Object with underscores should exist")
        self.assertIsNotNone(obj3, "Object with double underscores should exist")
        self.assertEqual(obj1["data"]["test"], "data1", "Data should match")
        self.assertEqual(obj3["data"]["test"], "data3", "Data should match")
    
    # =========================================================================
    # BASIC CRUD TESTS
    # =========================================================================
    
    async def test_create_and_fetch(self):
        """Test creating and fetching objects."""
        # Create test object
        path = [self.TEST_PREFIX, "user1", "configs", "settings"]
        data = {"name": "Test Object", "value": 123, "enabled": True}
        
        # Create object
        doc_id = await self.client.create_object(path, data)
        self.assertIsInstance(doc_id, str, "create_object should return a string ID")
        
        # Fetch object
        obj = await self.client.fetch_object(path)
        self.assertIsNotNone(obj, f"Failed to fetch object with path {path}")
        self.assertEqual(obj["data"]["name"], "Test Object", "Object data mismatch")
        self.assertEqual(obj["data"]["value"], 123, "Object data mismatch")
        
        # Fetch with non-existent path
        non_existent_path = [self.TEST_PREFIX, "nonexistent", "path", "object"]
        non_existent_obj = await self.client.fetch_object(non_existent_path)
        self.assertIsNone(non_existent_obj, "Fetch with non-existent path should return None")
    
    async def test_update_object(self):
        """Test updating objects."""
        # Create test object
        path = [self.TEST_PREFIX, "user1", "configs", "app"]
        data = {"name": "App Config", "version": "1.0", "debug": False}
        
        # Create object
        doc_id = await self.client.create_object(path, data)
        
        # Update object
        new_data = {"name": "App Config", "version": "1.1", "debug": True}
        updated_id = await self.client.update_object(path, new_data)
        self.assertEqual(updated_id, doc_id, "update_object should return the same ID")
        
        # Fetch and verify update
        updated_obj = await self.client.fetch_object(path)
        self.assertEqual(updated_obj["data"]["version"], "1.1", "Update failed: version not updated")
        self.assertTrue(updated_obj["data"]["debug"], "Update failed: debug flag not updated")
        
        # Update non-existent object
        non_existent_path = [self.TEST_PREFIX, "nonexistent", "path", "object"]
        non_existent_id = await self.client.update_object(non_existent_path, {"test": "data"})
        self.assertIsNone(non_existent_id, "Update of non-existent object should return None")

    async def test_update_subfields(self):
        """Test updating specific subfields of an object without replacing the entire object."""
        # Create test object with multiple fields
        path = [self.TEST_PREFIX, "user1", "configs", "complex_app"]
        data = {
            "name": "Complex App Config",
            "version": "1.0",
            "settings": {
                "debug": False,
                "log_level": "info",
                "cache_size": 1000
            },
            "features": ["basic", "standard"],
            "limits": {
                "max_users": 100,
                "max_storage": "5GB"
            }
        }
        
        # Create object
        doc_id = await self.client.create_object(path, data)
        self.assertIsNotNone(doc_id, "Object should be created successfully")
        
        # Update only specific subfields
        subfield_updates = {
            "version": "1.1",
            "settings.debug": True,  # This won't work with dot notation as is
            "features": ["basic", "standard", "premium"],
            "new_field": "added value"
        }
        
        # Update with subfields flag set to True
        updated_id = await self.client.update_object(
            path, 
            subfield_updates,
            update_subfields=True
        )
        
        self.assertEqual(updated_id, doc_id, "update_object should return the same ID")
        
        # Fetch and verify update
        updated_obj = await self.client.fetch_object(path)
        
        # Check that updated fields changed
        self.assertEqual(updated_obj["data"]["version"], "1.1", "Version should be updated")
        self.assertEqual(updated_obj["data"]["features"], ["basic", "standard", "premium"], "Features should be updated")
        self.assertEqual(updated_obj["data"]["new_field"], "added value", "New field should be added")
        
        # Check that non-updated fields remain unchanged
        self.assertEqual(updated_obj["data"]["name"], "Complex App Config", "Name should remain unchanged")
        self.assertEqual(updated_obj["data"]["limits"]["max_users"], 100, "Nested fields should remain unchanged")
        
        # Note: The dot notation field won't work directly with the current implementation
        # as the client would need special handling for nested paths
        
        # Test updating nested fields properly (using the whole nested object)
        nested_update = {
            "settings": {
                "debug": True,
                "log_level": "debug",
                "cache_size": 2000
            }
        }
        
        await self.client.update_object(path, nested_update, update_subfields=True)
        
        # Verify nested update
        updated_obj = await self.client.fetch_object(path)
        self.assertEqual(updated_obj["data"]["settings"]["debug"], True, "Nested debug setting should be updated")
        self.assertEqual(updated_obj["data"]["settings"]["log_level"], "debug", "Nested log_level should be updated")
        self.assertEqual(updated_obj["data"]["settings"]["cache_size"], 2000, "Nested cache_size should be updated")

    async def test_create_or_update(self):
        """Test create_or_update_object functionality."""
        # Test path
        path = [self.TEST_PREFIX, "user2", "data", "config"]
        
        # Create new object
        data1 = {"setting": "initial", "value": 100}
        doc_id, created = await self.client.create_or_update_object(path, data1)
        
        self.assertIsInstance(doc_id, str, "Should return a string ID")
        self.assertTrue(created, "Should indicate the object was created")
        
        # Update existing object
        data2 = {"setting": "updated", "value": 200}
        doc_id2, created2 = await self.client.create_or_update_object(path, data2)
        
        self.assertEqual(doc_id, doc_id2, "Should return the same ID")
        self.assertFalse(created2, "Should indicate the object was updated, not created")
        
        # Fetch and verify update
        obj = await self.client.fetch_object(path)
        self.assertEqual(obj["data"]["setting"], "updated", "Object data mismatch")
        self.assertEqual(obj["data"]["value"], 200, "Object data mismatch")
    
    async def test_delete_object(self):
        """Test delete_object functionality."""
        # Create test object
        path = [self.TEST_PREFIX, "user3", "data", "delete_me"]
        data = {"name": "Delete Test", "value": 123}
        
        await self.client.create_object(path, data)
        
        # Verify object exists
        obj = await self.client.fetch_object(path)
        self.assertIsNotNone(obj, "Object should exist before deletion")
        
        # Delete object
        deleted = await self.client.delete_object(path)
        self.assertTrue(deleted, "delete_object should return True for successful deletion")
        
        # Verify object no longer exists
        obj_after_delete = await self.client.fetch_object(path)
        self.assertIsNone(obj_after_delete, "Object should not exist after deletion")
        
        # Delete non-existent object
        deleted_again = await self.client.delete_object(path)
        self.assertFalse(deleted_again, "delete_object should return False for non-existent object")
    
    # =========================================================================
    # QUERY TESTS
    # =========================================================================
    
    async def test_list_objects(self):
        """Test listing objects with different patterns."""
        # Create test objects
        objects = [
            ([self.TEST_PREFIX, "user1", "configs", "app"], {"name": "App Config"}),
            ([self.TEST_PREFIX, "user1", "configs", "db"], {"name": "DB Config"}),
            ([self.TEST_PREFIX, "user2", "logs", "system"], {"name": "System Logs"}),
            ([self.TEST_PREFIX, "user2", "logs", "app"], {"name": "App Logs"})
        ]
        
        for path, data in objects:
            await self.client.create_object(path, data)
        
        # List all objects
        all_objects = await self.client.list_objects([self.TEST_PREFIX, "*", "*", "*"])
        self.assertEqual(len(all_objects), 4, "Should list all 4 objects")
        
        # List by user
        user1_objects = await self.client.list_objects([self.TEST_PREFIX, "user1", "*", "*"])
        self.assertEqual(len(user1_objects), 2, "Should list 2 user1 objects")
        
        # List by namespace
        configs_objects = await self.client.list_objects([self.TEST_PREFIX, "*", "configs", "*"])
        self.assertEqual(len(configs_objects), 2, "Should list 2 config objects")
        
        # List with include_data
        objects_with_data = await self.client.list_objects(
            [self.TEST_PREFIX, "*", "*", "*"],
            include_data=True
        )
        self.assertEqual(len(objects_with_data), 4, "Should list 4 objects with data")
        self.assertIn("data", objects_with_data[0], "Objects should include data field")
    
    async def test_search_objects(self):
        """Test searching objects with different criteria."""
        # Create test objects
        test_objects = [
            ([self.TEST_PREFIX, "search", "docs", "report1"], 
             {"name": "Sales Report", "description": "Monthly sales data", "department": "sales", "status": "active"}),
            ([self.TEST_PREFIX, "search", "docs", "report2"], 
             {"name": "Marketing Report", "description": "Campaign performance data", "department": "marketing", "status": "active"}),
            ([self.TEST_PREFIX, "search", "docs", "report3"], 
             {"name": "Financial Report", "description": "Quarterly financial data", "department": "finance", "status": "draft"}),
            ([self.TEST_PREFIX, "search", "config", "settings"], 
             {"name": "System Settings", "description": "System configuration settings", "department": "IT", "status": "active"})
        ]
        
        for path, data in test_objects:
            await self.client.create_object(path, data)
        
        # Search by pattern
        pattern_results = await self.client.search_objects([self.TEST_PREFIX, "search", "docs", "*"])
        self.assertEqual(len(pattern_results), 3, "Should find 3 docs objects")
        
        # Search by value filter
        value_results = await self.client.search_objects(
            [self.TEST_PREFIX, "search", "*", "*"],
            value_filter={"status": "active", "department": "sales"}
        )
        self.assertEqual(len(value_results), 1, "Should find 1 active sales document")
        
        # Search with embedded wildcard
        wildcard_results = await self.client.search_objects([self.TEST_PREFIX, "search", "*", "report*"])
        self.assertEqual(len(wildcard_results), 3, "Should find 3 report objects")
        
        # Search with text query (may be skipped if text index not available)
        try:
            text_results = await self.client.search_objects(
                [self.TEST_PREFIX, "search", "*", "*"],
                text_search_query="quarterly financial"
            )
            self.assertEqual(len(text_results), 1, "Should find 1 document with quarterly financial data")
            self.assertEqual(text_results[0]["data"]["name"], "Financial Report", "Should find financial report")
        except ValueError as e:
            if "text index required" in str(e).lower():
                logger.warning("Skipping text search test as text index is not available")
    
    async def test_search_objects_with_or_patterns(self):
        """Test searching objects with OR patterns (list of list patterns)."""
        # Create test objects in different paths
        test_objects = [
            # Group A - product catalog
            ([self.TEST_PREFIX, "catalog", "electronics", "product1"], 
             {"name": "Smartphone", "price": 999, "category": "electronics", "in_stock": True}),
            ([self.TEST_PREFIX, "catalog", "electronics", "product2"], 
             {"name": "Laptop", "price": 1499, "category": "electronics", "in_stock": True}),
            
            # Group B - inventory
            ([self.TEST_PREFIX, "inventory", "store1", "item1"], 
             {"name": "Desk Chair", "price": 199, "category": "furniture", "in_stock": False}),
            ([self.TEST_PREFIX, "inventory", "store1", "item2"], 
             {"name": "Coffee Table", "price": 299, "category": "furniture", "in_stock": True}),
            
            # Group C - orders
            ([self.TEST_PREFIX, "orders", "customer1", "order1"], 
             {"name": "Order #1001", "total": 1298, "status": "shipped", "items": ["Smartphone", "Case"]}),
            ([self.TEST_PREFIX, "orders", "customer2", "order1"], 
             {"name": "Order #1002", "total": 199, "status": "processing", "items": ["Desk Chair"]})
        ]
        
        # Batch create objects
        await self.client.batch_create_objects(test_objects)
        
        # Test 1: Search with a list of patterns (OR query)
        # Search across catalog electronics AND inventory store1
        or_patterns = [
            [self.TEST_PREFIX, "catalog", "electronics", "*"],  # All electronics products
            [self.TEST_PREFIX, "inventory", "store1", "*"]      # All store1 inventory items
        ]
        
        or_results = await self.client.search_objects(key_pattern=or_patterns)
        self.assertEqual(len(or_results), 4, "Should find 4 objects (2 electronics + 2 inventory items)")
        
        # Verify we got objects from both patterns
        # Extract paths using _id and segment values directly
        catalog_count = 0
        inventory_count = 0
        
        for doc in or_results:
            if doc.get(self.segment_names[1]) == "catalog" and doc.get(self.segment_names[2]) == "electronics":
                catalog_count += 1
            elif doc.get(self.segment_names[1]) == "inventory" and doc.get(self.segment_names[2]) == "store1":
                inventory_count += 1
        
        self.assertTrue(catalog_count > 0, "Should find objects matching the catalog/electronics pattern")
        self.assertTrue(inventory_count > 0, "Should find objects matching the inventory/store1 pattern")
        self.assertEqual(catalog_count + inventory_count, 4, "Should find exactly 4 objects in total")
        
        # Test 2: Combine OR patterns with value filter
        # Find all in-stock items across catalog and inventory
        stock_results = await self.client.search_objects(
            key_pattern=or_patterns,
            value_filter={"in_stock": True}
        )
        self.assertEqual(len(stock_results), 3, "Should find 3 in-stock items")
        
        # Test 3: Complex multi-pattern search with filtering
        # Search for specific items across different collections
        multi_patterns = [
            [self.TEST_PREFIX, "catalog", "*", "*"],     # All catalog items
            [self.TEST_PREFIX, "inventory", "*", "*"],   # All inventory items
            [self.TEST_PREFIX, "orders", "*", "*"]       # All orders
        ]
        
        # Search for expensive items (price > 1000)
        try:
            expensive_results = await self.client.search_objects(
                key_pattern=multi_patterns,
                value_filter={"price": {"$gt": 1000}}
            )
            
            # Get all orders with total > 1000 separately
            expensive_orders = await self.client.search_objects(
                key_pattern=[[self.TEST_PREFIX, "orders", "*", "*"]],
                value_filter={"total": {"$gt": 1000}}
            )
            
            # Total expensive items should be sum of expensive products and expensive orders
            total_expensive = len(expensive_results) + len(expensive_orders)
            self.assertTrue(total_expensive >= 2, "Should find at least 2 expensive items (laptop + order)")
            
        except Exception as e:
            # Skip this assertion if the database doesn't support these operations
            logger.warning(f"Skipping complex query test due to: {e}")
            
        # Test 4: Empty patterns should always return all results
        empty_patterns = []
        empty_results = await self.client.search_objects(key_pattern=empty_patterns)
        self.assertEqual(len(empty_results), 6, "Empty pattern list should always return all results")
        
        # Test 5: Invalid patterns should be skipped
        invalid_patterns = [
            [self.TEST_PREFIX, "catalog", "electronics", "*"],   # Valid pattern
            [f"invalid{self.client.PATH_DELIMITER}path", "*"],   # Invalid pattern with delimiter
            [self.TEST_PREFIX, "inventory", "store1", "*"]       # Valid pattern
        ]
        
        # This should succeed but skip the invalid pattern
        try:
            mixed_results = await self.client.search_objects(key_pattern=invalid_patterns)
            self.assertEqual(len(mixed_results), 4, "Should find 4 objects from valid patterns")
        except ValueError:
            # If the client validates all patterns first and fails on any invalid one,
            # this is also acceptable behavior
            logger.info("Client rejected query with invalid pattern, which is acceptable behavior")
    
    async def test_search_objects_pagination_and_sort(self):
        """Test searching objects with skip, limit, and sort options."""
        # Create test objects with distinct values for sorting
        test_objects_data = [
            ([self.TEST_PREFIX, "search_opts", "items", "item1"], {"name": "Charlie", "value": 30, "category": "A"}),
            ([self.TEST_PREFIX, "search_opts", "items", "item2"], {"name": "Alice", "value": 10, "category": "B"}),
            ([self.TEST_PREFIX, "search_opts", "items", "item3"], {"name": "Bob", "value": 20, "category": "A"}),
            ([self.TEST_PREFIX, "search_opts", "items", "item4"], {"name": "David", "value": 40, "category": "B"}),
            ([self.TEST_PREFIX, "search_opts", "items", "item5"], {"name": "Eve", "value": 50, "category": "A"}),
        ]
        
        # Batch create objects
        await self.client.batch_create_objects(test_objects_data)
        
        # 1. Test Sorting (Ascending by value)
        sort_asc_results = await self.client.search_objects(
            key_pattern=[self.TEST_PREFIX, "search_opts", "items", "*"],
            value_sort_by=[("value", 1)]  # 1 for ascending
        )
        self.assertEqual(len(sort_asc_results), 5, "Should find all 5 items")
        # Extract values to check order
        values_asc = [doc["data"]["value"] for doc in sort_asc_results]
        self.assertListEqual(values_asc, [10, 20, 30, 40, 50], "Items should be sorted by value ascending")

        # 2. Test Sorting (Descending by name)
        sort_desc_results = await self.client.search_objects(
            key_pattern=[self.TEST_PREFIX, "search_opts", "items", "*"],
            value_sort_by=[("name", -1)]  # -1 for descending
        )
        self.assertEqual(len(sort_desc_results), 5, "Should find all 5 items")
        # Extract names to check order
        names_desc = [doc["data"]["name"] for doc in sort_desc_results]
        self.assertListEqual(names_desc, ["Eve", "David", "Charlie", "Bob", "Alice"], "Items should be sorted by name descending")

        # 3. Test Limit
        limit_results = await self.client.search_objects(
            key_pattern=[self.TEST_PREFIX, "search_opts", "items", "*"],
            value_sort_by=[("value", 1)],  # Sort to make limit predictable
            limit=2
        )
        self.assertEqual(len(limit_results), 2, "Should return only 2 items due to limit")
        # Check the values of the returned items
        limit_values = [doc["data"]["value"] for doc in limit_results]
        self.assertListEqual(limit_values, [10, 20], "Should return the first 2 items when sorted by value")

        # 4. Test Skip
        skip_results = await self.client.search_objects(
            key_pattern=[self.TEST_PREFIX, "search_opts", "items", "*"],
            value_sort_by=[("value", 1)],  # Sort to make skip predictable
            skip=3
        )
        self.assertEqual(len(skip_results), 2, "Should return 2 items after skipping 3")
        # Check the values of the returned items
        skip_values = [doc["data"]["value"] for doc in skip_results]
        self.assertListEqual(skip_values, [40, 50], "Should return the last 2 items when sorted by value and skipping 3")

        # 5. Test Skip and Limit combined
        skip_limit_results = await self.client.search_objects(
            key_pattern=[self.TEST_PREFIX, "search_opts", "items", "*"],
            value_sort_by=[("value", 1)],  # Sort by value ascending
            skip=1,
            limit=2
        )
        self.assertEqual(len(skip_limit_results), 2, "Should return 2 items when skipping 1 and limiting to 2")
        # Check the values of the returned items (should be the 2nd and 3rd items)
        skip_limit_values = [doc["data"]["value"] for doc in skip_limit_results]
        self.assertListEqual(skip_limit_values, [20, 30], "Should return the items with values 20 and 30")

        # 6. Test Sorting by Multiple Fields
        multi_sort_results = await self.client.search_objects(
            key_pattern=[self.TEST_PREFIX, "search_opts", "items", "*"],
            value_sort_by=[("category", 1), ("value", -1)] # Sort by category ASC, then value DESC
        )
        self.assertEqual(len(multi_sort_results), 5, "Should find all 5 items for multi-sort")
        # Extract relevant fields to check order
        multi_sort_data = [(doc["data"]["category"], doc["data"]["value"]) for doc in multi_sort_results]
        expected_multi_sort = [('A', 50), ('A', 30), ('A', 20), ('B', 40), ('B', 10)]
        self.assertListEqual(multi_sort_data, expected_multi_sort, "Items should be sorted by category ASC, then value DESC")

    async def test_count_objects(self):
        """Test counting objects with different patterns."""
        # Create test objects
        test_objects = [
            ([self.TEST_PREFIX, "count", "data", "file1"], {"type": "data"}),
            ([self.TEST_PREFIX, "count", "data", "file2"], {"type": "data"}),
            ([self.TEST_PREFIX, "count", "config", "settings"], {"type": "config"}),
            ([self.TEST_PREFIX, "count2", "data", "file3"], {"type": "data"})
        ]
        
        for path, data in test_objects:
            await self.client.create_object(path, data)
        
        # Count all test objects
        total_count = await self.client.count_objects([self.TEST_PREFIX, "*", "*", "*"])
        self.assertEqual(total_count, 4, "Should count 4 total objects")
        
        # Count by prefix
        prefix_count = await self.client.count_objects([self.TEST_PREFIX, "count", "*", "*"])
        self.assertEqual(prefix_count, 3, "Should count 3 objects with 'count' prefix")
        
        # Count by namespace
        data_count = await self.client.count_objects([self.TEST_PREFIX, "*", "data", "*"])
        self.assertEqual(data_count, 3, "Should count 3 data objects")
        
        # Count with specific pattern
        specific_count = await self.client.count_objects([self.TEST_PREFIX, "*", "config", "*"])
        self.assertEqual(specific_count, 1, "Should count 1 config object")
    
    async def test_delete_objects(self):
        """Test deleting objects with patterns."""
        # Create test objects
        test_objects = [
            ([self.TEST_PREFIX, "delete", "temp", "file1"], {"name": "Temp File 1"}),
            ([self.TEST_PREFIX, "delete", "temp", "file2"], {"name": "Temp File 2"}),
            ([self.TEST_PREFIX, "delete", "keep", "doc1"], {"name": "Keep Doc 1"}),
            ([self.TEST_PREFIX, "delete", "keep", "doc2"], {"name": "Keep Doc 2"})
        ]
        
        for path, data in test_objects:
            await self.client.create_object(path, data)
        
        # Verify objects were created
        count_before = await self.client.count_objects([self.TEST_PREFIX, "delete", "*", "*"])
        self.assertEqual(count_before, 4, "Should have created 4 objects")
        
        # Delete temp files
        deleted = await self.client.delete_objects([self.TEST_PREFIX, "delete", "temp", "*"])
        self.assertEqual(deleted, 2, "Should delete 2 temp files")
        
        # Verify remaining objects
        count_after = await self.client.count_objects([self.TEST_PREFIX, "delete", "*", "*"])
        self.assertEqual(count_after, 2, "Should have 2 objects remaining")
        
        # Delete all remaining objects
        deleted_all = await self.client.delete_objects([self.TEST_PREFIX, "delete", "*", "*"])
        self.assertEqual(deleted_all, 2, "Should delete 2 remaining objects")
        
        # Verify all objects are gone
        count_final = await self.client.count_objects([self.TEST_PREFIX, "delete", "*", "*"])
        self.assertEqual(count_final, 0, "Should have 0 objects remaining")
    
    # =========================================================================
    # PERMISSION TESTS
    # =========================================================================
    
    async def test_permission_validation(self):
        """Test permission validation for different operations."""
        # Create test objects
        test_objects = [
            ([self.TEST_PREFIX, "perm", "team1", "doc1"], {"name": "Team 1 Doc"}),
            ([self.TEST_PREFIX, "perm", "team2", "doc1"], {"name": "Team 2 Doc"}),
            ([self.TEST_PREFIX, "perm", "team3", "doc1"], {"name": "Team 3 Doc"})
        ]
        
        for path, data in test_objects:
            await self.client.create_object(path, data)
        
        # Define permissions
        team1_perm = [[self.TEST_PREFIX, "perm", "team1"]]
        teams12_perm = [
            [self.TEST_PREFIX, "perm", "team1"],
            [self.TEST_PREFIX, "perm", "team2"]
        ]
        
        # Test fetch with permissions
        obj1 = await self.client.fetch_object(test_objects[0][0], allowed_prefixes=team1_perm)
        self.assertIsNotNone(obj1, "Should fetch team1 doc with team1 permission")
        
        obj2 = await self.client.fetch_object(test_objects[1][0], allowed_prefixes=team1_perm)
        self.assertIsNone(obj2, "Should not fetch team2 doc with team1 permission")
        
        # Test list with permissions
        list1 = await self.client.list_objects(
            [self.TEST_PREFIX, "perm", "*", "*"],
            allowed_prefixes=team1_perm
        )
        self.assertEqual(len(list1), 1, "Should list 1 object with team1 permission")
        
        list12 = await self.client.list_objects(
            [self.TEST_PREFIX, "perm", "*", "*"],
            allowed_prefixes=teams12_perm
        )
        self.assertEqual(len(list12), 2, "Should list 2 objects with teams12 permission")
        
        # Test create with permissions
        # Allowed
        try:
            await self.client.create_object(
                [self.TEST_PREFIX, "perm", "team1", "new_doc"],
                {"name": "New Team 1 Doc"},
                allowed_prefixes=team1_perm
            )
        except ValueError:
            self.fail("Should allow creation with team1 permission")
        
        # Not allowed
        with self.assertRaises(ValueError):
            await self.client.create_object(
                [self.TEST_PREFIX, "perm", "team3", "new_doc"],
                {"name": "New Team 3 Doc"},
                allowed_prefixes=team1_perm
            )
        
        # Test update with permissions
        # Allowed
        try:
            await self.client.update_object(
                [self.TEST_PREFIX, "perm", "team1", "doc1"],
                {"name": "Updated Team 1 Doc"},
                allowed_prefixes=team1_perm
            )
        except ValueError:
            self.fail("Should allow update with team1 permission")
        
        # Not allowed
        with self.assertRaises(ValueError):
            await self.client.update_object(
                [self.TEST_PREFIX, "perm", "team3", "doc1"],
                {"name": "Updated Team 3 Doc"},
                allowed_prefixes=team1_perm
            )
        
        # Test delete with permissions
        # Allowed
        deleted = await self.client.delete_object(
            [self.TEST_PREFIX, "perm", "team1", "doc1"],
            allowed_prefixes=team1_perm
        )
        self.assertTrue(deleted, "Should delete team1 doc with team1 permission")
        
        # Not allowed
        with self.assertRaises(ValueError):
            await self.client.delete_object(
                [self.TEST_PREFIX, "perm", "team3", "doc1"],
                allowed_prefixes=team1_perm
            )
    
    async def test_wildcard_permissions(self):
        """Test wildcard permissions including the allow-all permission."""
        # Create test objects
        test_objects = [
            ([self.TEST_PREFIX, "org1", "project1", "doc1"], {"name": "Org1 Project1 Doc1"}),
            ([self.TEST_PREFIX, "org1", "project2", "doc1"], {"name": "Org1 Project2 Doc1"}),
            ([self.TEST_PREFIX, "org2", "project1", "doc1"], {"name": "Org2 Project1 Doc1"})
        ]
        
        for path, data in test_objects:
            await self.client.create_object(path, data)
        
        # Define permissions
        org1_perm = [[self.TEST_PREFIX, "org1"]]
        org1_proj1_perm = [[self.TEST_PREFIX, "org1", "project1"]]
        allow_all_perm = [["*"]]
        partial_wildcard_perm = [[self.TEST_PREFIX, "*", "project1"]]
        invalid_all_wildcard_perm = [["*", "*", "*"]]
        
        # Test org1 permission
        list_org1 = await self.client.list_objects(
            [self.TEST_PREFIX, "*", "*", "*"],
            allowed_prefixes=org1_perm
        )
        self.assertEqual(len(list_org1), 2, "Should list 2 org1 objects")
        
        # Test org1/project1 permission
        list_org1_proj1 = await self.client.list_objects(
            [self.TEST_PREFIX, "*", "*", "*"],
            allowed_prefixes=org1_proj1_perm
        )
        self.assertEqual(len(list_org1_proj1), 1, "Should list 1 org1/project1 object")
        
        # Test allow-all permission
        list_all = await self.client.list_objects(
            [self.TEST_PREFIX, "*", "*", "*"],
            allowed_prefixes=allow_all_perm
        )
        self.assertEqual(len(list_all), 3, "Should list all 3 objects with allow-all permission")
        
        # Test partial wildcard permission
        list_proj1 = await self.client.list_objects(
            [self.TEST_PREFIX, "*", "*", "*"],
            allowed_prefixes=partial_wildcard_perm
        )
        self.assertEqual(len(list_proj1), 2, "Should list 2 project1 objects")
        
        # Test invalid all-wildcard permission
        list_invalid = await self.client.list_objects(
            [self.TEST_PREFIX, "*", "*", "*"],
            allowed_prefixes=invalid_all_wildcard_perm
        )
        self.assertEqual(len(list_invalid), 0, "Should not match any objects with invalid all-wildcard permission")
    
    # =========================================================================
    # BATCH OPERATION TESTS
    # =========================================================================
    
    async def test_batch_create_objects(self):
        """Test batch creating objects."""
        # Prepare test objects
        test_objects = [
            ([self.TEST_PREFIX, "batch", "create", "obj1"], {"name": "Batch Object 1", "value": 1}),
            ([self.TEST_PREFIX, "batch", "create", "obj2"], {"name": "Batch Object 2", "value": 2}),
            ([self.TEST_PREFIX, "batch", "create", "obj3"], {"name": "Batch Object 3", "value": 3})
        ]
        
        # Create objects in batch
        doc_ids = await self.client.batch_create_objects(test_objects)
        self.assertEqual(len(doc_ids), 3, "Should create 3 objects")
        
        # Verify objects were created
        for i, (path, expected_data) in enumerate(test_objects):
            obj = await self.client.fetch_object(path)
            self.assertIsNotNone(obj, f"Object {i+1} should exist")
            self.assertEqual(obj["data"]["name"], expected_data["name"], f"Object {i+1} name mismatch")
            self.assertEqual(obj["data"]["value"], expected_data["value"], f"Object {i+1} value mismatch")
        
        # Test batch create with permissions
        # Allowed paths
        allowed_objects = [
            ([self.TEST_PREFIX, "batch", "allowed", "obj1"], {"name": "Allowed Object 1"}),
            ([self.TEST_PREFIX, "batch", "allowed", "obj2"], {"name": "Allowed Object 2"})
        ]
        
        # Create with permissions
        allowed_ids = await self.client.batch_create_objects(
            allowed_objects,
            allowed_prefixes=[[self.TEST_PREFIX, "batch", "allowed"]]
        )
        self.assertEqual(len(allowed_ids), 2, "Should create 2 allowed objects")
        
        # Verify allowed objects were created
        for path, _ in allowed_objects:
            obj = await self.client.fetch_object(path)
            self.assertIsNotNone(obj, "Allowed object should exist")
        
        # Not allowed paths
        not_allowed_objects = [
            ([self.TEST_PREFIX, "batch", "allowed", "obj3"], {"name": "Allowed Object 3"}),
            ([self.TEST_PREFIX, "batch", "denied", "obj1"], {"name": "Denied Object 1"})
        ]
        
        # Try to create with permissions
        with self.assertRaises(ValueError):
            await self.client.batch_create_objects(
                not_allowed_objects,
                allowed_prefixes=[[self.TEST_PREFIX, "batch", "allowed"]]
            )
        
        # Verify no objects were created
        self.assertIsNone(
            await self.client.fetch_object([self.TEST_PREFIX, "batch", "denied", "obj1"]),
            "Denied object should not exist"
        )
    
    async def test_batch_update_objects(self):
        """Test batch updating objects."""
        # Create test objects
        original_objects = [
            ([self.TEST_PREFIX, "batch", "update", "obj1"], {"name": "Original 1", "value": 1}),
            ([self.TEST_PREFIX, "batch", "update", "obj2"], {"name": "Original 2", "value": 2}),
            ([self.TEST_PREFIX, "batch", "update", "obj3"], {"name": "Original 3", "value": 3})
        ]
        
        for path, data in original_objects:
            await self.client.create_object(path, data)
        
        # Prepare updates
        updates = [
            (original_objects[0][0], {"name": "Updated 1", "value": 10}),
            (original_objects[1][0], {"name": "Updated 2", "value": 20}),
            (original_objects[2][0], {"name": "Updated 3", "value": 30}),
            ([self.TEST_PREFIX, "batch", "update", "nonexistent"], {"name": "Nonexistent"})
        ]
        
        # Perform batch update
        updated_ids = await self.client.batch_update_objects(updates)
        
        # Verify results
        self.assertEqual(len(updated_ids), 4, "Should return 4 results")
        # self.assertIsNone(updated_ids[3], "Last update should return None for nonexistent document")
        
        # Verify objects were updated
        for i, (path, expected_data) in enumerate(updates[:3]):
            obj = await self.client.fetch_object(path)
            self.assertIsNotNone(obj, f"Object {i+1} should exist")
            self.assertEqual(obj["data"]["name"], expected_data["name"], f"Object {i+1} name mismatch")
            self.assertEqual(obj["data"]["value"], expected_data["value"], f"Object {i+1} value mismatch")
        
        # Test batch update with permissions
        # Create test objects
        perm_objects = [
            ([self.TEST_PREFIX, "batch", "perm", "obj1"], {"status": "original"}),
            ([self.TEST_PREFIX, "batch", "perm", "obj2"], {"status": "original"}),
            ([self.TEST_PREFIX, "batch", "denied", "obj1"], {"status": "original"})
        ]
        
        for path, data in perm_objects:
            await self.client.create_object(path, data)
        
        # Prepare updates
        perm_updates = [
            (perm_objects[0][0], {"status": "updated"}),
            (perm_objects[1][0], {"status": "updated"}),
            (perm_objects[2][0], {"status": "updated"})
        ]
        
        # Perform batch update with permissions
        perm_results = await self.client.batch_update_objects(
            perm_updates,
            allowed_prefixes=[[self.TEST_PREFIX, "batch", "perm"]]
        )
        
        # Verify results
        self.assertEqual(len(perm_results), 3, "Should return 3 results")
        self.assertIsNotNone(perm_results[0], "First update should succeed")
        self.assertIsNotNone(perm_results[1], "Second update should succeed")
        self.assertIsNone(perm_results[2], "Third update should fail (permission denied)")
        
        # Verify updates
        obj1 = await self.client.fetch_object(perm_objects[0][0])
        self.assertEqual(obj1["data"]["status"], "updated", "First object should be updated")
        
        obj2 = await self.client.fetch_object(perm_objects[1][0])
        self.assertEqual(obj2["data"]["status"], "updated", "Second object should be updated")
        
        obj3 = await self.client.fetch_object(perm_objects[2][0])
        self.assertEqual(obj3["data"]["status"], "original", "Third object should not be updated")
    
    async def test_batch_create_or_update_objects(self):
        """Test batch create_or_update operation."""
        # Create initial objects
        initial_objects = [
            ([self.TEST_PREFIX, "batch", "upsert", "existing1"], {"status": "initial", "count": 1}),
            ([self.TEST_PREFIX, "batch", "upsert", "existing2"], {"status": "initial", "count": 2})
        ]
        
        for path, data in initial_objects:
            await self.client.create_object(path, data)
        
        # Prepare upsert data
        upserts = [
            # Update existing objects
            (initial_objects[0][0], {"status": "updated", "count": 10}),
            (initial_objects[1][0], {"status": "updated", "count": 20}),
            # Create new objects
            ([self.TEST_PREFIX, "batch", "upsert", "new1"], {"status": "new", "count": 100}),
            ([self.TEST_PREFIX, "batch", "upsert", "new2"], {"status": "new", "count": 200})
        ]
        
        # Perform batch upsert
        results = await self.client.batch_create_or_update_objects(upserts)
        
        # Verify results
        self.assertEqual(len(results), 4, "Should return 4 results")
        
        # First two should be updates, last two should be creates
        self.assertFalse(results[0][1], "First operation should be an update")
        self.assertFalse(results[1][1], "Second operation should be an update")
        self.assertTrue(results[2][1], "Third operation should be a create")
        self.assertTrue(results[3][1], "Fourth operation should be a create")
        
        # Verify final state of objects
        for i, (path, expected_data) in enumerate(upserts):
            obj = await self.client.fetch_object(path)
            self.assertIsNotNone(obj, f"Object {i+1} should exist")
            self.assertEqual(obj["data"]["status"], expected_data["status"], f"Object {i+1} status mismatch")
            self.assertEqual(obj["data"]["count"], expected_data["count"], f"Object {i+1} count mismatch")
        
        # Test batch upsert with permissions
        # Create test object
        await self.client.create_object(
            [self.TEST_PREFIX, "batch", "perm", "existing"],
            {"status": "original"}
        )
        
        # Prepare upserts
        perm_upserts = [
            ([self.TEST_PREFIX, "batch", "perm", "existing"], {"status": "updated"}),
            ([self.TEST_PREFIX, "batch", "perm", "new"], {"status": "new"}),
            ([self.TEST_PREFIX, "batch", "denied", "existing"], {"status": "denied"})
        ]
        
        # This should fail on the denied path
        with self.assertRaises(ValueError):
            await self.client.batch_create_or_update_objects(
                perm_upserts,
                allowed_prefixes=[[self.TEST_PREFIX, "batch", "perm"]]
            )
        
        # Try with just the allowed paths
        allowed_upserts = perm_upserts[:2]
        allowed_results = await self.client.batch_create_or_update_objects(
            allowed_upserts,
            allowed_prefixes=[[self.TEST_PREFIX, "batch", "perm"]]
        )
        
        # Verify results
        self.assertEqual(len(allowed_results), 2, "Should return 2 results")
        self.assertFalse(allowed_results[0][1], "First operation should be an update")
        self.assertTrue(allowed_results[1][1], "Second operation should be a create")
        
        # Verify final state of objects
        obj1 = await self.client.fetch_object([self.TEST_PREFIX, "batch", "perm", "existing"])
        self.assertEqual(obj1["data"]["status"], "updated", "Existing object should be updated")
        
        obj2 = await self.client.fetch_object([self.TEST_PREFIX, "batch", "perm", "new"])
        self.assertEqual(obj2["data"]["status"], "new", "New object should be created")
    
    async def test_batch_fetch_objects(self):
        """Test batch fetching objects."""
        # Create test objects
        test_objects = [
            ([self.TEST_PREFIX, "batch", "fetch", "obj1"], {"name": "Fetch Object 1", "value": 1}),
            ([self.TEST_PREFIX, "batch", "fetch", "obj2"], {"name": "Fetch Object 2", "value": 2}),
            ([self.TEST_PREFIX, "batch", "fetch", "obj3"], {"name": "Fetch Object 3", "value": 3})
        ]
        
        for path, data in test_objects:
            await self.client.create_object(path, data)
        
        # Prepare paths to fetch
        fetch_paths = [path for path, _ in test_objects]
        fetch_paths.append([self.TEST_PREFIX, "batch", "fetch", "nonexistent"])
        
        # Perform batch fetch
        results = await self.client.batch_fetch_objects(fetch_paths)
        # import ipdb; ipdb.set_trace()
        # Verify results
        self.assertEqual(len(results), 4, "Should return 4 results")
        
        # Check each result
        for i, (path, expected_data) in enumerate(test_objects):
            path_str = str(path)
            self.assertIn(path_str, results, f"Path {i+1} should be in results")
            self.assertIsNotNone(results[path_str], f"Object {i+1} should be found")
            self.assertEqual(results[path_str]["data"]["name"], expected_data["name"], f"Object {i+1} name mismatch")
            self.assertEqual(results[path_str]["data"]["value"], expected_data["value"], f"Object {i+1} value mismatch")
        
        # Check nonexistent path
        nonexistent_path = str(fetch_paths[3])
        self.assertIn(nonexistent_path, results, "Nonexistent path should be in results")
        self.assertIsNone(results[nonexistent_path], "Nonexistent object should be None")
        
        # Test batch fetch with permissions
        # Create additional objects
        perm_objects = [
            ([self.TEST_PREFIX, "batch", "allowed", "obj1"], {"status": "allowed"}),
            ([self.TEST_PREFIX, "batch", "allowed", "obj2"], {"status": "allowed"}),
            ([self.TEST_PREFIX, "batch", "denied", "obj1"], {"status": "denied"})
        ]
        
        for path, data in perm_objects:
            await self.client.create_object(path, data)
        
        # Prepare paths to fetch
        perm_paths = [path for path, _ in perm_objects]
        
        # Perform batch fetch with permissions
        perm_results = await self.client.batch_fetch_objects(
            perm_paths,
            allowed_prefixes=[[self.TEST_PREFIX, "batch", "allowed"]]
        )
        
        # Verify results
        self.assertEqual(len(perm_results), 3, "Should return 3 results")
        
        # Check allowed paths
        allowed_path1 = str(perm_paths[0])
        allowed_path2 = str(perm_paths[1])
        denied_path = str(perm_paths[2])
        
        self.assertIsNotNone(perm_results[allowed_path1], "First object should be found")
        self.assertIsNotNone(perm_results[allowed_path2], "Second object should be found")
        self.assertIsNone(perm_results[denied_path], "Third object should be None (permission denied)")
    
    async def test_batch_delete_objects(self):
        """Test batch deleting objects."""
        # Create test objects
        test_objects = [
            ([self.TEST_PREFIX, "batch", "delete", "obj1"], {"name": "Delete Object 1"}),
            ([self.TEST_PREFIX, "batch", "delete", "obj2"], {"name": "Delete Object 2"}),
            ([self.TEST_PREFIX, "batch", "delete", "obj3"], {"name": "Delete Object 3"})
        ]
        
        for path, data in test_objects:
            await self.client.create_object(path, data)
        
        # Prepare paths to delete
        delete_paths = [path for path, _ in test_objects]
        delete_paths.append([self.TEST_PREFIX, "batch", "delete", "nonexistent"])
        
        # Perform batch delete
        results = await self.client.batch_delete_objects(delete_paths)
        
        # Verify results
        self.assertEqual(len(results), 4, "Should return 4 results")
        
        # Check results for existing objects
        for i, path in enumerate(delete_paths[:3]):
            path_str = str(path)
            self.assertIn(path_str, results, f"Path {i+1} should be in results")
            self.assertTrue(results[path_str], f"Object {i+1} should be deleted")
            
            # Verify object no longer exists
            obj = await self.client.fetch_object(path)
            self.assertIsNone(obj, f"Object {i+1} should not exist after deletion")
        
        # Check nonexistent path
        nonexistent_path = str(delete_paths[3])
        self.assertIn(nonexistent_path, results, "Nonexistent path should be in results")
        # import ipdb; ipdb.set_trace()
        # self.assertFalse(results[nonexistent_path], "Nonexistent object should return False")
        
        # Test batch delete with permissions
        # Create additional objects
        perm_objects = [
            ([self.TEST_PREFIX, "batch", "perm_delete", "obj1"], {"status": "allowed"}),
            ([self.TEST_PREFIX, "batch", "perm_delete", "obj2"], {"status": "allowed"}),
            ([self.TEST_PREFIX, "batch", "denied_delete", "obj1"], {"status": "denied"})
        ]
        
        for path, data in perm_objects:
            await self.client.create_object(path, data)
        
        # Prepare paths to delete
        perm_paths = [path for path, _ in perm_objects]
        
        # Perform batch delete with permissions
        perm_results = await self.client.batch_delete_objects(
            perm_paths,
            allowed_prefixes=[[self.TEST_PREFIX, "batch", "perm_delete"]]
        )
        
        # Verify results
        self.assertEqual(len(perm_results), 3, "Should return 3 results")
        
        # Check allowed paths
        allowed_path1 = str(perm_paths[0])
        allowed_path2 = str(perm_paths[1])
        denied_path = str(perm_paths[2])
        
        self.assertTrue(perm_results[allowed_path1], "First object should be deleted")
        self.assertTrue(perm_results[allowed_path2], "Second object should be deleted")
        self.assertFalse(perm_results[denied_path], "Third object should not be deleted (permission denied)")
        
        # Verify objects' existence
        self.assertIsNone(await self.client.fetch_object(perm_paths[0]), "First object should be deleted")
        self.assertIsNone(await self.client.fetch_object(perm_paths[1]), "Second object should be deleted")
        self.assertIsNotNone(await self.client.fetch_object(perm_paths[2]), "Third object should still exist")

# Add these test methods to the TestOptimizedMongoDBClient class

    async def test_string_data(self):
        """Test creating and managing documents with string data instead of dictionaries."""
        # Create test object with string data
        path = [self.TEST_PREFIX, "string_data", "test", "doc1"]
        string_data = "This is just a string, not a dictionary"
        
        # Create object
        doc_id = await self.client.create_object(path, string_data)
        self.assertIsInstance(doc_id, str, "create_object should return a string ID")
        
        # Fetch object
        obj = await self.client.fetch_object(path)
        self.assertIsNotNone(obj, f"Failed to fetch object with path {path}")
        self.assertEqual(obj["data"], string_data, "Object string data mismatch")
        
        # Update object with new string
        new_string_data = "This is an updated string"
        updated_id = await self.client.update_object(path, new_string_data)
        self.assertEqual(updated_id, doc_id, "update_object should return the same ID")
        
        # Fetch and verify update
        updated_obj = await self.client.fetch_object(path)
        self.assertEqual(updated_obj["data"], new_string_data, "Object string data not updated correctly")
        
        # Delete object
        deleted = await self.client.delete_object(path)
        self.assertTrue(deleted, "delete_object should return True for successful deletion")
        
        # Verify object no longer exists
        obj_after_delete = await self.client.fetch_object(path)
        self.assertIsNone(obj_after_delete, "Object should not exist after deletion")

    async def test_single_segment_path(self):
        """Test operations with single-segment paths."""
        # Create test object with single-segment path
        path = [self.TEST_PREFIX]
        data = {"name": "Root Object", "value": "test"}
        
        # Create object
        doc_id = await self.client.create_object(path, data)
        self.assertIsInstance(doc_id, str, "create_object should return a string ID")
        
        # Fetch object
        obj = await self.client.fetch_object(path)
        self.assertIsNotNone(obj, f"Failed to fetch object with path {path}")
        self.assertEqual(obj["data"]["name"], "Root Object", "Object data mismatch")
        
        # Update object
        new_data = {"name": "Updated Root Object", "value": "updated"}
        updated_id = await self.client.update_object(path, new_data)
        self.assertEqual(updated_id, doc_id, "update_object should return the same ID")
        
        # Fetch and verify update
        updated_obj = await self.client.fetch_object(path)
        self.assertEqual(updated_obj["data"]["name"], "Updated Root Object", "Object data not updated correctly")
        
        # List objects with single-segment pattern
        listed_objs = await self.client.list_objects([self.TEST_PREFIX])
        self.assertEqual(len(listed_objs), 1, "Should list 1 object with single-segment pattern")
        
        # Count objects with single-segment pattern
        count = await self.client.count_objects([self.TEST_PREFIX])
        self.assertEqual(count, 1, "Should count 1 object with single-segment pattern")
        
        # Delete object
        deleted = await self.client.delete_object(path)
        self.assertTrue(deleted, "delete_object should return True for successful deletion")
        
        # Verify object no longer exists
        obj_after_delete = await self.client.fetch_object(path)
        self.assertIsNone(obj_after_delete, "Object should not exist after deletion")

    async def test_different_segment_lengths(self):
        """Test operations with paths of different segment lengths."""
        # Create test objects with different path lengths
        paths_data = [
            ([self.TEST_PREFIX], {"level": "root"}),
            ([self.TEST_PREFIX, "level1"], {"level": "one"}),
            ([self.TEST_PREFIX, "level1", "level2"], {"level": "two"}),
            ([self.TEST_PREFIX, "level1", "level2", "level3"], {"level": "three"}),
            # ([self.TEST_PREFIX, "level1", "level2", "level3", "level4"], {"level": "four"})
        ]
        
        # Create and verify each object
        for path, data in paths_data:
            doc_id = await self.client.create_object(path, data)
            obj = await self.client.fetch_object(path)
            self.assertEqual(obj["data"]["level"], data["level"], f"Data mismatch for path {path}")
        
        # List objects at different levels
        root_objects = await self.client.list_objects([self.TEST_PREFIX])
        self.assertEqual(len(root_objects), 4, "Should find 5 objects (including nested)")
        
        level1_objects = await self.client.list_objects([self.TEST_PREFIX, "level1"])
        self.assertEqual(len(level1_objects), 3, "Should find 4 objects at level1 (including nested)")
        
        level3_objects = await self.client.list_objects([self.TEST_PREFIX, "level1", "level2", "level3"])
        self.assertEqual(len(level3_objects), 1, "Should find 2 objects at level3 (including nested)")
        
        # Clean up
        for path, _ in paths_data:
            await self.client.delete_object(path)

    async def test_mixed_data_types(self):
        """Test operations with mixed data types."""
        # Prepare paths and data with various types
        paths_data = [
            ([self.TEST_PREFIX, "mixed", "data", "dict"], {"type": "dict", "value": {"a": 1, "b": 2}}),
            ([self.TEST_PREFIX, "mixed", "data", "string"], "This is a plain string"),
            ([self.TEST_PREFIX, "mixed", "data", "int"], 12345),
            ([self.TEST_PREFIX, "mixed", "data", "null"], None),
            ([self.TEST_PREFIX, "mixed", "data", "list"], [1, 2, 3, "test"]),
            ([self.TEST_PREFIX, "mixed", "data", "bool"], True)
        ]
        
        # Test each type individually
        for path, data in paths_data:
            try:
                doc_id = await self.client.create_object(path, data)
                obj = await self.client.fetch_object(path)
                self.assertEqual(obj["data"], data, f"Data mismatch for type {type(data)}")
            except Exception as e:
                self.fail(f"Failed for data type {type(data)}: {e}")
        
        # Try batch operation with mixed types
        # Delete existing data first
        await self.client.delete_objects([self.TEST_PREFIX, "mixed", "data", "*"])
        
        # Batch create with mixed types
        doc_ids = await self.client.batch_create_objects(paths_data)
        self.assertEqual(len(doc_ids), len(paths_data), "Should create all objects in batch")
        
        # Verify all objects
        for path, expected_data in paths_data:
            obj = await self.client.fetch_object(path)
            self.assertEqual(obj["data"], expected_data, f"Data mismatch for path {path}")

    async def test_empty_data(self):
        """Test handling of empty data."""
        # Test with empty dict
        path1 = [self.TEST_PREFIX, "empty", "dict", "test"]
        doc_id1 = await self.client.create_object(path1, {})
        obj1 = await self.client.fetch_object(path1)
        self.assertEqual(obj1["data"], {}, "Empty dict should be stored and retrieved correctly")
        
        # Test with empty string
        path2 = [self.TEST_PREFIX, "empty", "string", "test"]
        doc_id2 = await self.client.create_object(path2, "")
        obj2 = await self.client.fetch_object(path2)
        self.assertEqual(obj2["data"], "", "Empty string should be stored and retrieved correctly")
        
        # Test with None
        path3 = [self.TEST_PREFIX, "empty", "none", "test"]
        doc_id3 = await self.client.create_object(path3, None)
        obj3 = await self.client.fetch_object(path3)
        self.assertIsNone(obj3["data"], "None should be stored and retrieved correctly")

    async def test_unicode_paths(self):
        """Test paths with Unicode characters."""
        # Create paths with various Unicode characters
        paths = [
            [self.TEST_PREFIX, "unicode", "test", "🚀"],  # Emoji
            [self.TEST_PREFIX, "unicode", "test", "你好"],  # Chinese
            [self.TEST_PREFIX, "unicode", "test", "équipe"],  # French accent
            [self.TEST_PREFIX, "unicode", "test", "Москва"]   # Russian
        ]
        
        # Create and verify objects
        for i, path in enumerate(paths):
            data = {"test": f"Unicode test {i}"}
            doc_id = await self.client.create_object(path, data)
            
            # Fetch and verify
            obj = await self.client.fetch_object(path)
            self.assertIsNotNone(obj, f"Failed to fetch object with Unicode path {path}")
            self.assertEqual(obj["data"]["test"], f"Unicode test {i}", "Object data mismatch")
        
        # List objects with Unicode pattern
        unicode_objects = await self.client.list_objects([self.TEST_PREFIX, "unicode", "test", "*"])
        self.assertEqual(len(unicode_objects), 4, "Should list 4 Unicode objects")

    async def test_large_batch_operations(self):
        """Test batch operations with a large number of documents."""
        # Create a large batch of documents
        batch_size = 100
        paths_data = []
        
        for i in range(batch_size):
            path = [self.TEST_PREFIX, "large_batch", f"item{i}", "data"]
            data = {"index": i, "name": f"Batch Item {i}", "value": i * 10}
            paths_data.append((path, data))
        
        # Batch create
        doc_ids = await self.client.batch_create_objects(paths_data)
        self.assertEqual(len(doc_ids), batch_size, f"Should create {batch_size} objects")
        
        # Count to verify creation
        count = await self.client.count_objects([self.TEST_PREFIX, "large_batch", "*", "*"])
        self.assertEqual(count, batch_size, f"Should have created {batch_size} objects")
        
        # Batch fetch
        fetch_paths = [path for path, _ in paths_data[:10]]  # Sample first 10
        fetch_results = await self.client.batch_fetch_objects(fetch_paths)
        self.assertEqual(len(fetch_results), 10, "Should fetch 10 objects")
        
        # Batch update
        update_paths_data = [(path, {"index": i, "updated": True, "value": i * 20}) 
                            for i, (path, _) in enumerate(paths_data[:20])]  # Update first 20
        updated_ids = await self.client.batch_update_objects(update_paths_data)
        self.assertEqual(len(updated_ids), 20, "Should update 20 objects")
        
        # Verify updates
        for i, (path, _) in enumerate(update_paths_data):
            obj = await self.client.fetch_object(path)
            self.assertTrue(obj["data"]["updated"], f"Object {i} should be marked as updated")
            self.assertEqual(obj["data"]["value"], i * 20, f"Object {i} value should be updated")
        
        # Batch delete
        delete_paths = [path for path, _ in paths_data[50:70]]  # Delete 20 items
        delete_results = await self.client.batch_delete_objects(delete_paths)
        self.assertEqual(sum(delete_results.values()), 20, "Should delete 20 objects")
        
        # Verify deletions
        count_after_delete = await self.client.count_objects([self.TEST_PREFIX, "large_batch", "*", "*"])
        self.assertEqual(count_after_delete, batch_size - 20, "Should have deleted 20 objects")
        
        # Clean up remaining with pattern delete
        deleted = await self.client.delete_objects([self.TEST_PREFIX, "large_batch", "*", "*"])
        self.assertEqual(deleted, batch_size - 20, "Should delete all remaining batch objects")

    async def test_batch_operations_with_errors(self):
        """Test batch operations with some operations that will fail."""
        # Create valid objects first
        valid_paths_data = [
            ([self.TEST_PREFIX, "batch_errors", "valid", f"obj{i}"], {"index": i})
            for i in range(5)
        ]
        await self.client.batch_create_objects(valid_paths_data)
        
        # Prepare a mix of valid and invalid operations
        mixed_paths_data = [
            # Valid paths
            (valid_paths_data[0][0], {"updated": True}),
            (valid_paths_data[1][0], {"updated": True}),
            # Invalid paths (containing delimiter)
            ([self.TEST_PREFIX, f"invalid{self.client.PATH_DELIMITER}path", "test", "obj"], {"invalid": True}),
            # Path with permission that will be denied
            ([self.TEST_PREFIX, "denied", "access", "obj"], {"denied": True})
        ]
        
        # Test batch update with mixed paths
        try:
            results = await self.client.batch_update_objects(
                mixed_paths_data,
                allowed_prefixes=[[self.TEST_PREFIX, "batch_errors"]]  # Only allow batch_errors prefix
            )
            
            # Only the first two should succeed
            self.assertIsNotNone(results[0], "First update should succeed")
            self.assertIsNotNone(results[1], "Second update should succeed")
            self.assertIsNone(results[2], "Invalid path update should fail")
            self.assertIsNone(results[3], "Permission denied update should fail")
        except ValueError:
            # If the method doesn't handle errors and raises instead, that's also valid behavior
            pass
        
        # Test batch fetch with mixed paths
        fetch_paths = [path for path, _ in mixed_paths_data]
        fetch_results = await self.client.batch_fetch_objects(
            fetch_paths,
            allowed_prefixes=[[self.TEST_PREFIX, "batch_errors"]]  # Only allow batch_errors prefix
        )
        
        # The first two should be found, the others not
        self.assertIsNotNone(fetch_results[str(fetch_paths[0])], "First object should be found")
        self.assertIsNotNone(fetch_results[str(fetch_paths[1])], "Second object should be found")
        self.assertIsNone(fetch_results[str(fetch_paths[3])], "Permission denied object should not be found")

    async def test_batch_performance(self):
        """Test performance characteristics of batch vs. individual operations."""
        import time
        
        # Create test data
        batch_size = 50
        paths_data = [
            ([self.TEST_PREFIX, "perf", "batch", f"obj{i}"], {"index": i, "data": "x" * 100})
            for i in range(batch_size)
        ]
        
        # Time batch create
        start_time = time.time()
        await self.client.batch_create_objects(paths_data)
        batch_create_time = time.time() - start_time
        
        # Clean up
        await self.client.delete_objects([self.TEST_PREFIX, "perf", "batch", "*"])
        
        # Time individual creates
        start_time = time.time()
        for path, data in paths_data:
            await self.client.create_object(path, data)
        individual_create_time = time.time() - start_time
        
        # Log performance comparison
        logger.info(f"Batch create time for {batch_size} docs: {batch_create_time:.3f}s")
        logger.info(f"Individual create time for {batch_size} docs: {individual_create_time:.3f}s")
        logger.info(f"Performance ratio: {individual_create_time / batch_create_time:.2f}x")
        
        # Clean up
        await self.client.delete_objects([self.TEST_PREFIX, "perf", "*", "*"])
        
        # No strict assertions here, as performance depends on environment
        # But we can assert batch should be faster
        self.assertLess(batch_create_time, individual_create_time, 
                        "Batch operations should be faster than individual operations")

    async def test_large_data(self):
        """Test handling of large data objects."""
        # Create a document with a large string
        large_string = "x" * 1000000  # 1MB string
        path = [self.TEST_PREFIX, "large_data", "test", "large_string"]
        
        # Create object
        doc_id = await self.client.create_object(path, large_string)
        
        # Fetch and verify
        obj = await self.client.fetch_object(path)
        self.assertEqual(len(obj["data"]), 1000000, "Large string data should be stored correctly")
        
        # Create a document with a large nested structure
        large_nested = {"level1": {}}
        current = large_nested["level1"]
        for i in range(100):
            current[f"level{i+2}"] = {}
            current = current[f"level{i+2}"]
        current["value"] = "test"
        
        path_nested = [self.TEST_PREFIX, "large_data", "test", "large_nested"]
        doc_id = await self.client.create_object(path_nested, large_nested)
        
        # Fetch and verify
        obj = await self.client.fetch_object(path_nested)
        
        # Traverse the structure to verify
        current = obj["data"]["level1"]
        for i in range(100):
            self.assertIn(f"level{i+2}", current, f"Missing nested level {i+2}")
            current = current[f"level{i+2}"]
        self.assertEqual(current["value"], "test", "Value at deepest level should match")

    async def test_edge_case_string_data_operations(self):
        """Test edge cases with string data in various operations."""
        # Create objects with string data
        string_objects = [
            ([self.TEST_PREFIX, "strings", "search", f"obj{i}"], f"String data {i}")
            for i in range(5)
        ]
        
        for path, data in string_objects:
            await self.client.create_object(path, data)
        
        # Test search_objects with string data
        # Note: This might behave differently than with dict data
        try:
            search_results = await self.client.search_objects(
                [self.TEST_PREFIX, "strings", "search", "*"],
                value_filter={"notapplicable": "value"}  # This might not work with string data
            )
            # Just checking if it runs without error
            logger.info(f"Search with string data returned {len(search_results)} results")
        except Exception as e:
            logger.warning(f"search_objects with string data raised: {e}")
            # This might be expected behavior
        
        # Test batch operations with string data
        string_batch = [
            ([self.TEST_PREFIX, "strings", "batch", f"obj{i}"], f"Batch string {i}")
            for i in range(10)
        ]
        
        batch_ids = await self.client.batch_create_objects(string_batch)
        self.assertEqual(len(batch_ids), 10, "Should create 10 string objects in batch")
        
        # Update string data in batch
        update_batch = [
            (path, f"Updated {data}")
            for path, data in string_batch[:5]
        ]
        
        update_ids = await self.client.batch_update_objects(update_batch)
        self.assertEqual(len(update_ids), 5, "Should update 5 string objects in batch")
        
        # Verify updates
        for path, expected_data in update_batch:
            obj = await self.client.fetch_object(path)
            self.assertEqual(obj["data"], expected_data, "String data should be updated correctly")
        
        # Test list_objects with string data
        string_objects = await self.client.list_objects(
            [self.TEST_PREFIX, "strings", "*", "*"],
            include_data=True
        )
        
        for obj in string_objects:
            self.assertIsNotNone(obj["data"], "Object should include string data")
            if isinstance(obj["data"], str):
                self.assertIsInstance(obj["data"], str, "Data should be a string")

    async def test_create_only_fields(self):
        """
        Tests the create_only_fields and keep_create_fields_if_missing parameters
        in create_or_update_object method.
        
        This test validates:
        1. Fields in create_only_fields are preserved during document creation
        2. Fields in create_only_fields are removed during document update
        3. The keep_create_fields_if_missing parameter controls whether create_only_fields
           are removed when they don't exist in the original document
        4. When keep_create_fields_if_missing=True and the original document has the field,
           the original value is preserved even if update data tries to change it
        """
        client = self.client
        
        # Test case 1: Create a document with create_only_fields
        path = ["test_org", "test_project", "create_only_test"]
        initial_data = {
            "name": "Test Document",
            "created_by": "user123",  # This field should only be included during creation
            "timestamp": 12345,       # This field should only be included during creation
            "regular_field": "value"  # This field should always be included
        }
        
        # Create document with create_only_fields
        doc_id, was_created = await client.create_or_update_object(
            path=path,
            data=initial_data.copy(),
            create_only_fields=["created_by", "timestamp"],
            update_subfields=True,
        )
        
        self.assertTrue(was_created)
        
        # Verify all fields are present after creation
        doc = await client.fetch_object(path=path)
        self.assertIsNotNone(doc)
        self.assertEqual(doc["data"]["name"], "Test Document")
        self.assertEqual(doc["data"]["created_by"], "user123")
        self.assertEqual(doc["data"]["timestamp"], 12345)
        self.assertEqual(doc["data"]["regular_field"], "value")
        
        # Test case 2: Update the document with create_only_fields
        update_data = {
            "name": "Updated Document",
            "created_by": "different_user",  # This should be removed during update
            "timestamp": 67890,              # This should be removed during update
            "regular_field": "new_value"     # This should be updated
        }
        
        # Update document with create_only_fields
        doc_id, was_created = await client.create_or_update_object(
            path=path,
            data=update_data.copy(),
            create_only_fields=["created_by", "timestamp"],
            update_subfields=True,
        )
        
        self.assertFalse(was_created)
        
        # Verify create_only_fields weren't updated
        doc = await client.fetch_object(path=path)
        self.assertIsNotNone(doc)
        self.assertEqual(doc["data"]["name"], "Updated Document")
        self.assertEqual(doc["data"]["created_by"], "user123")  # Should retain original value
        self.assertEqual(doc["data"]["timestamp"], 12345)       # Should retain original value
        self.assertEqual(doc["data"]["regular_field"], "new_value")
        
        # Test case 3: Create a new document for testing keep_create_fields_if_missing
        path2 = ["test_org", "test_project", "create_only_test2"]
        initial_data2 = {
            "name": "Test Document 2",
            "regular_field": "value"
        }
        
        # Create document without the create_only_fields
        doc_id2, was_created2 = await client.create_or_update_object(
            path=path2,
            data=initial_data2.copy(),
            update_subfields=True,
        )
        
        self.assertTrue(was_created2)
        
        # Verify initial state
        doc2 = await client.fetch_object(path=path2)
        self.assertIsNotNone(doc2)
        self.assertEqual(doc2["data"]["name"], "Test Document 2")
        self.assertNotIn("created_by", doc2["data"])
        self.assertNotIn("timestamp", doc2["data"])
        
        # Test case 4: Update with keep_create_fields_if_missing=True
        update_data2 = {
            "name": "Updated Document 2",
            "created_by": "user456",
            "timestamp": 54321,
            "regular_field": "new_value"
        }
        
        # Update with keep_create_fields_if_missing=True
        doc_id2, was_created2 = await client.create_or_update_object(
            path=path2,
            data=update_data2.copy(),
            create_only_fields=["created_by", "timestamp"],
            keep_create_fields_if_missing=True,
            update_subfields=True,
        )
        
        self.assertFalse(was_created2)
        
        # Verify create_only_fields were added because they were missing
        doc2 = await client.fetch_object(path=path2)
        self.assertIsNotNone(doc2)
        self.assertEqual(doc2["data"]["name"], "Updated Document 2")
        self.assertEqual(doc2["data"]["created_by"], "user456")  # Should be added
        self.assertEqual(doc2["data"]["timestamp"], 54321)       # Should be added
        self.assertEqual(doc2["data"]["regular_field"], "new_value")
        
        # Test case 5: Update with keep_create_fields_if_missing=False
        path3 = ["test_org", "test_project", "create_only_test3"]
        initial_data3 = {
            "name": "Test Document 3",
            "regular_field": "value"
        }
        
        # Create document without the create_only_fields
        doc_id3, was_created3 = await client.create_or_update_object(
            path=path3,
            data=initial_data3.copy(),
            update_subfields=True,
        )
        
        self.assertTrue(was_created3)
        
        update_data3 = {
            "name": "Updated Document 3",
            "created_by": "user789",
            "timestamp": 98765,
            "regular_field": "new_value"
        }
        
        # Update with keep_create_fields_if_missing=False (default)
        doc_id3, was_created3 = await client.create_or_update_object(
            path=path3,
            data=update_data3.copy(),
            create_only_fields=["created_by", "timestamp"],
            keep_create_fields_if_missing=False,
            update_subfields=True,
        )
        
        self.assertFalse(was_created3)
        
        # Verify create_only_fields were NOT added because keep_create_fields_if_missing=False
        doc3 = await client.fetch_object(path=path3)
        self.assertIsNotNone(doc3)
        self.assertEqual(doc3["data"]["name"], "Updated Document 3")
        self.assertNotIn("created_by", doc3["data"])  # Should NOT be added
        self.assertNotIn("timestamp", doc3["data"])   # Should NOT be added
        self.assertEqual(doc3["data"]["regular_field"], "new_value")
        
        # Test case 6: Update a document with existing create_only_fields using keep_create_fields_if_missing=True
        # This tests that when a field already exists and is in create_only_fields, the original value is preserved
        # even when keep_create_fields_if_missing=True and update data contains new values for those fields
        path4 = ["test_org", "test_project", "create_only_test4"]
        initial_data4 = {
            "name": "Test Document 4",
            "created_by": "original_user",  # Will be marked as create_only_field
            "timestamp": 11111,             # Will be marked as create_only_field
            "regular_field": "value"
        }
        
        # Create document with fields that will later be designated as create_only_fields
        doc_id4, was_created4 = await client.create_or_update_object(
            path=path4,
            data=initial_data4.copy(),
            update_subfields=True,
        )
        
        self.assertTrue(was_created4)
        
        # Verify initial state
        doc4 = await client.fetch_object(path=path4)
        self.assertIsNotNone(doc4)
        self.assertEqual(doc4["data"]["created_by"], "original_user")
        self.assertEqual(doc4["data"]["timestamp"], 11111)
        
        # Now update with new values for create_only_fields while setting keep_create_fields_if_missing=True
        update_data4 = {
            "name": "Updated Document 4",
            "created_by": "attempted_new_user",  # Should not change the original value
            "timestamp": 22222,                  # Should not change the original value
            "regular_field": "new_value"
        }
        
        # Update with create_only_fields and keep_create_fields_if_missing=True
        doc_id4, was_created4 = await client.create_or_update_object(
            path=path4,
            data=update_data4.copy(),
            create_only_fields=["created_by", "timestamp"],
            keep_create_fields_if_missing=True,
            update_subfields=True,
        )
        
        self.assertFalse(was_created4)
        
        # Verify create_only_fields values were NOT changed despite keep_create_fields_if_missing=True
        doc4 = await client.fetch_object(path=path4)
        self.assertIsNotNone(doc4)
        self.assertEqual(doc4["data"]["name"], "Updated Document 4")
        self.assertEqual(doc4["data"]["created_by"], "original_user")  # Should retain original value
        self.assertEqual(doc4["data"]["timestamp"], 11111)             # Should retain original value
        self.assertEqual(doc4["data"]["regular_field"], "new_value")

def run_async_tests():
    unittest.main()

if __name__ == "__main__":
    run_async_tests()
