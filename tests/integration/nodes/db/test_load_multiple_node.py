import unittest
import uuid
import asyncio
from typing import Dict, Any, Optional, List, Tuple, Type
import time # Import time for delays

# Pydantic for User mock & create_model
from pydantic import BaseModel, Field, create_model

# Node imports
from services.workflow_service.registry.nodes.db.load_multiple_customer_node import (
    LoadMultipleCustomerDataNode,
    LoadMultipleCustomerDataConfig,
    LoadMultipleCustomerDataOutput,
)
# Sibling node components might be needed for config/data setup
from services.workflow_service.registry.nodes.db.customer_data import (
    VersionConfig,
    SchemaOptions,
)
# Enum imports for config/assertions
from services.kiwi_app.workflow_app.schemas import (
    CustomerDataSortBy,
    SortOrder
)


# Context and Service imports
from services.workflow_service.services.external_context_manager import (
    ExternalContextManager,
    get_external_context_manager_with_clients
)
from services.kiwi_app.workflow_app.service_customer_data import CustomerDataService
from services.workflow_service.config.constants import (
    APPLICATION_CONTEXT_KEY,
    EXTERNAL_CONTEXT_MANAGER_KEY
)

# Schema/Model imports (adjust paths as necessary based on your project structure)
from services.kiwi_app.workflow_app.schemas import WorkflowRunJobCreate
# Simple Mock User if real one is complex to import/instantiate
class MockUser(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    is_superuser: bool = False
    # Add other fields if CustomerDataService checks them, but keep minimal

# --- Test Class ---

class TestLoadMultipleCustomerNode(unittest.IsolatedAsyncioTestCase):
    """
    Integration tests for LoadMultipleCustomerDataNode.

    These tests assume a running MongoDB instance accessible via settings.
    They create, list, and load test documents based on various criteria.
    """
    test_org_id: uuid.UUID
    test_user_id: uuid.UUID
    test_superuser_id: uuid.UUID
    test_other_user_id: uuid.UUID # For on behalf of tests
    user_regular: MockUser
    user_superuser: MockUser
    user_other: MockUser
    run_job_regular: WorkflowRunJobCreate
    run_job_superuser: WorkflowRunJobCreate
    runtime_config_regular: Dict[str, Any]
    runtime_config_superuser: Dict[str, Any]

    test_namespace_a: str = "test_ns_a"
    test_namespace_b: str = "test_ns_b"
    test_doc_prefix: str = "multi_load_doc_"

    async def asyncSetUp(self):
        """Set up test-specific users, orgs, and contexts before each test."""
        self.test_org_id = uuid.uuid4()
        self.test_user_id = uuid.uuid4()
        self.test_superuser_id = uuid.uuid4()
        self.test_other_user_id = uuid.uuid4()

        self.user_regular = MockUser(id=self.test_user_id, is_superuser=False)
        self.user_superuser = MockUser(id=self.test_superuser_id, is_superuser=True)
        self.user_other = MockUser(id=self.test_other_user_id, is_superuser=False)

        # Base Run Job (can be customized per test)
        base_run_job_info = {
            "run_id": uuid.uuid4(),
            "workflow_id": uuid.uuid4(),
            "owner_org_id": self.test_org_id,
            # triggered_by_user_id will be set below
        }
        self.run_job_regular = WorkflowRunJobCreate(
            **base_run_job_info, triggered_by_user_id=self.user_regular.id
        )
        self.run_job_superuser = WorkflowRunJobCreate(
            **base_run_job_info, triggered_by_user_id=self.user_superuser.id
        )

        # Initialize context for each test
        self.external_context = await get_external_context_manager_with_clients()

        # Runtime Configs
        self.runtime_config_regular = {
            "configurable": {
                APPLICATION_CONTEXT_KEY: {
                    "user": self.user_regular,
                    "workflow_run_job": self.run_job_regular
                },
                EXTERNAL_CONTEXT_MANAGER_KEY: self.external_context
            }
        }
        self.runtime_config_superuser = {
            "configurable": {
                APPLICATION_CONTEXT_KEY: {
                    "user": self.user_superuser,
                    "workflow_run_job": self.run_job_superuser
                },
                EXTERNAL_CONTEXT_MANAGER_KEY: self.external_context
            }
        }


        self.customer_data_service = self.external_context.customer_data_service
        if not self.customer_data_service or not self.customer_data_service.versioned_mongo_client:
             raise unittest.SkipTest("CustomerDataService or Versioned Client could not be initialized.")
        self.external_context.mongo.customer.add_default_fields_to_data = False
        self.external_context.customer_data_service.mongo_client.add_default_fields_to_data = False
        self.external_context.customer_data_service.versioned_mongo_client.return_timestamp_metadata = False

        # Ensure clean slate before each test by deleting potential leftovers
        await self._clean_test_data()

    async def asyncTearDown(self):
        """Clean up any data created by the test and close context."""
        await self._clean_test_data()
        # Close context after each test
        if self.external_context:
            await self.external_context.close()

    async def _clean_test_data(self):
        """Helper to delete test data using appropriate patterns. (Copied from sibling test file)"""
        if not self.customer_data_service:
            return

        # Define base patterns for deletion
        base_customer_segments = 4
        versioned_customer_segments = base_customer_segments + len(self.customer_data_service.versioned_mongo_client.VERSION_SEGMENT_NAMES)

        # Common User IDs to cleanup
        user_ids_to_clean = [
            str(self.test_user_id),
            str(self.test_superuser_id),
            str(self.test_other_user_id)
        ]

        # --- Cleanup Unversioned Client Data --- #
        patterns_to_delete_unversioned = []
        for user_id_str in user_ids_to_clean:
             patterns_to_delete_unversioned.append(
                 [str(self.test_org_id), user_id_str] + [ "*" ] * (base_customer_segments - 2)
             )
        patterns_to_delete_unversioned.extend([
            [str(self.test_org_id), self.customer_data_service.SHARED_DOC_PLACEHOLDER] + [ "*" ] * (base_customer_segments - 2),
            [self.customer_data_service.SYSTEM_DOC_PLACEHOLDER] + [ "*" ] * (base_customer_segments - 1)
        ])
        delete_prefixes = [ [ "*" ] ] # Superuser access

        for pattern in patterns_to_delete_unversioned:
            try:
                await self.customer_data_service.mongo_client.delete_objects(
                    pattern=pattern, allowed_prefixes=delete_prefixes
                )
            except Exception as e:
                print(f"Warning: Error during unversioned cleanup for pattern {pattern}: {e}")

        # --- Cleanup Versioned Client Data --- #
        if self.customer_data_service.versioned_mongo_client:
            patterns_to_delete_versioned = []
            for user_id_str in user_ids_to_clean:
                 patterns_to_delete_versioned.append(
                     [str(self.test_org_id), user_id_str] + [ "*" ] * (versioned_customer_segments - 2)
                 )
            patterns_to_delete_versioned.extend([
                [str(self.test_org_id), self.customer_data_service.SHARED_DOC_PLACEHOLDER] + [ "*" ] * (versioned_customer_segments - 2),
                [self.customer_data_service.SYSTEM_DOC_PLACEHOLDER] + [ "*" ] * (versioned_customer_segments - 1)
            ])

            for pattern in patterns_to_delete_versioned:
                try:
                    await self.customer_data_service.versioned_mongo_client.client.delete_objects(
                        pattern=pattern, allowed_prefixes=delete_prefixes
                    )
                except Exception as e:
                     print(f"Warning: Error during versioned cleanup for pattern {pattern}: {e}")

    # --- Test Helper Methods ---
    def _get_load_multiple_node(self, config: Dict[str, Any]) -> LoadMultipleCustomerDataNode:
        """Instantiate LoadMultipleCustomerDataNode with given config."""
        node_config = LoadMultipleCustomerDataConfig(**config)
        return LoadMultipleCustomerDataNode(config=node_config, node_id="test-load-multiple-node")

    # Re-use helper from sibling test file to dynamically create output model
    def _get_dynamic_load_multiple_output_cls(self, model_name: str, field_definitions: List[Tuple[str, Type, Any]]) -> Type[LoadMultipleCustomerDataOutput]:
        """Creates a dynamic Pydantic model inheriting from LoadMultipleCustomerDataOutput."""
        fields_for_dynamic_schema: Dict[str, Any] = {}
        base_fields = LoadMultipleCustomerDataOutput.model_fields.keys()

        for name, type_hint, default_value in field_definitions:
            if name in base_fields:
                 print(f"Warning: Dynamic field '{name}' overrides a field from the base LoadMultipleCustomerDataOutput schema.")

            if default_value is ...: # Required field
                field_info = Field(...)
            else: # Optional field with a default value
                field_info = Field(default=default_value)

            fields_for_dynamic_schema[name] = (type_hint, field_info)

        DynamicOutputModel = create_model(
            model_name,
            __base__=LoadMultipleCustomerDataOutput,
            __module__=LoadMultipleCustomerDataOutput.__module__,
            **fields_for_dynamic_schema
        )
        return DynamicOutputModel

    async def _store_test_doc(
        self, namespace: str, docname: str, data: Any,
        is_shared: bool = False, is_system: bool = False, is_versioned: bool = False,
        version: Optional[str] = "default", user: Optional[MockUser] = None
    ) -> None:
        """Helper to store a document for testing purposes."""
        store_user = user or self.user_regular # Default to regular user
        target_org_id = None if is_system else self.test_org_id

        if is_versioned:
            try:
                await self.customer_data_service.initialize_versioned_document(
                    db=None, org_id=target_org_id, namespace=namespace, docname=docname,
                    is_shared=is_shared, user=store_user, initial_version=version,
                    initial_data=data, is_system_entity=is_system
                )
            except Exception as e:
                # If init fails (e.g., already exists), try update
                if "already exists" in str(e) or ("status_code=409" in str(e)): # Check for conflict
                    print(f"Info: Init failed for {namespace}/{docname} (versioned), attempting update.")
                    await self.customer_data_service.update_versioned_document(
                         db=None, org_id=target_org_id, namespace=namespace, docname=docname,
                         is_shared=is_shared, user=store_user, data=data, version=version,
                         is_system_entity=is_system
                    )
                else:
                    print(f"Error during versioned init for {namespace}/{docname}: {e}")
                    raise # Re-raise other initialization errors
        else:
            # Using upsert logic for unversioned is simpler for testing
            await self.customer_data_service.create_or_update_unversioned_document(
                db=None, org_id=target_org_id, namespace=namespace, docname=docname,
                is_shared=is_shared, user=store_user, data=data, is_system_entity=is_system
            )
        # Small delay to help ensure created_at differs if tests rely on it
        await asyncio.sleep(0.01)


    # --- Test Cases ---

    async def test_load_multiple_basic(self):
        """Test loading user-specific and shared docs in the same namespace."""
        output_field = "loaded_docs"
        doc_name_user = self.test_doc_prefix + "basic_user"
        data_user = {"owner": "user", "id": 1}
        await self._store_test_doc(self.test_namespace_a, doc_name_user, data_user, user=self.user_regular)

        doc_name_shared = self.test_doc_prefix + "basic_shared"
        data_shared = {"owner": "shared", "id": 2}
        await self._store_test_doc(self.test_namespace_a, doc_name_shared, data_shared, is_shared=True, user=self.user_regular)

        doc_name_other_ns = self.test_doc_prefix + "basic_other_ns"
        data_other_ns = {"owner": "user", "id": 3}
        await self._store_test_doc(self.test_namespace_b, doc_name_other_ns, data_other_ns, user=self.user_regular)

        load_node = self._get_load_multiple_node({
            "namespace_filter": self.test_namespace_a, # Filter by namespace A
            "include_shared": True,
            "include_user_specific": True,
            "output_field_name": output_field,
            "sort_by": None # Ensure default sort order doesn't break things
        })

        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls(
            "LoadMultipleBasicOutput",
            [(output_field, List[Dict[str, Any]], ...)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        self.assertTrue(hasattr(output, output_field))
        loaded_data = getattr(output, output_field)
        self.assertIsInstance(loaded_data, list)
        self.assertEqual(len(loaded_data), 2, f"Expected 2 docs, got {len(loaded_data)}: {loaded_data}")
        self.assertIn(data_user, loaded_data)
        self.assertIn(data_shared, loaded_data)
        # Note: documents_listed might be higher if the service lists before filtering user access within list_documents
        # self.assertEqual(output.load_metadata["documents_listed"], 2)
        self.assertEqual(output.load_metadata["documents_loaded"], 2)

    async def test_load_multiple_versioned_and_unversioned(self):
        """Test loading a mix of versioned and unversioned docs."""
        output_field = "mixed_docs"
        doc_name_unv = self.test_doc_prefix + "mix_unv"
        data_unv = {"type": "unversioned"}
        await self._store_test_doc(self.test_namespace_a, doc_name_unv, data_unv)

        doc_name_ver = self.test_doc_prefix + "mix_ver"
        data_ver = {"type": "versioned", "val": "v1"}
        await self._store_test_doc(self.test_namespace_a, doc_name_ver, data_ver, is_versioned=True, version="v1")

        load_node = self._get_load_multiple_node({
            "namespace_filter": self.test_namespace_a,
            "output_field_name": output_field,
            "global_version_config": {"version": "v1"} # Specify version to load for versioned docs
        })

        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls(
            "LoadMultipleMixedOutput",
            [(output_field, List[Dict[str, Any]], ...)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        loaded_data = getattr(output, output_field)
        self.assertEqual(len(loaded_data), 2, f"Expected 2 docs, got {len(loaded_data)}: {loaded_data}")
        self.assertIn(data_unv, loaded_data)
        self.assertIn(data_ver, loaded_data) # Should load v1 data
        self.assertEqual(output.load_metadata["documents_loaded"], 2)

    async def test_load_multiple_versioned_loads_active_by_default(self):
        """Test versioned docs load the active version when global_version_config is None."""
        output_field = "active_ver_docs"
        doc_name = self.test_doc_prefix + "active_ver"
        data_v1 = {"val": "v1"}
        data_v2_active = {"val": "v2_active"}

        # Store v1
        await self._store_test_doc(self.test_namespace_a, doc_name, data_v1, is_versioned=True, version="v1")
        # Store v2 and make it active
        await self.customer_data_service.create_versioned_document_version(
             org_id=self.test_org_id, namespace=self.test_namespace_a, docname=doc_name,
             is_shared=False, user=self.user_regular, new_version="v2"
        )
        await self._store_test_doc(self.test_namespace_a, doc_name, data_v2_active, is_versioned=True, version="v2")
        await self.customer_data_service.set_active_version(
             org_id=self.test_org_id, namespace=self.test_namespace_a, docname=doc_name,
             is_shared=False, user=self.user_regular, version="v2"
        )

        load_node = self._get_load_multiple_node({
            "namespace_filter": self.test_namespace_a,
            "output_field_name": output_field,
            "global_version_config": None # Explicitly None (or omitted)
        })

        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls(
            "LoadMultipleActiveVerOutput",
            [(output_field, List[Dict[str, Any]], ...)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        loaded_data = getattr(output, output_field)
        # import ipdb; ipdb.set_trace()
        self.assertEqual(len(loaded_data), 1, f"Expected 1 doc, got {len(loaded_data)}: {loaded_data}")
        self.assertEqual(loaded_data[0], data_v2_active) # Should load active v2 data
        self.assertEqual(output.load_metadata["documents_loaded"], 1)


    async def test_load_multiple_pagination_and_sort_asc(self):
        """Test skip, limit, and sort_by (ASC) parameters."""
        output_field = "paginated_docs_asc"
        # Create 5 docs with an index for predictable sorting
        docs_data = []
        for i in range(5):
            doc_name = f"{self.test_doc_prefix}page_{i}"
            # Store index within the data, assuming list_documents uses created_at
            data = {"id": i, "doc_name": doc_name}
            docs_data.append(data)
            await self._store_test_doc(self.test_namespace_a, doc_name, data)

        load_node = self._get_load_multiple_node({
            "namespace_filter": self.test_namespace_a,
            "skip": 1,
            "limit": 2,
            "output_field_name": output_field,
            "sort_by": CustomerDataSortBy.CREATED_AT, # Sort by creation time
            "sort_order": SortOrder.ASC, # Oldest first
        })

        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls(
            "LoadMultiplePaginationAscOutput",
            [(output_field, List[Dict[str, Any]], ...)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        loaded_data = getattr(output, output_field)
        self.assertEqual(len(loaded_data), 2, f"Expected 2 docs, got {len(loaded_data)}")
        # Based on ASC sort by creation, skip 1, limit 2 should load docs with id=1 and id=2
        loaded_ids = sorted([d.get("id") for d in loaded_data])
        self.assertEqual(loaded_ids, [1, 2], f"Expected IDs [1, 2], got {loaded_ids}")
        self.assertEqual(output.load_metadata["documents_loaded"], 2)
        self.assertEqual(output.load_metadata["config_skip"], 1)
        self.assertEqual(output.load_metadata["config_limit"], 2)

    async def test_load_multiple_pagination_and_sort_desc(self):
        """Test skip, limit, and sort_by (DESC) parameters."""
        output_field = "paginated_docs_desc"
        # Create 5 docs with an index for predictable sorting
        docs_data = []
        for i in range(5):
            doc_name = f"{self.test_doc_prefix}page_desc_{i}"
            data = {"id": i, "doc_name": doc_name}
            docs_data.append(data)
            await self._store_test_doc(self.test_namespace_a, doc_name, data, is_versioned=True)

        load_node = self._get_load_multiple_node({
            "namespace_filter": self.test_namespace_a,
            "skip": 2,
            "limit": 4,  # NOTE: this is hack to load atleast 2 versioned data -- which is also not guaranteed since versioned metadata
            "output_field_name": output_field,
            "sort_by": CustomerDataSortBy.CREATED_AT, # Sort by creation time
            "sort_order": SortOrder.DESC, # Newest first
        })

        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls(
            "LoadMultiplePaginationDescOutput",
            [(output_field, List[Dict[str, Any]], ...)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        loaded_data = getattr(output, output_field)
        self.assertEqual(len(loaded_data), 2, f"Expected 2 docs, got {len(loaded_data)}")
        # Based on DESC sort by creation, skip 1, limit 2 should load docs with id=3 and id=2
        loaded_ids = sorted([d.get("id") for d in loaded_data])
        self.assertEqual(loaded_ids, [2, 3], f"Expected IDs [2, 3], got {loaded_ids}")
        self.assertEqual(output.load_metadata["documents_loaded"], 2)
        self.assertEqual(output.load_metadata["config_skip"], 2)
        self.assertEqual(output.load_metadata["config_limit"], 4)

    async def test_load_multiple_only_shared(self):
        """Test loading only shared documents."""
        output_field = "shared_only_docs"
        # Store user doc (should be excluded)
        await self._store_test_doc(self.test_namespace_a, "user_doc_excl", {"id": "user"})
        # Store shared doc (should be included)
        data_shared = {"id": "shared"}
        await self._store_test_doc(self.test_namespace_a, "shared_doc_incl", data_shared, is_shared=True)

        load_node = self._get_load_multiple_node({
            "namespace_filter": self.test_namespace_a,
            "include_shared": True,
            "include_user_specific": False, # Exclude user docs
            "output_field_name": output_field,
        })
        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls(
            "LoadMultipleSharedOnlyOutput", [(output_field, List[Dict[str, Any]], ...)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        loaded_data = getattr(output, output_field)
        self.assertEqual(len(loaded_data), 1)
        self.assertEqual(loaded_data[0], data_shared)
        self.assertEqual(output.load_metadata["documents_loaded"], 1)

    async def test_load_multiple_only_user(self):
        """Test loading only user-specific documents."""
        output_field = "user_only_docs"
        # Store user doc (should be included)
        data_user = {"id": "user"}
        await self._store_test_doc(self.test_namespace_a, "user_doc_incl", data_user)
        # Store shared doc (should be excluded)
        await self._store_test_doc(self.test_namespace_a, "shared_doc_excl", {"id": "shared"}, is_shared=True)

        load_node = self._get_load_multiple_node({
            "namespace_filter": self.test_namespace_a,
            "include_shared": False, # Exclude shared docs
            "include_user_specific": True,
            "output_field_name": output_field,
        })
        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls(
            "LoadMultipleUserOnlyOutput", [(output_field, List[Dict[str, Any]], ...)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        loaded_data = getattr(output, output_field)
        self.assertEqual(len(loaded_data), 1)
        self.assertEqual(loaded_data[0], data_user)
        self.assertEqual(output.load_metadata["documents_loaded"], 1)


    async def test_load_multiple_on_behalf_of_superuser(self):
        """Test superuser loading docs on behalf of another user."""
        output_field = "other_user_docs"
        # Store docs for the target user
        doc_name_other1 = self.test_doc_prefix + "other_user_1"
        data_other1 = {"owner": str(self.test_other_user_id)}
        await self._store_test_doc(self.test_namespace_a, doc_name_other1, data_other1, user=self.user_other)

        doc_name_other2 = self.test_doc_prefix + "other_user_2"
        data_other2 = {"owner": str(self.test_other_user_id)}
        await self._store_test_doc(self.test_namespace_a, doc_name_other2, data_other2, user=self.user_other)

        # Store a doc for the superuser themselves (should not be loaded)
        doc_name_su = self.test_doc_prefix + "su_doc_1"
        data_su = {"owner": str(self.test_superuser_id)}
        await self._store_test_doc(self.test_namespace_a, doc_name_su, data_su, user=self.user_superuser)

        load_node = self._get_load_multiple_node({
            "namespace_filter": self.test_namespace_a,
            "include_shared": False,
            "include_user_specific": True,
            "on_behalf_of_user_id": str(self.test_other_user_id), # Target the other user
            "output_field_name": output_field,
        })

        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls(
            "LoadMultipleOnBehalfOutput",
            [(output_field, List[Dict[str, Any]], ...)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        # Run with superuser context
        output = await load_node.process({}, runtime_config=self.runtime_config_superuser)

        loaded_data = getattr(output, output_field)
        self.assertEqual(len(loaded_data), 2)
        self.assertIn(data_other1, loaded_data)
        self.assertIn(data_other2, loaded_data)
        self.assertNotIn(data_su, loaded_data) # Ensure superuser's own doc wasn't loaded
        self.assertEqual(output.load_metadata["documents_loaded"], 2)

    async def test_load_multiple_on_behalf_of_regular_user_fail(self):
        """Test regular user cannot use on_behalf_of_user_id."""
        load_node = self._get_load_multiple_node({
            "on_behalf_of_user_id": str(self.test_other_user_id),
            "output_field_name": "should_fail",
        })
        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls("LoadMultipleOnBehalfFailOutput", [])
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        # Run with regular user context
        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        # Expect error in metadata, no documents loaded
        self.assertIn("error", output.load_metadata)
        self.assertIn("Permission denied for on_behalf_of_user_id", output.load_metadata["error"])
        # The output field itself won't be present in the output model instance data
        self.assertEqual(output.model_dump(), {"load_metadata": output.load_metadata})


    async def test_load_multiple_include_system_superuser(self):
        """Test superuser loading system entities."""
        output_field = "system_docs"
        doc_name_system = self.test_doc_prefix + "system_1"
        data_system = {"scope": "system"}
        # Store system entity (requires superuser) - let's make it shared system
        await self._store_test_doc(
            self.test_namespace_a, doc_name_system, data_system,
            is_shared=True, is_system=True, user=self.user_superuser
        )

        load_node = self._get_load_multiple_node({
            "include_shared": False, # Don't include normal shared
            "include_user_specific": False,
            "include_system_entities": True, # Specifically request system entities
            "output_field_name": output_field,
        })

        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls(
            "LoadMultipleSystemOutput",
            [(output_field, List[Dict[str, Any]], ...)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        # Run with superuser context
        output = await load_node.process({}, runtime_config=self.runtime_config_superuser)

        loaded_data = getattr(output, output_field)
        self.assertEqual(len(loaded_data), 1)
        self.assertIn(data_system, loaded_data)
        self.assertEqual(output.load_metadata["documents_loaded"], 1)

    async def test_load_multiple_include_system_regular_user_fail(self):
        """Test regular user cannot request include_system_entities=True."""
        load_node = self._get_load_multiple_node({
            "include_system_entities": True,
            "output_field_name": "should_fail",
        })
        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls("LoadMultipleSystemFailOutput", [])
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        # Run with regular user context
        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        # Expect error in metadata
        self.assertIn("error", output.load_metadata)
        self.assertIn("Permission denied for include_system_entities", output.load_metadata["error"])
        self.assertEqual(output.model_dump(), {"load_metadata": output.load_metadata})


    async def test_load_multiple_no_results(self):
        """Test loading when no documents match the criteria."""
        output_field = "empty_list"
        load_node = self._get_load_multiple_node({
            "namespace_filter": "non_existent_namespace",
            "output_field_name": output_field,
        })

        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls(
            "LoadMultipleEmptyOutput",
            [(output_field, List[Dict[str, Any]], ...)] # Expect an empty list
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        loaded_data = getattr(output, output_field)
        self.assertEqual(loaded_data, [])
        # Ensure metadata reflects 0 listed/loaded
        self.assertIn("documents_listed", output.load_metadata)
        self.assertEqual(output.load_metadata["documents_listed"], 0)
        self.assertEqual(output.load_metadata["documents_loaded"], 0)


    async def test_load_multiple_with_schema_option(self):
        """Test loading multiple docs with the global schema loading option."""
        output_field = "docs_with_schemas"
        # Doc 1 (Versioned with schema)
        doc_name_ver = self.test_doc_prefix + "schema_ver"
        data_ver = {"id": 1}
        schema_ver = {"type": "object", "properties": {"id": {"type": "integer"}}}
        await self.customer_data_service.initialize_versioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace_a, docname=doc_name_ver,
            user=self.user_regular, initial_data=data_ver, schema_definition=schema_ver, is_shared=False,
        )
        # Doc 2 (Unversioned - schema loading not applicable without template/def in opts)
        doc_name_unv = self.test_doc_prefix + "schema_unv"
        data_unv = {"id": "A"}
        await self._store_test_doc(self.test_namespace_a, doc_name_unv, data_unv)

        load_node = self._get_load_multiple_node({
            "namespace_filter": self.test_namespace_a,
            "output_field_name": output_field,
            "global_schema_options": {"load_schema": True} # Enable schema loading
        })

        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls(
            "LoadMultipleWithSchemaOptOutput",
            [(output_field, List[Dict[str, Any]], ...)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        loaded_data = getattr(output, output_field)
        self.assertEqual(len(loaded_data), 2)
        # Check data is present
        self.assertIn(data_ver, loaded_data)
        self.assertIn(data_unv, loaded_data)
        # Check metadata includes schema loaded count
        self.assertEqual(output.load_metadata["schemas_loaded_count"], 1) # Only versioned doc had schema associated

    # --- New tests for dynamic configuration functionality ---

    async def test_load_multiple_with_config_input_path(self):
        """Test loading docs using configuration from input_data via config_input_path."""
        output_field = "dynamic_config_docs"
        
        # Create test documents in namespace A
        doc_name_a = self.test_doc_prefix + "dynamic_conf_a"
        data_a = {"source": "namespace_a"}
        await self._store_test_doc(self.test_namespace_a, doc_name_a, data_a)
        
        # Create test documents in namespace B
        doc_name_b = self.test_doc_prefix + "dynamic_conf_b" 
        data_b = {"source": "namespace_b"}
        await self._store_test_doc(self.test_namespace_b, doc_name_b, data_b)
        
        # Define the expected output model
        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls(
            "LoadMultipleDynamicConfigOutput",
            [(output_field, List[Dict[str, Any]], ...)]
        )
        
        # Create node with config_input_path
        load_node = self._get_load_multiple_node({
            "config_input_path": "dynamic_config",  # Look for config in input_data.dynamic_config
            "output_field_name": output_field,      # Default field name if not overridden
            "namespace_filter": self.test_namespace_a  # Default namespace if not overridden
        })
        load_node.__class__.output_schema_cls = ExpectedOutputModel
        
        # Input data containing the dynamic configuration
        input_data = {
            "dynamic_config": {
                "namespace_filter": self.test_namespace_b,  # Override namespace_filter
                "limit": 10,
                "output_field_name": output_field  # Keep same output field
            }
        }
        
        # Process with dynamic config
        output = await load_node.process(input_data, runtime_config=self.runtime_config_regular)
        
        # Verify results
        loaded_data = getattr(output, output_field)
        self.assertEqual(len(loaded_data), 1)
        self.assertEqual(loaded_data[0], data_b)  # Should load namespace B doc
        self.assertEqual(output.load_metadata["documents_loaded"], 1)
        self.assertTrue(output.load_metadata["used_dynamic_config"])
        
    async def test_load_multiple_namespace_pattern(self):
        """Test loading docs using namespace pattern and namespace_pattern_input_path."""
        output_field = "pattern_docs"
        
        # Create test documents in dynamically determined namespaces
        # Format: user_{user_id}_docs
        user1_id = "user123"
        user2_id = "user456"
        
        user1_namespace = f"user_{user1_id}_docs"
        user2_namespace = f"user_{user2_id}_docs"
        
        # Store docs in user-specific namespaces
        doc_name_1 = self.test_doc_prefix + "pattern_test_1"
        data_1 = {"owner": user1_id}
        await self._store_test_doc(user1_namespace, doc_name_1, data_1)
        
        doc_name_2 = self.test_doc_prefix + "pattern_test_2"
        data_2 = {"owner": user2_id}
        await self._store_test_doc(user2_namespace, doc_name_2, data_2)
        
        # Define the expected output model
        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls(
            "LoadMultiplePatternOutput",
            [(output_field, List[Dict[str, Any]], ...)]
        )
        
        # Create node with namespace pattern
        load_node = self._get_load_multiple_node({
            "namespace_pattern": "user_{item}_docs",
            "namespace_pattern_input_path": "user_context.user_id",
            "output_field_name": output_field,
        })
        load_node.__class__.output_schema_cls = ExpectedOutputModel
        
        # Input data containing user context
        input_data = {
            "user_context": {
                "user_id": user1_id  # Will resolve to user_user123_docs
            }
        }
        
        # Process with namespace pattern
        output = await load_node.process(input_data, runtime_config=self.runtime_config_regular)
        
        # Verify results
        loaded_data = getattr(output, output_field)
        self.assertEqual(len(loaded_data), 1)
        self.assertEqual(loaded_data[0], data_1)  # Should load user1's doc
        self.assertEqual(output.load_metadata["documents_loaded"], 1)
        self.assertEqual(output.load_metadata["resolved_namespace"], user1_namespace)
        
        # Try with the second user
        input_data = {
            "user_context": {
                "user_id": user2_id  # Will resolve to user_user456_docs
            }
        }
        
        output = await load_node.process(input_data, runtime_config=self.runtime_config_regular)
        
        # Verify results
        loaded_data = getattr(output, output_field)
        self.assertEqual(len(loaded_data), 1)
        self.assertEqual(loaded_data[0], data_2)  # Should load user2's doc
        self.assertEqual(output.load_metadata["documents_loaded"], 1)
        self.assertEqual(output.load_metadata["resolved_namespace"], user2_namespace)
    
    async def test_load_multiple_namespace_pattern_with_complex_object(self):
        """Test namespace pattern with a complex object from input path."""
        output_field = "complex_pattern_docs"
        
        # Create test document with a complex namespace pattern
        complex_namespace = "customer_123_project_456"
        
        doc_name = self.test_doc_prefix + "complex_pattern"
        data = {"type": "complex_pattern_test"}
        await self._store_test_doc(complex_namespace, doc_name, data)
        
        # Define the expected output model
        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls(
            "LoadMultipleComplexPatternOutput",
            [(output_field, List[Dict[str, Any]], ...)]
        )
        
        # Create node with namespace pattern
        load_node = self._get_load_multiple_node({
            "namespace_pattern": "customer_{item[customer_id]}_project_{item[project_id]}",
            "namespace_pattern_input_path": "project_context",
            "output_field_name": output_field,
        })
        load_node.__class__.output_schema_cls = ExpectedOutputModel
        
        # Input data containing complex object
        input_data = {
            "project_context": {
                "customer_id": "123",
                "project_id": "456"
            }
        }
        
        # Process with namespace pattern
        output = await load_node.process(input_data, runtime_config=self.runtime_config_regular)
        
        # Verify results
        loaded_data = getattr(output, output_field)
        self.assertEqual(len(loaded_data), 1)
        self.assertEqual(loaded_data[0], data)
        self.assertEqual(output.load_metadata["documents_loaded"], 1)
        self.assertEqual(output.load_metadata["resolved_namespace"], complex_namespace)
    
    async def test_load_multiple_missing_namespace_pattern_data(self):
        """Test behavior when namespace pattern input path doesn't exist."""
        output_field = "missing_pattern_docs"
        
        # Define the expected output model
        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls(
            "LoadMultipleMissingPatternOutput",
            [(output_field, List[Dict[str, Any]], ...)]
        )
        
        # Create node with namespace pattern
        load_node = self._get_load_multiple_node({
            "namespace_pattern": "user_{item}_docs",
            "namespace_pattern_input_path": "nonexistent.path",
            "output_field_name": output_field,
        })
        load_node.__class__.output_schema_cls = ExpectedOutputModel
        
        # Empty input data
        input_data = {}
        
        # Process with namespace pattern - should not fail but return empty results
        output = await load_node.process(input_data, runtime_config=self.runtime_config_regular)
        
        # Verify we get empty results due to pattern resolution failure
        loaded_data = getattr(output, output_field)
        self.assertEqual(len(loaded_data), 0)
        self.assertEqual(output.load_metadata["documents_loaded"], 0)
        # Should be no resolved namespace in metadata
        self.assertIsNone(output.load_metadata["resolved_namespace"])
    
    async def test_load_multiple_combined_dynamic_config_and_pattern(self):
        """Test combining dynamic configuration and namespace pattern."""
        output_field = "combined_feature_docs"
        dynamic_output_field = "dynamic_output_name"
        
        # Create test documents in a dynamically determined namespace
        dynamic_namespace = "tenant_789_data"
        
        doc_name = self.test_doc_prefix + "combined_test"
        data = {"type": "combined_features_test"}
        await self._store_test_doc(dynamic_namespace, doc_name, data)
        
        # Define the expected output model - support both potential field names
        ExpectedOutputModel = self._get_dynamic_load_multiple_output_cls(
            "LoadMultipleCombinedOutput",
            [
                (output_field, List[Dict[str, Any]], []),
                (dynamic_output_field, List[Dict[str, Any]], [])
            ]
        )
        
        # Create node with config_input_path but default values
        load_node = self._get_load_multiple_node({
            "config_input_path": "dynamic_node_config",
            "namespace_pattern": "default_pattern_{item}",  # Should be overridden
            "namespace_pattern_input_path": "default.path", # Should be overridden
            "output_field_name": output_field,               # Should be overridden
        })
        load_node.__class__.output_schema_cls = ExpectedOutputModel
        
        # Input data containing both dynamic config and pattern data
        input_data = {
            "dynamic_node_config": {
                "namespace_pattern": "tenant_{item}_data",
                "namespace_pattern_input_path": "tenant_info.id",
                "output_field_name": dynamic_output_field,
                "limit": 5
            },
            "tenant_info": {
                "id": "789",
                "name": "Test Tenant"
            }
        }
        
        # Process with combined features
        output = await load_node.process(input_data, runtime_config=self.runtime_config_regular)
        
        # Verify results - should use dynamically configured field name
        loaded_data = getattr(output, dynamic_output_field)
        self.assertEqual(len(loaded_data), 1)
        self.assertEqual(loaded_data[0], data)
        self.assertEqual(output.load_metadata["documents_loaded"], 1)
        self.assertEqual(output.load_metadata["resolved_namespace"], dynamic_namespace)
        self.assertTrue(output.load_metadata["used_dynamic_config"])
        # Original field should be an empty list (or missing)
        self.assertFalse(hasattr(output, output_field) and getattr(output, output_field))

# --- Run Tests ---
if __name__ == '__main__':
    unittest.main()
