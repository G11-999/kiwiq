import unittest
import uuid
import asyncio
from typing import Dict, Any, Optional, List, Tuple, Type

# Pydantic for User mock & create_model
from pydantic import BaseModel, Field, create_model

# Node imports
from services.workflow_service.registry.nodes.db.customer_data import (
    LoadCustomerDataNode,
    StoreCustomerDataNode,
    LoadCustomerDataConfig,
    StoreCustomerDataConfig,
    LoadPathConfig,
    StoreConfig,
    FilenameConfig,
    VersioningInfo,
    SchemaOptions,
    StoreOperation,
    LoadCustomerDataOutput,
    StoreCustomerDataOutput
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
# Assuming User model can be mocked simply or imported
# Simple Mock User if real one is complex to import/instantiate
class MockUser(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    is_superuser: bool = False
    # Add other fields if CustomerDataService checks them, but keep minimal

# --- Test Class ---

class TestCustomerDataNodes(unittest.IsolatedAsyncioTestCase):
    """
    Integration tests for LoadCustomerDataNode and StoreCustomerDataNode.

    These tests assume a running MongoDB instance accessible via settings.
    They create, retrieve, and delete test documents.
    """
    test_org_id: uuid.UUID
    test_user_id: uuid.UUID
    test_superuser_id: uuid.UUID
    test_target_user_id: uuid.UUID # New user ID for 'on behalf of' tests
    user_regular: MockUser
    user_superuser: MockUser
    user_target: MockUser # New user instance
    run_job_regular: WorkflowRunJobCreate
    run_job_superuser: WorkflowRunJobCreate
    runtime_config_regular: Dict[str, Any]
    runtime_config_superuser: Dict[str, Any]

    test_namespace: str = "test_namespace"
    test_docname_base: str = "test_doc_"

    async def asyncSetUp(self):
        """Set up test-specific users, orgs, and contexts before each test."""
        self.test_org_id = uuid.uuid4()
        self.test_user_id = uuid.uuid4()
        self.test_superuser_id = uuid.uuid4()
        self.test_target_user_id = uuid.uuid4()

        self.user_regular = MockUser(id=self.test_user_id, is_superuser=False)
        self.user_superuser = MockUser(id=self.test_superuser_id, is_superuser=True)
        self.user_target = MockUser(id=self.test_target_user_id, is_superuser=False)

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
        self.external_context.mongo.customer.add_default_fields_to_data = False
        self.external_context.customer_data_service.mongo_client.add_default_fields_to_data = False
        self.external_context.customer_data_service.versioned_mongo_client.return_timestamp_metadata = False

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
        if not self.customer_data_service:
             raise unittest.SkipTest("CustomerDataService could not be initialized.")

        # Ensure clean slate before each test by deleting potential leftovers
        await self._clean_test_data()

    async def asyncTearDown(self):
        """Clean up any data created by the test and close context."""
        await self._clean_test_data()
        # Close context after each test
        if self.external_context:
            await self.external_context.close()

    async def _clean_test_data(self):
        """Helper to delete test data using appropriate patterns."""
        if not self.customer_data_service:
            return

        # Define base patterns for deletion (adjust segment count if necessary)
        # Assuming customer data uses [org, user/shared, ns, docname]
        # And versioned adds [version, sequence]
        base_customer_segments = 4
        versioned_customer_segments = base_customer_segments + len(self.customer_data_service.versioned_mongo_client.VERSION_SEGMENT_NAMES)

        # --- Cleanup Unversioned Client Data --- #
        patterns_to_delete_unversioned = [
            # User specific data for regular user
            [str(self.test_org_id), str(self.test_user_id)] + [ "*" ] * (base_customer_segments - 2),
            # User specific data for superuser
            [str(self.test_org_id), str(self.test_superuser_id)] + [ "*" ] * (base_customer_segments - 2),
            # User specific data for target user (for on behalf of tests)
            [str(self.test_org_id), str(self.test_target_user_id)] + [ "*" ] * (base_customer_segments - 2),
            # Shared data for the org
            [str(self.test_org_id), self.customer_data_service.SHARED_DOC_PLACEHOLDER] + [ "*" ] * (base_customer_segments - 2),
            # Potential System data (assuming superuser can clean)
            [self.customer_data_service.SYSTEM_DOC_PLACEHOLDER] + [ "*" ] * (base_customer_segments - 1)
        ]
        # Define allowed prefixes for deletion (superuser should be able to delete all)
        delete_prefixes_unversioned = [ [ "*" ] ] # Superuser access

        for pattern in patterns_to_delete_unversioned:
            try:
                await self.customer_data_service.mongo_client.delete_objects(
                    pattern=pattern,
                    allowed_prefixes=delete_prefixes_unversioned
                )
            except Exception as e:
                print(f"Warning: Error during unversioned cleanup for pattern {pattern}: {e}")

        # --- Cleanup Versioned Client Data --- #
        if self.customer_data_service.versioned_mongo_client:
            patterns_to_delete_versioned = [
                # User specific data (including versions/history)
                [str(self.test_org_id), str(self.test_user_id)] + [ "*" ] * (versioned_customer_segments - 2),
                # Superuser specific data
                [str(self.test_org_id), str(self.test_superuser_id)] + [ "*" ] * (versioned_customer_segments - 2),
                # Shared data
                [str(self.test_org_id), self.customer_data_service.SHARED_DOC_PLACEHOLDER] + [ "*" ] * (versioned_customer_segments - 2),
                # System data
                [self.customer_data_service.SYSTEM_DOC_PLACEHOLDER] + [ "*" ] * (versioned_customer_segments - 1)
            ]
            delete_prefixes_versioned = [ [ "*" ] ] # Superuser access

            for pattern in patterns_to_delete_versioned:
                try:
                    await self.customer_data_service.versioned_mongo_client.client.delete_objects(
                        pattern=pattern,
                        allowed_prefixes=delete_prefixes_versioned
                    )
                except Exception as e:
                     print(f"Warning: Error during versioned cleanup for pattern {pattern}: {e}")

    # --- Test Helper Methods ---
    def _get_store_node(self, config: Dict[str, Any]) -> StoreCustomerDataNode:
        """Instantiate StoreCustomerDataNode with given config."""
        node_config = StoreCustomerDataConfig(**config)
        return StoreCustomerDataNode(config=node_config, node_id="test-store-node", prefect_mode=False)

    def _get_load_node(self, config: Dict[str, Any]) -> LoadCustomerDataNode:
        """Instantiate LoadCustomerDataNode with given config."""
        node_config = LoadCustomerDataConfig(**config)
        return LoadCustomerDataNode(config=node_config, node_id="test-load-node", prefect_mode=False)

    # Helper to create dynamic output model for Load node tests
    def _get_dynamic_load_output_cls(self, model_name: str, field_definitions: List[Tuple[str, Type, Any]] = [] , cur__class=LoadCustomerDataOutput) -> Type[LoadCustomerDataOutput]:
        """Creates a dynamic Pydantic model inheriting from LoadCustomerDataOutput."""
        # Start with all fields from the base class, marked for reuse.
        # Note: create_dynamic_schema_with_fields automatically inherits from the base class.
        fields_for_dynamic_schema: Dict[str, Any] = {
            # field_name: None for field_name in LoadCustomerDataOutput.model_fields.keys()
        }

        base_fields = cur__class.model_fields.keys()

        # Add or override fields based on the provided definitions
        for name, type_hint, default_value in field_definitions:
            if name in base_fields:
                print(f"Warning: Dynamic field '{name}' overrides a field from the base LoadCustomerDataOutput schema.")
                # If overriding, we still need to provide the definition
                # continue # Original behavior skipped conflicting fields. Let's allow override but warn.

            # Create a Pydantic Field object for the new field definition.
            # Use Ellipsis (...) as the default for required fields.
            if default_value is ...:
                # Required field
                field_info = Field(...)
            else:
                # Optional field with a default value
                field_info = Field(default=default_value)

            # Add the field definition as a tuple (type_hint, Field(...))
            fields_for_dynamic_schema[name] = (type_hint, field_info)

        # Use the BaseSchema helper to create the new dynamic model class
        DynamicOutputModel = create_model(
            model_name,
            __base__=cur__class,   
            __module__=cur__class.__module__,
            **fields_for_dynamic_schema
        )

        # The create_dynamic_schema_with_fields method already sets __base__,
        # so we don't need to pass it again.

        return DynamicOutputModel

    async def _assert_doc_exists(
        self,
        namespace: str,
        docname: str,
        is_shared: bool,
        is_system: bool,
        user: MockUser,
        expected_data: Optional[Dict] = None,
        version_to_check: Optional[str] = None,
    ):
        is_versioned = False
        metadata = None
        try:
            metadata = await self.customer_data_service.get_document_metadata(
                org_id=self.test_org_id,
                namespace=namespace,
                docname=docname,
                is_shared=is_shared,
                user=user,
                is_system_entity=is_system
            )
            print(f"Metadata: {metadata}; ****versioned={metadata.is_versioned}")
            is_versioned = metadata.is_versioned
        except Exception as meta_exc:
            self.fail(f"Metadata check failed for '{namespace}/{docname}' (shared={is_shared}, system={is_system}): {meta_exc}")

        get_method_args = {
            "org_id": self.test_org_id,
            "namespace": namespace,
            "docname": docname,
            "is_shared": is_shared,
            "user": user,
            "is_system_entity": is_system
        }

        if is_versioned:
            get_method = self.customer_data_service.get_versioned_document
            get_method_args["version"] = version_to_check
        else:
            get_method = self.customer_data_service.get_unversioned_document
            if version_to_check is not None:
                print(f"Warning: version_to_check '{version_to_check}' provided but document is unversioned. Ignoring version.")

        try:
            fetched_data = await get_method(**get_method_args)
            actual_data_to_compare = fetched_data
            if is_versioned and isinstance(fetched_data, dict) and 'document' in fetched_data and 'min_sequence' in fetched_data:
                 print(f"Note: Fetched versioned data appears to be container for '{namespace}/{docname}', extracting 'document' field for comparison.")
                 actual_data_to_compare = fetched_data.get('document')

            self.assertIsNotNone(actual_data_to_compare, f"Document '{namespace}/{docname}' (version: {version_to_check or 'active/N/A'}) should exist and contain data.")
            
            if expected_data is not None:
                self.assertEqual(actual_data_to_compare, expected_data, f"Data mismatch for '{namespace}/{docname}' (version: {version_to_check or 'active/N/A'}).")

        except Exception as e:
            print(f"DEBUG: _assert_doc_exists failed. is_versioned={is_versioned}, version_to_check={version_to_check}")
            # Avoid printing potentially large fetched_data directly in failure message
            # print(f"DEBUG: Fetched data: {fetched_data}")
            print(f"DEBUG: Expected data: {expected_data}")
            self.fail(f"Failed assertion or error getting document '{namespace}/{docname}' (version: {version_to_check or 'active/N/A'}): {e}")

    # --- Store Node Tests ---

    async def test_store_unversioned_static_path(self):
        """Test storing a simple unversioned document with static path."""
        doc_name = self.test_docname_base + "unversioned_static"
        input_data = {"my_doc": {"value": 1, "label": "test1"}}
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "my_doc",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {
                        "is_versioned": False,
                        "operation": "upsert"
                    }
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        await self._assert_doc_exists(self.test_namespace, doc_name, is_shared=False, is_system=False, user=self.user_regular, expected_data=input_data["my_doc"])

    async def test_store_versioned_initialize_static_path(self):
        """Test initializing a versioned document."""
        doc_name = self.test_docname_base + "versioned_init"
        input_data = {"v_doc": {"version": 1, "status": "new"}}
        version_name = "v1.0"
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "v_doc",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {
                        "is_versioned": True,
                        "operation": "initialize",
                        "version": version_name
                    }
                }
            ]
        })
        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        await self._assert_doc_exists(self.test_namespace, doc_name, is_shared=False, is_system=False, user=self.user_regular, expected_data=input_data["v_doc"], version_to_check=version_name)

    async def test_store_versioned_update_static_path(self):
        """Test updating an existing versioned document."""
        doc_name = self.test_docname_base + "versioned_update"
        initial_data = {"version": 1, "status": "initial"}
        updated_data = {"version": 2, "status": "updated"}
        input_data = {"v_doc_update": updated_data}
        # 1. Initialize
        await self.customer_data_service.initialize_versioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, initial_version="default", initial_data=initial_data
        )
        # 2. Update
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "v_doc_update",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {
                        "is_versioned": True,
                        "operation": "update",
                        "version": "default"
                    }
                }
            ]
        })
        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        await self._assert_doc_exists(self.test_namespace, doc_name, is_shared=False, is_system=False, user=self.user_regular, expected_data=updated_data, version_to_check="default")





    # --- New Tests for UPSERT_VERSIONED ---

    async def test_store_versioned_upsert_initializes_new_doc(self):
        """Test UPSERT_VERSIONED initializes a new document when it doesn't exist."""
        doc_name = self.test_docname_base + "v_upsert_init"
        initial_data = {"status": "created_by_upsert"}
        input_data = {"new_doc": initial_data}
        version_name = "v1.0_upsert"

        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "new_doc",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {
                        "is_versioned": True,
                        "operation": StoreOperation.UPSERT_VERSIONED, # Use the enum
                        "version": version_name,
                        "is_complete": True # Mark as complete during init
                    }
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)

        # Assert document was created
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, initial_data, version_to_check=version_name)

        # Assert output path reflects initialization
        self.assertIsNotNone(output.paths_processed)
        self.assertEqual(len(output.paths_processed), 1)
        self.assertEqual(output.paths_processed[0][:3], [self.test_namespace, doc_name, f"initialized_version_{version_name}"])

    async def test_store_versioned_upsert_initializes_default_version(self):
        """Test UPSERT_VERSIONED initializes the 'default' version if no version is specified."""
        doc_name = self.test_docname_base + "v_upsert_init_default"
        initial_data = {"status": "created_by_upsert_default"}
        input_data = {"new_doc_default": initial_data}

        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "new_doc_default",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {
                        "is_versioned": True,
                        "operation": StoreOperation.UPSERT_VERSIONED,
                        "version": None, # Explicitly None, should initialize 'default'
                        "is_complete": True
                    }
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)

        # Assert document was created with 'default' version
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, initial_data, version_to_check="default")

        # Assert output path reflects initialization of 'default'
        self.assertEqual(output.paths_processed[0][:3], [self.test_namespace, doc_name, f"initialized_version_default"])

    async def test_store_versioned_upsert_updates_existing_version(self):
        """Test UPSERT_VERSIONED updates an existing document version."""
        doc_name = self.test_docname_base + "v_upsert_update"
        initial_data = {"status": "initial", "value": 1}
        updated_data = {"status": "updated_by_upsert", "value": 2}
        input_data = {"update_doc": updated_data}
        version_name = "v_to_update"

        # 1. Initialize the document first
        await self.customer_data_service.initialize_versioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, initial_version=version_name, initial_data=initial_data
        )

        # 2. Configure the upsert node
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "update_doc",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {
                        "is_versioned": True,
                        "operation": StoreOperation.UPSERT_VERSIONED,
                        "version": version_name # Target the existing version
                    }
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)

        # Assert document was updated
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, updated_data, version_to_check=version_name)

        # Assert output path reflects update
        self.assertEqual(output.paths_processed[0][:3], [self.test_namespace, doc_name, f"updated_{version_name}"])

    async def test_store_versioned_upsert_updates_active_version(self):
        """Test UPSERT_VERSIONED updates the active ('default') version when version is None."""
        doc_name = self.test_docname_base + "v_upsert_update_active"
        initial_data = {"status": "initial_active", "value": 10}
        updated_data = {"status": "updated_active_by_upsert", "value": 20}
        input_data = {"update_doc_active": updated_data}

        # 1. Initialize the document with 'default' version
        await self.customer_data_service.initialize_versioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, initial_version="default", initial_data=initial_data
        )

        # 2. Configure the upsert node targeting active version (version=None)
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "update_doc_active",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {
                        "is_versioned": True,
                        "operation": StoreOperation.UPSERT_VERSIONED,
                        "version": None # Target the active version
                    }
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)

        # Assert 'default' version was updated
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, updated_data, version_to_check="default")

        # Assert output path reflects update of 'active'
        self.assertEqual(output.paths_processed[0][:3], [self.test_namespace, doc_name, f"updated_$active"])

    async def test_store_versioned_upsert_initializes_new_version_for_existing_doc(self):
        """Test UPSERT_VERSIONED initializes a new version when the doc exists but the version doesn't."""
        doc_name = self.test_docname_base + "v_upsert_init_new_ver"
        initial_data_v1 = {"status": "v1_original"}
        new_data_v2 = {"status": "v2_created_by_upsert"}
        input_data = {"new_version_data": new_data_v2}
        version_name_v1 = "v1.0"
        version_name_v2 = "v2.0_upsert_init"

        # 1. Initialize the document with v1
        await self.customer_data_service.initialize_versioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, initial_version=version_name_v1, initial_data=initial_data_v1
        )

        # 2. Configure the upsert node to target a non-existent version (v2)
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "new_version_data",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {
                        "is_versioned": True,
                        "operation": StoreOperation.UPSERT_VERSIONED,
                        "version": version_name_v2, # Target the new version
                        "is_complete": False # Optional: mark new version as incomplete
                    }
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        print(f"output: {output.model_dump_json(indent=4)}")

        # Assert v2 was created
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, new_data_v2, version_to_check=version_name_v2)
        # Assert v1 still exists unchanged
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, initial_data_v1, version_to_check=version_name_v1)

        # Assert output path reflects initialization of v2
        self.assertEqual(output.paths_processed[0][:3], [self.test_namespace, doc_name, f"created_and_updated_version_{version_name_v2}"])





    # --- End of New UPSERT_VERSIONED Tests ---

    async def test_store_versioned_create_version_static_path(self):
        """Test creating a new version of an existing versioned document."""
        doc_name = self.test_docname_base + "versioned_new_ver"
        initial_data = {"value": 100}
        new_version_data = {"value": 150}
        input_data = {"new_data": new_version_data}
        new_version_name = "v2.0"

        # 1. Initialize
        await self.customer_data_service.initialize_versioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, initial_data=initial_data
        )

        # 2. Create Version Node
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "new_data",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {
                        "is_versioned": True,
                        "operation": "create_version",
                        "version": new_version_name,
                        "from_version": "default"
                    }
                }
            ]
        })
        await store_node.process(input_data, runtime_config=self.runtime_config_regular)

        # 3. Verify new version using helper
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, new_version_data, version_to_check=new_version_name)

        # 4. Verify default version using helper
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, initial_data, version_to_check="default")

    async def test_store_derive_path_from_item(self):
        """Test deriving namespace/docname from fields within the stored item."""
        input_data = {
            "item_to_store": {
                "meta_ns": "derived_ns",
                "meta_dn": "derived_dn_123",
                "payload": {"x": 1}
            }
        }
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "item_to_store",
                    "target_path": {
                        "filename_config": {
                            "input_namespace_field": "meta_ns",
                            "input_docname_field": "meta_dn"
                        }
                    },
                    "versioning": {
                        "is_versioned": False,
                        "operation": "upsert"
                    }
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        await self._assert_doc_exists("derived_ns", "derived_dn_123", is_shared=False, is_system=False, user=self.user_regular, expected_data=input_data["item_to_store"])

    async def test_store_list_derive_path_pattern(self):
        """Test storing a list of items with path derived from item patterns (explicit separate processing)."""
        input_data = {
            "item_list": [
                {"id": "A", "type": "widget", "value": 10},
                {"id": "B", "type": "gadget", "value": 20},
                {"id": "C", "type": "widget", "value": 30},
            ]
        }
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "item_list",
                    "target_path": {
                        "filename_config": {
                            "namespace_pattern": "items_{item[type]}",
                            "docname_pattern": "{item[id]}_{index}"
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"},
                    # EXPLICITLY SET to True, overriding the new None default
                    "process_list_items_separately": True
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 3)
        await self._assert_doc_exists("items_widget", "A_0", False, False, self.user_regular, input_data["item_list"][0])
        await self._assert_doc_exists("items_gadget", "B_1", False, False, self.user_regular, input_data["item_list"][1])
        await self._assert_doc_exists("items_widget", "C_2", False, False, self.user_regular, input_data["item_list"][2])

    async def test_store_system_entity_superuser(self):
        """Test storing a system entity as superuser."""
        doc_name = self.test_docname_base + "system"
        input_data = {"system_config": {"param": "value"}}
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "system_config",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "is_system_entity": True, # Explicitly set
                    "is_shared": True, # System entities often shared
                    "versioning": {"is_versioned": False, "operation": "upsert"}
                }
            ]
        })
        await store_node.process(input_data, runtime_config=self.runtime_config_superuser)
        await self._assert_doc_exists(self.test_namespace, doc_name, is_shared=True, is_system=True, user=self.user_superuser, expected_data=input_data["system_config"])

    async def test_store_system_entity_forbidden(self):
        """Test storing a system entity fails for non-superuser."""
        doc_name = self.test_docname_base + "system_forbidden"
        input_data = {"system_config": {"param": "value"}}
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "system_config",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "is_system_entity": True,
                    "versioning": {"is_versioned": False, "operation": "upsert"}
                }
            ]
        })
        await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        # Assert document does NOT exist
        with self.assertRaises(Exception): # Expect some kind of failure/not found
             await self.customer_data_service.get_unversioned_document(
                 org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
                 is_shared=False, user=self.user_regular, is_system_entity=True
             )

    # --- Load Node Tests ---

    async def test_load_unversioned_static_path(self):
        """Test loading a simple unversioned document."""
        doc_name = self.test_docname_base + "load_unversioned"
        doc_data = {"data": "abc", "id": 1}
        output_field_name = "loaded_doc"
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, data=doc_data
        )
        load_node = self._get_load_node({
            "load_paths": [
                {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    },
                    "output_field_name": output_field_name
                }
            ]
        })

        # Define and set the expected dynamic output schema for this test
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadUnversionedStaticOutput",
            [(output_field_name, Dict[str, Any], None)] # Field is required
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel # Override instance schema

        # Run the node
        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        # Assertions on the output instance (which should be of ExpectedOutputModel type)
        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertTrue(hasattr(output, output_field_name))
        self.assertEqual(getattr(output, output_field_name), doc_data)
        self.assertEqual(output.output_metadata, {})

    async def test_load_versioned_specific_version(self):
        """Test loading a specific version of a versioned document."""
        doc_name = self.test_docname_base + "load_versioned_spec"
        data_v1 = {"v": 1}
        data_v2 = {"v": 2}
        output_field_name = "doc_v2"
        await self.customer_data_service.initialize_versioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, initial_version="v1", initial_data=data_v1
        )
        await self.customer_data_service.create_versioned_document_version(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, new_version="v2", from_version="v1"
        )
        await self.customer_data_service.update_versioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, data=data_v2, version="v2"
        )

        load_node = self._get_load_node({
            "load_paths": [
                {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    },
                    "output_field_name": output_field_name,
                    "version_config": {"version": "v2"}
                }
            ]
        })

        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadVersionedSpecificOutput",
            [(output_field_name, Dict[str, Any], None)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertTrue(hasattr(output, output_field_name))
        self.assertEqual(getattr(output, output_field_name), data_v2)
        self.assertEqual(output.output_metadata, {})

    async def test_load_derive_path_from_input(self):
        """Test loading where the path details come from input data."""
        doc_name = self.test_docname_base + "load_derived"
        doc_data = {"content": "derived_load"}
        output_field_name = "loaded_item"
        input_data = {"source_info": {"ns": self.test_namespace, "dn": doc_name}}
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, data=doc_data
        )

        load_node = self._get_load_node({
            "load_paths": [
                {
                    "filename_config": {
                        "input_namespace_field": "source_info.ns",
                        "input_docname_field": "source_info.dn"
                    },
                    "output_field_name": output_field_name
                }
            ]
        })

        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadDerivedPathOutput",
            [(output_field_name, Dict[str, Any], None)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process(input_data, runtime_config=self.runtime_config_regular)

        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertTrue(hasattr(output, output_field_name))
        self.assertEqual(getattr(output, output_field_name), doc_data)
        self.assertEqual(output.output_metadata, {})

    async def test_load_shared(self):
        """Test loading a shared document."""
        doc_name = self.test_docname_base + "load_shared"
        doc_data = {"shared_val": 99}
        output_field_name = "shared_loaded"
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=True, user=self.user_regular, data=doc_data
        )

        load_node = self._get_load_node({
            "load_paths": [
                {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    },
                    "output_field_name": output_field_name,
                    "is_shared": True
                }
            ]
        })

        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadSharedOutput",
            [(output_field_name, Dict[str, Any], None)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertTrue(hasattr(output, output_field_name))
        self.assertEqual(getattr(output, output_field_name), doc_data)
        self.assertEqual(output.output_metadata, {})

    async def test_load_system_entity_superuser(self):
        """Test loading a system entity as superuser."""
        doc_name = self.test_docname_base + "load_system"
        doc_data = {"system_param": True}
        output_field_name = "system_loaded"
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=True, user=self.user_superuser, data=doc_data, is_system_entity=True
        )

        load_node = self._get_load_node({
            "load_paths": [
                {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    },
                    "output_field_name": output_field_name,
                    "is_system_entity": True,
                    "is_shared": True
                }
            ]
        })

        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadSystemSuperuserOutput",
            [(output_field_name, Dict[str, Any], None)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process({}, runtime_config=self.runtime_config_superuser)

        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertTrue(hasattr(output, output_field_name))
        self.assertEqual(getattr(output, output_field_name), doc_data)
        self.assertEqual(output.output_metadata, {})

    async def test_load_system_entity_regular_user_shared_allowed(self):
        """Test loading a SHARED system entity as a regular user (should be allowed)."""
        doc_name = self.test_docname_base + "load_system_shared"
        doc_data = {"public_system_info": "ok"}
        output_field_name = "system_shared_loaded"
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=True, user=self.user_superuser, data=doc_data, is_system_entity=True
        )

        load_node = self._get_load_node({
            "load_paths": [
                {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    },
                    "output_field_name": output_field_name,
                    "is_system_entity": True,
                    "is_shared": True
                }
            ]
        })

        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadSystemSharedRegularOutput",
            [(output_field_name, Dict[str, Any], None)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertTrue(hasattr(output, output_field_name))
        self.assertEqual(getattr(output, output_field_name), doc_data)
        self.assertEqual(output.output_metadata, {})

    async def test_load_non_existent(self):
        """Test loading a document that does not exist."""
        doc_name = self.test_docname_base + "non_existent"
        output_field_name = "should_not_exist"
        load_node = self._get_load_node({
            "load_paths": [
                {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    },
                    "output_field_name": output_field_name
                }
            ]
        })

        # Define the expected model, making the field optional
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadNonExistentOutput",
            [(output_field_name, Optional[Dict[str, Any]], None)] # Expect Optional[Dict[str, Any]], defaults to None
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        # Assertions on the output instance
        self.assertIsInstance(output, ExpectedOutputModel)
        # Check that the field was NOT populated (should have default value if defined, None here)
        self.assertFalse(hasattr(output, output_field_name) and getattr(output, output_field_name) is not None, f"Field '{output_field_name}' should not be populated.")
        self.assertTrue(hasattr(output, 'output_metadata'))
        self.assertEqual(output.output_metadata, {})

    async def test_load_with_schema(self):
        """Test loading a versioned document and its schema."""
        doc_name = self.test_docname_base + "load_with_schema"
        doc_data = {"field": "value"}
        doc_schema = {"type": "object", "properties": {"field": {"type": "string"}}}
        output_field_name = "doc_with_schema"
        await self.customer_data_service.initialize_versioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular,
            initial_data=doc_data,
            schema_definition=doc_schema
        )

        load_node = self._get_load_node({
            "load_paths": [
                {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    },
                    "output_field_name": output_field_name,
                    "schema_options": {"load_schema": True}
                }
            ]
        })

        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadWithSchemaOutput",
            [(output_field_name, Dict[str, Any], None)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertTrue(hasattr(output, output_field_name))
        self.assertEqual(getattr(output, output_field_name), doc_data)
        # Check metadata for the loaded schema
        self.assertIn(output_field_name, output.output_metadata)
        self.assertIn("schema", output.output_metadata[output_field_name])
        self.assertEqual(output.output_metadata[output_field_name]["schema"], doc_schema)

    # --- Advanced Load/Store Tests ---

    async def test_load_multiple_paths(self):
        """Test loading multiple documents (versioned, unversioned, shared) in one node."""
        # 1. Setup data
        doc_name_unv = self.test_docname_base + "multi_unv"
        data_unv = {"type": "unversioned"}
        output_field_unv = "loaded_unversioned"
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name_unv,
            is_shared=False, user=self.user_regular, data=data_unv
        )

        doc_name_ver = self.test_docname_base + "multi_ver"
        data_ver = {"type": "versioned", "v": "1.0"}
        output_field_ver = "loaded_versioned"
        await self.customer_data_service.initialize_versioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name_ver,
            is_shared=False, user=self.user_regular, initial_version="v1.0", initial_data=data_ver
        )

        doc_name_shared = self.test_docname_base + "multi_shared"
        data_shared = {"type": "shared"}
        output_field_shared = "loaded_shared"
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name_shared,
            is_shared=True, user=self.user_regular, data=data_shared # Regular user creates shared
        )

        # 2. Configure Load Node
        load_node = self._get_load_node({
            "load_paths": [
                { # Unversioned
                    "filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name_unv},
                    "output_field_name": output_field_unv
                },
                { # Versioned (specific version)
                    "filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name_ver},
                    "output_field_name": output_field_ver,
                    "version_config": {"version": "v1.0"}
                },
                { # Shared
                    "filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name_shared},
                    "output_field_name": output_field_shared,
                    "is_shared": True
                }
            ]
        })

        # 3. Define Expected Output Schema
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadMultiplePathsOutput",
            [
                (output_field_unv, Dict[str, Any], ...),
                (output_field_ver, Dict[str, Any], ...),
                (output_field_shared, Dict[str, Any], ...)
            ]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        # 4. Run and Assert
        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertEqual(getattr(output, output_field_unv), data_unv)
        self.assertEqual(getattr(output, output_field_ver), data_ver)
        self.assertEqual(getattr(output, output_field_shared), data_shared)
        self.assertEqual(output.output_metadata, {})


    async def test_store_complex_data_types(self):
        """Test storing a document with various complex data types."""
        doc_name = self.test_docname_base + "complex_types"
        complex_data = {
            "a_list": [1, "two", True, None, {"nested_key": 3.14}],
            "a_nested_dict": {
                "bool_val": False,
                "int_val": 100,
                "float_val": 99.9,
                "null_val": None,
                "sub_list": [4, 5, 6]
            },
            "a_bool": True,
            "a_number": 123.456,
            "a_string": "String with spaces and symbols!@#$%^&*()"
        }
        input_data = {"complex_doc": complex_data}
        store_node = self._get_store_node({
            "store_configs": [{
                "input_field_path": "complex_doc",
                "target_path": {"filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name}},
                "versioning": {"is_versioned": False, "operation": "upsert"}
            }]
        })

        await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, complex_data)

    async def test_load_complex_data_types(self):
        """Test loading a document with complex data types."""
        doc_name = self.test_docname_base + "complex_types_load"
        output_field = "loaded_complex"
        complex_data = {
            "top_level_list": ["a", 1, None],
            "nested": {"key": "value", "num": 1.23}
        }
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, data=complex_data
        )

        load_node = self._get_load_node({
            "load_paths": [{
                "filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name},
                "output_field_name": output_field
            }]
        })
        ExpectedOutputModel = self._get_dynamic_load_output_cls("LoadComplexOutput", [(output_field, Dict[str, Any], ...)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertEqual(getattr(output, output_field), complex_data)

    async def test_store_invalid_operation_versioned(self):
        """Test that attempting 'upsert' on a versioned path configuration fails validation."""
        doc_name = self.test_docname_base + "invalid_op_ver"
        # Attempt to configure store node with UPSERT on versioned=True
        with self.assertRaisesRegex(ValueError, "Operation 'upsert' is only valid for unversioned documents"):
            self._get_store_node({
                "store_configs": [{
                    "input_field_path": "data",
                    "target_path": {"filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name}},
                    "versioning": {"is_versioned": True, "operation": "upsert"} # Invalid combination
                }]
            })

    async def test_store_create_version_invalid_from(self):
        """Test creating a new version from a non-existent source version fails."""
        doc_name = self.test_docname_base + "invalid_from_ver"
        initial_data = {"v": 0}
        new_version_data = {"v": 1}
        input_data = {"new_data": new_version_data}
        new_version_name = "v2.0"
        non_existent_from_version = "v_non_existent"

        # 1. Initialize with 'default' version
        await self.customer_data_service.initialize_versioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, initial_data=initial_data
        )

        # 2. Configure Store Node to create from non-existent version
        store_node = self._get_store_node({
            "store_configs": [{
                "input_field_path": "new_data",
                "target_path": {"filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name}},
                "versioning": {
                    "is_versioned": True,
                    "operation": "create_version",
                    "version": new_version_name,
                    "from_version": non_existent_from_version # Invalid 'from'
                }
            }]
        })
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "StoreWithSchemaOutput",
            cur__class=StoreCustomerDataOutput
            # [(output_field_name, Dict[str, Any], None)]
        )
        store_node.__class__.output_schema_cls = ExpectedOutputModel
        # 3. Process and expect failure (likely within _store_single_document logging error)
        # The node process itself might not raise, but the underlying service call should fail.
        # We check that the new version was NOT created.
        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(output.paths_processed, []) # Expect empty list as operation failed

        # Assert the intended new version does not exist
        with self.assertRaises(Exception): # Expect service call to fail or return None/error
            await self.customer_data_service.get_versioned_document(
                org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
                is_shared=False, user=self.user_regular, version=new_version_name
            )
        # Assert default version still exists
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, initial_data, version_to_check="default")


    async def test_store_update_nonexistent_version(self):
        """Test updating a specific version that doesn't exist fails."""
        doc_name = self.test_docname_base + "update_nonexistent_ver"
        initial_data = {"v": "original"}
        update_data = {"v": "updated"}
        input_data = {"update_doc": update_data}
        non_existent_version = "v_missing"

        # 1. Initialize with 'default' version
        await self.customer_data_service.initialize_versioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, initial_data=initial_data
        )

        # 2. Configure Store Node to update a non-existent version
        store_node = self._get_store_node({
            "store_configs": [{
                "input_field_path": "update_doc",
                "target_path": {"filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name}},
                "versioning": {
                    "is_versioned": True,
                    "operation": "update",
                    "version": non_existent_version # Version that doesn't exist
                }
            }]
        })
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "StoreWithSchemaOutput",
            cur__class=StoreCustomerDataOutput
            # [(output_field_name, Dict[str, Any], None)]
        )
        store_node.__class__.output_schema_cls = ExpectedOutputModel
        # 3. Process and expect failure
        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(output.paths_processed, []) # Expect empty list

        # Assert the default version was NOT updated
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, initial_data, version_to_check="default")


    async def test_load_path_resolution_fallback(self):
        """Test loading where path info is resolved from full input data (fallback)."""
        doc_name = self.test_docname_base + "load_fallback"
        doc_data = {"content": "fallback_load"}
        output_field_name = "loaded_fallback"
        # Path info is OUTSIDE the 'item' structure (if we imagined loading an item)
        input_data = {
            "path_details": {"ns": self.test_namespace, "dn": doc_name},
            "some_other_data": {} # Placeholder for where an item might normally be
        }
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, data=doc_data
        )

        load_node = self._get_load_node({
            "load_paths": [{
                "filename_config": {
                    "input_namespace_field": "path_details.ns", # Points to top-level input
                    "input_docname_field": "path_details.dn"  # Points to top-level input
                },
                "output_field_name": output_field_name
            }]
        })

        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadFallbackPathOutput",
            [(output_field_name, Dict[str, Any], ...)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process(input_data, runtime_config=self.runtime_config_regular)

        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertTrue(hasattr(output, output_field_name))
        self.assertEqual(getattr(output, output_field_name), doc_data)

    async def test_store_path_resolution_fallback(self):
        """Test storing where path info is resolved from full input data (fallback)."""
        doc_name = self.test_docname_base + "store_fallback"
        doc_data = {"content": "fallback_store"}
        # Path info is OUTSIDE the item being stored
        input_data = {
            "path_details": {"ns": self.test_namespace, "dn": doc_name},
            "item_to_store": doc_data
        }

        store_node = self._get_store_node({
            "store_configs": [{
                "input_field_path": "item_to_store", # The actual data to store
                "target_path": {
                    "filename_config": {
                        "input_namespace_field": "path_details.ns", # Points to top-level input
                        "input_docname_field": "path_details.dn"  # Points to top-level input
                    }
                },
                "versioning": {"is_versioned": False, "operation": "upsert"}
            }]
        })
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "StoreWithSchemaOutput",
            cur__class=StoreCustomerDataOutput
            # [(output_field_name, Dict[str, Any], None)]
        )
        store_node.__class__.output_schema_cls = ExpectedOutputModel
        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertNotEqual(output.paths_processed, []) # Check if store reported success

        await self._assert_doc_exists(self.test_namespace, doc_name, is_shared=False, is_system=False, user=self.user_regular, expected_data=doc_data)


    async def test_store_with_schema_association(self):
        """Test storing a versioned document and associating a schema definition."""
        doc_name = self.test_docname_base + "store_with_schema"
        doc_data = {"field": "value", "optional_field": None}
        doc_schema = {
            "type": "object",
            "properties": {
                "field": {"type": "string"},
                "optional_field": {"type": ["string", "null"]}
            },
            "required": ["field"]
        }
        input_data = {"doc_with_schema": doc_data}
        version_name = "v1_schema"

        store_node = self._get_store_node({
            "store_configs": [{
                "input_field_path": "doc_with_schema",
                "target_path": {"filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name}},
                "versioning": {"is_versioned": True, "operation": "initialize", "version": version_name},
                "schema_options": {"schema_definition": doc_schema} # Associate schema directly
            }]
        })

        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "StoreWithSchemaOutput",
            cur__class=StoreCustomerDataOutput
            # [(output_field_name, Dict[str, Any], None)]
        )
        store_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertNotEqual(output.paths_processed, [])

        # Verify document exists
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, doc_data, version_to_check=version_name)

        # Verify schema was stored (using service directly)
        stored_schema = await self.customer_data_service.get_versioned_document_schema(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, is_system_entity=False
        )
        self.assertEqual(stored_schema, doc_schema)


    async def test_load_non_existent_optional_field(self):
        """Test loading a non-existent doc results in default value (None) for an Optional output field."""
        doc_name = self.test_docname_base + "non_existent_optional"
        output_field_name = "optional_missing_doc"

        load_node = self._get_load_node({
            "load_paths": [{
                "filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name},
                "output_field_name": output_field_name
            }]
        })

        # Define the expected model, making the field Optional explicitly
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadNonExistentOptionalOutput",
            # Explicitly Optional[Dict], defaulting to None
            [(output_field_name, Optional[Dict[str, Any]], None)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        # Assertions on the output instance
        self.assertIsInstance(output, ExpectedOutputModel)
        # Check the field exists due to the schema definition, but its value is None
        self.assertTrue(hasattr(output, output_field_name))
        self.assertIsNone(getattr(output, output_field_name), f"Field '{output_field_name}' should be None.")
        self.assertEqual(output.output_metadata, {})


    # --- On Behalf Of User ID Tests --- #

    async def test_store_on_behalf_of_superuser_success(self):
        """Test superuser storing a user-specific doc on behalf of another user."""
        doc_name = self.test_docname_base + "on_behalf_store_su" + str(self.test_target_user_id)
        target_user_id_str = str(self.test_target_user_id)
        doc_data = {"owner": target_user_id_str, "value": "stored by superuser"}
        input_data = {"on_behalf_data": doc_data}

        store_node = self._get_store_node({
            "store_configs": [{
                "input_field_path": "on_behalf_data",
                "target_path": {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    }
                },
                "is_shared": False, # User-specific doc
                "on_behalf_of_user_id": target_user_id_str, # Specify target user
                "versioning": {"is_versioned": False, "operation": "upsert"}
            }]
        })
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "StoreOnBehalfSuperuserOutput",
            cur__class=StoreCustomerDataOutput
        )
        store_node.__class__.output_schema_cls = ExpectedOutputModel

        # Run with SUPERUSER context
        output = await store_node.process(input_data, runtime_config=self.runtime_config_superuser)

        # Assert the operation succeeded in the output
        self.assertEqual(len(output.paths_processed), 1)
        self.assertEqual(output.paths_processed[0][0], self.test_namespace)
        self.assertEqual(output.paths_processed[0][1], doc_name)

        # Assert document exists and is owned by the TARGET user
        # Use the superuser to verify existence, as the target user might not exist
        # in the auth system for a direct service call check.
        try:
            fetched_data = await self.customer_data_service.get_unversioned_document(
                org_id=self.test_org_id,
                namespace=self.test_namespace,
                docname=doc_name,
                is_shared=False,
                user=self.user_superuser, # Use superuser to read
                on_behalf_of_user_id=self.test_target_user_id # Specify target user for path
            )
            self.assertEqual(fetched_data, doc_data)
        except Exception as e:
            self.fail(f"Failed to fetch document stored on behalf of target user: {e}")

    async def test_store_on_behalf_of_regular_user_fail(self):
        """Test regular user fails to store user-specific doc on behalf of another user."""
        doc_name = self.test_docname_base + "on_behalf_store_reg_fail"
        target_user_id_str = str(self.test_target_user_id)
        doc_data = {"value": "should not be stored"}
        input_data = {"failed_on_behalf": doc_data}

        store_node = self._get_store_node({
            "store_configs": [{
                "input_field_path": "failed_on_behalf",
                "target_path": {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    }
                },
                "is_shared": False,
                "on_behalf_of_user_id": target_user_id_str, # Attempt on behalf of
                "versioning": {"is_versioned": False, "operation": "upsert"}
            }]
        })
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "StoreOnBehalfRegularFailOutput",
            cur__class=StoreCustomerDataOutput
        )
        store_node.__class__.output_schema_cls = ExpectedOutputModel

        # Run with REGULAR USER context
        # Use assertLogs to check for the specific error message from the node
        # with self.assertLogs(level='ERROR') as log_cm:
        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)

        # Assert the operation failed (no paths processed)
        self.assertEqual(output.paths_processed, [])

        # Assert the log message indicates permission error
        # self.assertTrue(any(f"User '{self.user_regular.id}' is not a superuser and cannot use 'on_behalf_of_user_id'" in msg for msg in log_cm.output))

        # Assert document does NOT exist (check as superuser on behalf of target)
        with self.assertRaises(Exception): # Expect some kind of failure/not found
            await self.customer_data_service.get_unversioned_document(
                org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
                is_shared=False, user=self.user_superuser, on_behalf_of_user_id=self.test_target_user_id
            )

    async def test_store_shared_on_behalf_of_superuser_ignored(self):
        """Test superuser storing SHARED doc with on_behalf_of_user_id (should be ignored)."""
        doc_name = self.test_docname_base + "on_behalf_shared_ignored"
        target_user_id_str = str(self.test_target_user_id)
        doc_data = {"value": "shared, on behalf ignored"}
        input_data = {"shared_on_behalf": doc_data}

        store_node = self._get_store_node({
            "store_configs": [{
                "input_field_path": "shared_on_behalf",
                "target_path": {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    }
                },
                "is_shared": True, # SHARED document
                "on_behalf_of_user_id": target_user_id_str, # This should be ignored by service
                "versioning": {"is_versioned": False, "operation": "upsert"}
            }]
        })
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "StoreSharedOnBehalfIgnoredOutput",
            cur__class=StoreCustomerDataOutput
        )
        store_node.__class__.output_schema_cls = ExpectedOutputModel

        # Run with SUPERUSER context
        output = await store_node.process(input_data, runtime_config=self.runtime_config_superuser)

        # Assert the operation succeeded
        self.assertEqual(len(output.paths_processed), 1)

        # Assert document exists and IS SHARED (not user-specific to target)
        await self._assert_doc_exists(self.test_namespace, doc_name, is_shared=True, is_system=False, user=self.user_superuser, expected_data=doc_data)

        # Double-check it's not user-specific to the target user
        with self.assertRaises(Exception): # Expect not found
            await self.customer_data_service.get_unversioned_document(
                org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
                is_shared=False, user=self.user_superuser, on_behalf_of_user_id=self.test_target_user_id
            )

    async def test_load_on_behalf_of_superuser_success(self):
        """Test superuser loading a user-specific doc on behalf of another user."""
        doc_name = self.test_docname_base + "on_behalf_load_su" + str(self.test_target_user_id)
        target_user_id_str = str(self.test_target_user_id)
        doc_data = {"owner": target_user_id_str, "value": "loaded by superuser on behalf"}
        output_field_name = "loaded_target_doc"

        # Setup: Store data as the target user (using superuser on behalf of)
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_superuser, data=doc_data, on_behalf_of_user_id=self.test_target_user_id
        )

        load_node = self._get_load_node({
            "load_paths": [{
                "filename_config": {
                    "static_namespace": self.test_namespace,
                    "static_docname": doc_name
                },
                "output_field_name": output_field_name,
                "is_shared": False, # User-specific doc
                "on_behalf_of_user_id": target_user_id_str # Specify target user
            }]
        })
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadOnBehalfSuperuserOutput",
            [(output_field_name, Dict[str, Any], ...)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        # Run with SUPERUSER context
        output = await load_node.process({}, runtime_config=self.runtime_config_superuser)

        # Assertions
        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertTrue(hasattr(output, output_field_name))
        self.assertEqual(getattr(output, output_field_name), doc_data)

    async def test_load_on_behalf_of_regular_user_fail(self):
        """Test regular user fails to load user-specific doc on behalf of another user."""
        doc_name = self.test_docname_base + "on_behalf_load_reg_fail"
        target_user_id_str = str(self.test_target_user_id)
        doc_data = {"value": "should not be loaded by regular user"}
        output_field_name = "failed_load"

        # Setup: Store data as the target user (using superuser on behalf of)
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_superuser, data=doc_data, on_behalf_of_user_id=self.test_target_user_id
        )

        load_node = self._get_load_node({
            "load_paths": [{
                "filename_config": {
                    "static_namespace": self.test_namespace,
                    "static_docname": doc_name
                },
                "output_field_name": output_field_name,
                "is_shared": False,
                "on_behalf_of_user_id": target_user_id_str # Attempt on behalf of
            }]
        })
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadOnBehalfRegularFailOutput",
            [(output_field_name, Optional[Dict[str, Any]], None)] # Expect optional field
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        # Run with REGULAR USER context and check logs
        # with self.assertLogs(level='ERROR') as log_cm:
        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        # Assertions
        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertFalse(hasattr(output, output_field_name) and getattr(output, output_field_name) is not None, f"Field '{output_field_name}' should not be populated.")
        self.assertEqual(output.output_metadata, {})
        # self.assertTrue(any(f"User '{self.user_regular.id}' is not a superuser and cannot use 'on_behalf_of_user_id'" in msg for msg in log_cm.output))

    async def test_load_shared_on_behalf_of_superuser_ignored(self):
        """Test superuser loading SHARED doc with on_behalf_of_user_id (should be ignored)."""
        doc_name = self.test_docname_base + "on_behalf_load_shared_ignored"
        target_user_id_str = str(self.test_target_user_id)
        doc_data = {"value": "shared, load on behalf ignored"}
        output_field_name = "shared_on_behalf_load"

        # Setup: Store shared data
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=True, user=self.user_superuser, data=doc_data
        )

        load_node = self._get_load_node({
            "load_paths": [{
                "filename_config": {
                    "static_namespace": self.test_namespace,
                    "static_docname": doc_name
                },
                "output_field_name": output_field_name,
                "is_shared": True, # Load SHARED
                "on_behalf_of_user_id": target_user_id_str # Should be ignored
            }]
        })
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadSharedOnBehalfIgnoredOutput",
            [(output_field_name, Dict[str, Any], ...)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        # Run with SUPERUSER context
        output = await load_node.process({}, runtime_config=self.runtime_config_superuser)

        # Assertions - successfully loaded the shared doc
        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertTrue(hasattr(output, output_field_name))
        self.assertEqual(getattr(output, output_field_name), doc_data)

    # --- End On Behalf Of User ID Tests --- #

    # --- Load/Store Interaction Tests --- #

    async def test_store_derive_path_input_field_pattern(self):
        """Test deriving path using patterns based on data from a specific input field."""
        input_data = {
            "path_metadata": {
                "category": "logs",
                "source_system": "system_A",
                "id": "run_123"
            },
            "log_entry": {
                "timestamp": "2024-01-01T10:00:00Z",
                "message": "Process started."
            }
        }
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "log_entry", # Data to store
                    "target_path": {
                        "filename_config": {
                            # Use data from path_metadata to generate path
                            "input_namespace_field": "path_metadata",
                            "input_namespace_field_pattern": "{item[category]}/{item[source_system]}",
                            "input_docname_field": "path_metadata",
                            "input_docname_field_pattern": "{item[id]}"
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"}
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 1)
        # Verify using the expected derived path
        await self._assert_doc_exists(
            namespace="logs/system_A",
            docname="run_123",
            is_shared=False,
            is_system=False,
            user=self.user_regular,
            expected_data=input_data["log_entry"]
        )

    async def test_store_list_derive_path_input_field_pattern(self):
        """Test storing list items using patterns based on common input metadata (explicit separate processing)."""
        input_data = {
            "batch_info": {
                "job_id": "batch_XYZ",
                "data_type": "metrics"
            },
            "metric_items": [
                {"metric_name": "cpu_usage", "value": 0.75, "instance": "web_1"},
                {"metric_name": "memory_usage", "value": 0.50, "instance": "db_1"},
                {"metric_name": "cpu_usage", "value": 0.65, "instance": "web_2"},
            ]
        }
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "metric_items", # List to store
                    "target_path": {
                        "filename_config": {
                            # Use batch_info for namespace
                            "input_namespace_field": "batch_info",
                            "input_namespace_field_pattern": "{item[data_type]}/{item[job_id]}",
                            # Use the *item being processed* for docname (different pattern type)
                            "docname_pattern": "{item[metric_name]}_{item[instance]}"
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"},
                    # EXPLICITLY SET to True
                    "process_list_items_separately": True
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 3)
        expected_ns = "metrics/batch_XYZ"
        # import ipdb; ipdb.set_trace()
        await self._assert_doc_exists(expected_ns, "cpu_usage_web_1", False, False, self.user_regular, input_data["metric_items"][0])
        await self._assert_doc_exists(expected_ns, "memory_usage_db_1", False, False, self.user_regular, input_data["metric_items"][1])
        await self._assert_doc_exists(expected_ns, "cpu_usage_web_2", False, False, self.user_regular, input_data["metric_items"][2])

    async def test_store_derive_path_input_field_pattern_key_error(self):
        """Test storing with input field pattern fails if key is missing in source data."""
        input_data = {
            "path_metadata": {
                "category": "results" # Missing 'source_system' needed by pattern
            },
            "result_data": {"score": 100}
        }
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "result_data",
                    "target_path": {
                        "filename_config": {
                            "input_namespace_field": "path_metadata",
                            "input_namespace_field_pattern": "{item[category]}/{item[source_system]}", # Will cause KeyError
                            "input_docname_field": "path_metadata.category",
                            "input_docname_field_pattern": "{item}" # Simpler pattern for docname
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"}
                }
            ]
        })

        # with self.assertLogs(level='ERROR') as log_cm:
        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)

        # Assert the operation failed (no paths processed)
        self.assertEqual(output.paths_processed, [])
        # Assert the log message indicates a KeyError during formatting
        # self.assertTrue(any("Error formatting input_namespace_field_pattern" in msg for msg in log_cm.output))
        # self.assertTrue(any("Key 'source_system' not found" in msg for msg in log_cm.output))


    async def test_load_derive_path_input_field_pattern(self):
        """Test loading a document where path is derived from input field patterns."""
        # 1. Prepare data to be loaded
        expected_ns = "config/global"
        expected_dn = "settings_prod"
        doc_data = {"theme": "dark", "feature_flags": ["new_ui", "beta_feature"]}
        output_field = "loaded_config"
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=expected_ns, docname=expected_dn,
            is_shared=True, user=self.user_superuser, data=doc_data # Store as shared by superuser
        )

        # 2. Prepare input data for the load node
        input_data = {
            "load_params": {
                "environment": "prod",
                "config_type": "global"
            }
        }

        # 3. Configure Load Node with input field patterns
        load_node = self._get_load_node({
            "load_paths": [
                {
                    "filename_config": {
                        "input_namespace_field": "load_params",
                        "input_namespace_field_pattern": "config/{item[config_type]}",
                        "input_docname_field": "load_params",
                        "input_docname_field_pattern": "settings_{item[environment]}"
                    },
                    "output_field_name": output_field,
                    "is_shared": True # Load the shared document
                }
            ]
        })

        # 4. Define Expected Output Schema
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadInputFieldPatternOutput",
            [(output_field, Dict[str, Any], ...)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        # 5. Run and Assert
        # Regular user can load shared data
        output = await load_node.process(input_data, runtime_config=self.runtime_config_regular)

        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertTrue(hasattr(output, output_field))
        self.assertEqual(getattr(output, output_field), doc_data)


    # --- End of New Tests for input_*_field_pattern --- #

    async def test_store_shared(self):
        """Test storing a shared document."""
        doc_name = self.test_docname_base + "shared"
        input_data = {"shared_data": {"config": "global"}}
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "shared_data",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "is_shared": True, # Explicitly set
                    "versioning": {"is_versioned": False, "operation": "upsert"}
                }
            ]
        })
        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        await self._assert_doc_exists(self.test_namespace, doc_name, is_shared=True, is_system=False, user=self.user_regular, expected_data=input_data["shared_data"])

    async def test_store_primitive_string(self):
        """Test storing a simple string value."""
        doc_name = self.test_docname_base + "primitive_string"
        input_string = "This is a test string."
        input_data = {"my_string": input_string}
        target_ns = self.test_namespace
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "my_string",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": target_ns,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"}
                    # process_list_items_separately is irrelevant here
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 1)
        await self._assert_doc_exists(
            target_ns, doc_name, False, False, self.user_regular,
            expected_data=input_string # Expect the string itself to be stored
        )

    async def test_store_primitive_integer(self):
        """Test storing a simple integer value."""
        doc_name = self.test_docname_base + "primitive_int"
        input_integer = 12345
        input_data = {"my_int": input_integer}
        target_ns = self.test_namespace
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "my_int",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": target_ns,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"}
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 1)
        await self._assert_doc_exists(
            target_ns, doc_name, False, False, self.user_regular,
            expected_data=input_integer # Expect the integer itself
        )

    async def test_store_list_of_primitives_as_single_document(self):
        """Test storing a list of primitives (int, str) as a single document."""
        doc_name = self.test_docname_base + "list_primitives_single"
        input_list = [1, "two", 3, True, None, 4.5]
        input_data = {"primitive_list": input_list}
        target_ns = self.test_namespace

        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "primitive_list",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": target_ns,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"},
                    "process_list_items_separately": False # Store the list as one doc
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 1)
        await self._assert_doc_exists(
            target_ns, doc_name, False, False, self.user_regular,
            expected_data=input_list # Expect the list itself
        )

    async def test_store_list_of_primitives_separately(self):
        """Test storing list of primitives with process_separately=True."""
        doc_name_base = self.test_docname_base + "list_primitives_sep"
        input_list = [10, 20, 30]
        input_data = {"primitive_list_sep": input_list}
        target_ns = self.test_namespace

        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "primitive_list_sep",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": target_ns,
                            # Path resolution won't use item data here, so it won't fail,
                            # but the warning about non-dict items should appear.
                            "docname_pattern": f"{doc_name_base}_{{index}}"
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"},
                    "process_list_items_separately": True # Try to process separately
                }
            ]
        })

        # with self.assertLogs(level='WARNING') as log_cm:
        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)

        # Expect 3 successful stores because path resolution didn't fail
        self.assertEqual(len(output.paths_processed), 3)

        # # Check that warnings were logged about non-dict items
        # self.assertTrue(any(f"is not a dictionary (Type: <class 'int'>)" in msg for msg in log_cm.output),
        #                 f"Expected warning about non-dict items not found in logs: {log_cm.output}")

        # Verify documents were stored (containing the primitives)
        await self._assert_doc_exists(target_ns, f"{doc_name_base}_0", False, False, self.user_regular, expected_data=10)
        await self._assert_doc_exists(target_ns, f"{doc_name_base}_1", False, False, self.user_regular, expected_data=20)
        await self._assert_doc_exists(target_ns, f"{doc_name_base}_2", False, False, self.user_regular, expected_data=30)

    # --- End On Behalf Of User ID Tests --- #

    # --- Dynamic Config Loading Tests --- #

    async def test_load_configs_from_input_single(self):
        """Test loading a single LoadPathConfig dynamically from input data."""
        # 1. Prepare data to be loaded
        doc_name = self.test_docname_base + "dynamic_load_single"
        doc_data = {"dynamic_key": "value_single"}
        output_field = "loaded_dynamic_doc"
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, data=doc_data
        )

        # 2. Prepare input data containing the load configuration
        load_config_dict = {
            "filename_config": {
                "static_namespace": self.test_namespace,
                "static_docname": doc_name
            },
            "output_field_name": output_field
        }
        input_data = {
            "my_load_config": load_config_dict
        }

        # 3. Configure Load Node to use dynamic config path
        load_node = self._get_load_node({
            # Note: load_paths is intentionally omitted/None
            "load_configs_input_path": "my_load_config" # Path to the config in input_data
        })

        # 4. Define Expected Output Schema
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadDynamicSingleConfigOutput",
            [(output_field, Dict[str, Any], ...)]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        # 5. Run and Assert
        output = await load_node.process(input_data, runtime_config=self.runtime_config_regular)

        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertTrue(hasattr(output, output_field))
        self.assertEqual(getattr(output, output_field), doc_data)
        self.assertEqual(output.output_metadata, {})

    async def test_load_configs_from_input_list(self):
        """Test loading multiple LoadPathConfig objects dynamically from a list in input data."""
        # 1. Prepare data
        doc_name1 = self.test_docname_base + "dynamic_load_list_1"
        data1 = {"id": 1, "val": "A"}
        output1 = "doc1"
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name1,
            is_shared=False, user=self.user_regular, data=data1
        )
        doc_name2_shared = self.test_docname_base + "dynamic_load_list_2_shared"
        data2 = {"id": 2, "val": "B"}
        output2 = "doc2_shared"
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name2_shared,
            is_shared=True, user=self.user_regular, data=data2
        )

        # 2. Prepare input data with list of configs
        load_configs_list = [
            {
                "filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name1},
                "output_field_name": output1
            },
            {
                "filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name2_shared},
                "output_field_name": output2,
                "is_shared": True
            }
        ]
        input_data = {
            "load_config_array": load_configs_list
        }

        # 3. Configure Load Node
        load_node = self._get_load_node({
            "load_configs_input_path": "load_config_array"
        })

        # 4. Define Expected Output Schema
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadDynamicListConfigOutput",
            [
                (output1, Dict[str, Any], ...),
                (output2, Dict[str, Any], ...)
            ]
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        # 5. Run and Assert
        output = await load_node.process(input_data, runtime_config=self.runtime_config_regular)

        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertEqual(getattr(output, output1), data1)
        self.assertEqual(getattr(output, output2), data2)
        self.assertEqual(output.output_metadata, {})

    async def test_load_configs_from_input_invalid_path(self):
        """Test load node handles invalid dynamic config path gracefully."""
        load_node = self._get_load_node({
            "load_configs_input_path": "non_existent_path"
        })
        ExpectedOutputModel = self._get_dynamic_load_output_cls("LoadInvalidPathOutput", [])
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        input_data = {"some_other_key": "value"}

        with self.assertLogs(level="ERROR") as log_cm:
            output = await load_node.process(input_data, runtime_config=self.runtime_config_regular)

        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertEqual(output.model_dump(), {"loaded_fields": [], "output_metadata": {}}) # Expect empty output
        self.assertTrue(any("Input path \'non_existent_path\' for load configs not found" in msg for msg in log_cm.output))

    async def test_load_configs_from_input_invalid_data(self):
        """Test load node handles invalid data at dynamic config path gracefully."""
        input_data = {
            "invalid_config_data": "just a string, not a config"
        }
        load_node = self._get_load_node({
            "load_configs_input_path": "invalid_config_data"
        })
        ExpectedOutputModel = self._get_dynamic_load_output_cls("LoadInvalidDataOutput", [])
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        with self.assertLogs(level="ERROR") as log_cm:
            output = await load_node.process(input_data, runtime_config=self.runtime_config_regular)

        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertEqual(output.model_dump(), {"loaded_fields": [], "output_metadata": {}})
        self.assertTrue(any("is not a valid list or object for load configurations" in msg for msg in log_cm.output))

    async def test_store_configs_from_input_single(self):
        """Test storing data based on a single StoreConfig dynamically loaded from input."""
        # 1. Prepare data to store and the config in input
        doc_name = self.test_docname_base + "dynamic_store_single"
        doc_data = {"payload": "dynamic_store_test"}
        store_config_dict = {
            "input_field_path": "data_to_save",
            "target_path": {
                "filename_config": {
                    "static_namespace": self.test_namespace,
                    "static_docname": doc_name
                }
            },
            "versioning": {"is_versioned": False, "operation": "upsert"}
        }
        input_data = {
            "my_store_config": store_config_dict,
            "data_to_save": doc_data
        }

        # 2. Configure Store Node
        store_node = self._get_store_node({
            # Note: store_configs is intentionally omitted/None
            "store_configs_input_path": "my_store_config" # Path to the config
        })

        # 3. Run and Assert Store Operation
        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)

        # Assert output indicates success
        self.assertEqual(len(output.paths_processed), 1)
        self.assertEqual(output.paths_processed[0][0], self.test_namespace)
        self.assertEqual(output.paths_processed[0][1], doc_name)

        # Assert document was actually stored
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, doc_data)

    async def test_store_configs_from_input_list(self):
        """Test storing multiple items based on a list of StoreConfig objects from input."""
        # 1. Prepare data and configs
        doc_name1 = self.test_docname_base + "dynamic_store_list_1"
        data1 = {"item": 1}
        doc_name2 = self.test_docname_base + "dynamic_store_list_2"
        data2 = {"item": 2, "shared": True}

        store_configs_list = [
            { # Config for item 1 (user-specific)
                "input_field_path": "items_to_save.0", # Index into the list
                "target_path": {"filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name1}},
                "versioning": {"is_versioned": False, "operation": "upsert"},
                "is_shared": False
            },
            { # Config for item 2 (shared)
                "input_field_path": "items_to_save.1",
                "target_path": {"filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name2}},
                "versioning": {"is_versioned": False, "operation": "upsert"},
                "is_shared": True
            }
        ]
        input_data = {
            "store_config_definitions": store_configs_list,
            "items_to_save": [data1, data2]
        }

        # 2. Configure Store Node
        store_node = self._get_store_node({
            "store_configs_input_path": "store_config_definitions"
        })

        # 3. Run and Assert
        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)

        # Assert output indicates success for both
        self.assertEqual(len(output.paths_processed), 2)
        self.assertIn([self.test_namespace, doc_name1, "upsert_unversioned (created: True)"], [p[:3] for p in output.paths_processed])
        self.assertIn([self.test_namespace, doc_name2, "upsert_unversioned (created: True)"], [p[:3] for p in output.paths_processed])

        # Assert documents were stored correctly
        await self._assert_doc_exists(self.test_namespace, doc_name1, False, False, self.user_regular, data1)
        await self._assert_doc_exists(self.test_namespace, doc_name2, True, False, self.user_regular, data2)

    async def test_store_configs_from_input_invalid_path(self):
        """Test store node handles invalid dynamic config path gracefully."""
        store_node = self._get_store_node({
            "store_configs_input_path": "path_does_not_exist"
        })
        input_data = {"data_to_save": {"a": 1}}

        with self.assertLogs(level="ERROR") as log_cm:
            output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)

        self.assertEqual(output.paths_processed, []) # Expect no paths processed
        self.assertTrue(any("Input path \'path_does_not_exist\' for store configs not found" in msg for msg in log_cm.output))

    async def test_store_configs_from_input_invalid_data(self):
        """Test store node handles invalid data at dynamic config path gracefully."""
        input_data = {
            "bad_config": {"not_a_valid": "store_config"},
            "data_to_save": {"b": 2}
        }
        store_node = self._get_store_node({
            "store_configs_input_path": "bad_config"
        })

        with self.assertLogs(level="ERROR") as log_cm:
            output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)

        self.assertEqual(output.paths_processed, [])
        # Check for Pydantic validation error message
        self.assertTrue(any("Validation error parsing store configuration(s)" in msg for msg in log_cm.output))

    def test_load_config_validation_both_sources_fail(self):
        """Test LoadCustomerDataConfig validation fails if both static and dynamic sources provided."""
        with self.assertRaisesRegex(ValueError, "Provide either \'load_paths\' or \'load_configs_input_path\', not both."):
            LoadCustomerDataConfig(
                load_paths=[{"filename_config": {"static_namespace": "a", "static_docname": "b"}, "output_field_name": "c"}],
                load_configs_input_path="some.path"
            )

    def test_store_config_validation_both_sources_fail(self):
        """Test StoreCustomerDataConfig validation fails if both static and dynamic sources provided."""
        with self.assertRaisesRegex(ValueError, "Provide either \'store_configs\' or \'store_configs_input_path\', not both."):
            StoreCustomerDataConfig(
                store_configs=[{"input_field_path": "d", "target_path": {"filename_config": {"static_namespace": "e", "static_docname": "f"}}}],
                store_configs_input_path="other.path"
            )

    # --- End Dynamic Config Loading Tests --- #

    # --- Load/Store Interaction Tests --- #

    async def test_load_multiple_paths_overlapping_output_field(self):
        """Test loading multiple documents into the same output field, resulting in a list."""
        # 1. Setup data for two separate documents
        doc_name_1 = self.test_docname_base + "overlap_1"
        data_1 = {"id": "doc1", "value": 100}
        output_field = "combined_docs" # The overlapping field name
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name_1,
            is_shared=False, user=self.user_regular, data=data_1
        )

        doc_name_2 = self.test_docname_base + "overlap_2"
        data_2 = {"id": "doc2", "value": 200}
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name_2,
            is_shared=False, user=self.user_regular, data=data_2
        )

        # 2. Configure Load Node with overlapping output fields
        load_node = self._get_load_node({
            "load_paths": [
                { # Load doc 1
                    "filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name_1},
                    "output_field_name": output_field # Same output field
                },
                { # Load doc 2
                    "filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name_2},
                    "output_field_name": output_field # Same output field
                }
            ]
        })

        # 3. Define Expected Output Schema - expecting a list for the overlapping field
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadOverlappingOutput",
            # The field should contain a list of dictionaries
            [(output_field, List[Dict[str, Any]], ...)] # Required field (...)
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        # 4. Run and Assert
        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertTrue(hasattr(output, output_field))
        loaded_data = getattr(output, output_field)
        self.assertIsInstance(loaded_data, list)
        self.assertEqual(len(loaded_data), 2)
        # Check if both documents are present in the list (order might vary)
        self.assertIn(data_1, loaded_data)
        self.assertIn(data_2, loaded_data)
        self.assertEqual(output.output_metadata, {})

    async def test_load_multiple_paths_overlapping_output_field_one_missing(self):
        """Test loading into overlapping field when one document is missing."""
        # 1. Setup data for one document
        doc_name_1 = self.test_docname_base + "overlap_missing_1"
        data_1 = {"id": "doc1_exists", "value": 100}
        output_field = "combined_some_missing"
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name_1,
            is_shared=False, user=self.user_regular, data=data_1
        )

        # Document 2 does NOT exist
        doc_name_2_missing = self.test_docname_base + "overlap_missing_2"

        # 2. Configure Load Node
        load_node = self._get_load_node({
            "load_paths": [
                { # Load existing doc 1
                    "filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name_1},
                    "output_field_name": output_field
                },
                { # Attempt to load non-existent doc 2
                    "filename_config": {"static_namespace": self.test_namespace, "static_docname": doc_name_2_missing},
                    "output_field_name": output_field
                }
            ]
        })

        # 3. Define Expected Output Schema - still expect a list, potentially with only one item
        ExpectedOutputModel = self._get_dynamic_load_output_cls(
            "LoadOverlappingOneMissingOutput",
            # Field is still a list, but might be shorter or empty if none found
            [(output_field, List[Dict[str, Any]], ...)] # Still required, but list might be len 1
        )
        load_node.__class__.output_schema_cls = ExpectedOutputModel

        # 4. Run and Assert
        output = await load_node.process({}, runtime_config=self.runtime_config_regular)

        self.assertIsInstance(output, ExpectedOutputModel)
        self.assertTrue(hasattr(output, output_field))
        loaded_data = getattr(output, output_field)
        self.assertIsInstance(loaded_data, list)
        # Only the existing document should be in the list
        self.assertEqual(len(loaded_data), 1)
        self.assertIn(data_1, loaded_data)
        self.assertEqual(output.output_metadata, {})

    # --- End Load/Store Interaction Tests --- #

    # --- Tests for Extra Fields and UUID Generation Features --- #

    async def test_store_with_extra_fields_simple(self):
        """Test storing a document with extra fields from input data."""
        doc_name = self.test_docname_base + "extra_fields_simple"
        doc_data = {"original": "value"}
        extra_value = "extra_value_from_input"
        input_data = {
            "doc_to_store": doc_data,
            "metadata": {
                "extra_field": extra_value
            }
        }
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "doc_to_store",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"},
                    "extra_fields": [
                        {
                            "src_path": "metadata.extra_field",
                            "dst_path": "added_field"  # Custom destination path
                        }
                    ]
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 1)

        # Expected data should have the extra field added
        expected_data = {"original": "value", "added_field": extra_value}
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, expected_data)

    async def test_store_with_extra_fields_default_dst_path(self):
        """Test storing with extra fields using default destination path (last segment of src_path)."""
        doc_name = self.test_docname_base + "extra_fields_default_dst"
        doc_data = {"original": "content"}
        input_data = {
            "doc_to_store": doc_data,
            "context": {
                "timestamp": "2023-01-01T12:00:00Z"
            }
        }
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "doc_to_store",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"},
                    "extra_fields": [
                        {
                            "src_path": "context.timestamp"
                            # No dst_path - should default to "timestamp"
                        }
                    ]
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 1)

        # Expected data should have the timestamp field added using default dst path
        expected_data = {"original": "content", "timestamp": "2023-01-01T12:00:00Z"}
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, expected_data)

    async def test_store_with_extra_fields_nested_paths(self):
        """Test storing with extra fields using nested source and destination paths."""
        doc_name = self.test_docname_base + "extra_fields_nested"
        doc_data = {"level1": {"level2": "original"}}
        input_data = {
            "doc_to_store": doc_data,
            "deep": {
                "nested": {
                    "source": "nested_value"
                }
            }
        }
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "doc_to_store",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"},
                    "extra_fields": [
                        {
                            "src_path": "deep.nested.source",
                            "dst_path": "new.nested.field"  # Deep nesting in target
                        }
                    ]
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 1)

        # Expected data with the nested field structure created
        expected_data = {
            "level1": {"level2": "original"},
            "new": {"nested": {"field": "nested_value"}}
        }
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, expected_data)

    async def test_store_with_extra_fields_list_skipped(self):
        """Test that list values at source paths are skipped as per requirements."""
        doc_name = self.test_docname_base + "extra_fields_skip_list"
        doc_data = {"original": "data"}
        input_data = {
            "doc_to_store": doc_data,
            "metadata": {
                "scalar_field": "scalar_value",
                "list_field": [1, 2, 3]  # This should be skipped
            }
        }
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "doc_to_store",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"},
                    "extra_fields": [
                        {
                            "src_path": "metadata.scalar_field",
                            "dst_path": "scalar"
                        },
                        {
                            "src_path": "metadata.list_field",
                            "dst_path": "list_value"  # This shouldn't be added
                        }
                    ]
                }
            ]
        })

        # Using assertLogs to check for the warning about skipping list values
        with self.assertLogs(level='WARNING') as log_cm:
            output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        
        self.assertEqual(len(output.paths_processed), 1)
        
        # Expected data should only have the scalar field added, not the list
        expected_data = {"original": "data", "scalar": "scalar_value"}
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, expected_data)
        
        # Check log for warning about skipping list value
        self.assertTrue(any("resolves to a list, skipping as per requirements" in msg for msg in log_cm.output))

    async def test_store_with_global_extra_fields(self):
        """Test storing with extra fields defined in the global config."""
        doc_name = self.test_docname_base + "global_extra_fields"
        doc_data = {"doc": "content"}
        input_data = {
            "doc_to_store": doc_data,
            "global_meta": "global_value"
        }
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "doc_to_store",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"}
                    # No extra_fields here - using global config
                }
            ],
            "global_extra_fields": [
                {
                    "src_path": "global_meta",
                    "dst_path": "global_field"
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 1)

        # Expected data should have the global extra field
        expected_data = {"doc": "content", "global_field": "global_value"}
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, expected_data)

    async def test_store_extra_fields_override_global(self):
        """Test that config-specific extra fields override global extra fields."""
        doc_name = self.test_docname_base + "override_extra_fields"
        doc_data = {"doc": "base"}
        input_data = {
            "doc_to_store": doc_data,
            "global_value": "from_global",
            "specific_value": "from_specific"
        }
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "doc_to_store",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"},
                    "extra_fields": [
                        {
                            "src_path": "specific_value",
                            "dst_path": "added_field"
                        }
                    ]
                }
            ],
            "global_extra_fields": [
                {
                    "src_path": "global_value",
                    "dst_path": "added_field"  # Same destination, should be overridden
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 1)

        # Expected data should have the specific value, not the global one
        expected_data = {"doc": "base", "added_field": "from_specific"}
        await self._assert_doc_exists(self.test_namespace, doc_name, False, False, self.user_regular, expected_data)

    async def test_store_with_generate_uuid_dict(self):
        """Test UUID generation for dictionary objects."""
        doc_name = self.test_docname_base + "uuid_dict"
        doc_data = {"original": "content"}
        input_data = {"doc_to_store": doc_data}
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "doc_to_store",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"},
                    "generate_uuid": True  # Enable UUID generation
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 1)

        # Retrieve the stored document
        fetched_data = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular
        )

        # Verify it has the original content plus a UUID field
        self.assertEqual(fetched_data["original"], "content")
        self.assertTrue("uuid" in fetched_data, "UUID field should be present")
        self.assertTrue(isinstance(fetched_data["uuid"], str), "UUID should be a string")
        try:
            uuid_obj = uuid.UUID(fetched_data["uuid"])
            self.assertTrue(uuid_obj.version == 4, "Should be a valid UUIDv4")
        except ValueError:
            self.fail("UUID is not a valid UUID string")

    async def test_store_with_generate_uuid_primitive(self):
        """Test UUID generation for primitive/non-dict objects (should be wrapped)."""
        doc_name = self.test_docname_base + "uuid_primitive"
        simple_value = "simple string value"
        input_data = {"primitive_to_store": simple_value}
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "primitive_to_store",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"},
                    "generate_uuid": True  # Enable UUID generation
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 1)

        # Retrieve the stored document
        fetched_data = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular
        )

        # Verify it's a wrapper with uuid and data fields
        self.assertTrue("uuid" in fetched_data, "UUID field should be present")
        self.assertTrue("data" in fetched_data, "Data field should be present")
        self.assertEqual(fetched_data["data"], simple_value, "Original data should be in 'data' field")
        self.assertTrue(isinstance(fetched_data["uuid"], str), "UUID should be a string")
        try:
            uuid.UUID(fetched_data["uuid"])  # Validate UUID format
        except ValueError:
            self.fail("UUID is not a valid UUID string")

    async def test_store_with_uuid_in_filename(self):
        """Test UUID generation with _uuid_ placeholder in filename."""
        doc_data = {"content": "with_uuid_filename"}
        input_data = {"doc_to_store": doc_data}
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "doc_to_store",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "docname_pattern": f"{self.test_docname_base}_{{_uuid_}}"  # Using _uuid_ placeholder
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"},
                    "generate_uuid": True  # Enable UUID generation
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 1)
        
        # Extract the generated docname from the result
        namespace, docname, _ = output.paths_processed[0][:3]
        
        # Verify the document exists with expected content
        fetched_data = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=namespace, docname=docname,
            is_shared=False, user=self.user_regular
        )
        
        # Verify it has a UUID field and the original content
        self.assertEqual(fetched_data["content"], "with_uuid_filename")
        self.assertTrue("uuid" in fetched_data, "UUID field should be present")
        
        # Most importantly, verify the UUID in the docname matches the UUID in the document
        # Extract the UUID part from the docname
        prefix = f"{self.test_docname_base}_"
        docname_uuid = docname[len(prefix):]
        
        # Check that it's the same UUID used in the document
        self.assertEqual(docname_uuid, fetched_data["uuid"], 
                        "UUID in filename should match UUID in document")
    
    async def test_store_with_uuid_in_filename_in_static_docname(self):
        """Test UUID generation with _uuid_ placeholder in filename."""
        doc_data = {"content": "with_uuid_filename"}
        input_data = {"doc_to_store": doc_data}
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "doc_to_store",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": f"{self.test_docname_base}_{{_uuid_}}"  # Using _uuid_ placeholder
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"},
                    "generate_uuid": True  # Enable UUID generation
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 1)
        
        # Extract the generated docname from the result
        namespace, docname, _ = output.paths_processed[0][:3]
        
        # Verify the document exists with expected content
        fetched_data = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=namespace, docname=docname,
            is_shared=False, user=self.user_regular
        )
        
        # Verify it has a UUID field and the original content
        self.assertEqual(fetched_data["content"], "with_uuid_filename")
        self.assertTrue("uuid" in fetched_data, "UUID field should be present")
        
        # Most importantly, verify the UUID in the docname matches the UUID in the document
        # Extract the UUID part from the docname
        prefix = f"{self.test_docname_base}_"
        docname_uuid = docname[len(prefix):]
        
        # Check that it's the same UUID used in the document
        self.assertEqual(docname_uuid, fetched_data["uuid"], 
                        "UUID in filename should match UUID in document")

    async def test_store_with_uuid_filename_placeholder_no_generate(self):
        """Test filename with _uuid_ placeholder when generate_uuid is False (should use different UUIDs)."""
        doc_data = {"content": "separate_uuids"}
        input_data = {"doc_to_store": doc_data}
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "doc_to_store",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "docname_pattern": f"{self.test_docname_base}_{{_uuid_}}"  # Using _uuid_ placeholder
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"},
                    "generate_uuid": False  # UUID not generated for document
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 1)
        
        # Extract the generated docname from the result
        namespace, docname, _ = output.paths_processed[0][:3]
        
        # Verify the document exists with expected content
        fetched_data = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=namespace, docname=docname,
            is_shared=False, user=self.user_regular
        )
        
        # Verify the original content is intact
        self.assertEqual(fetched_data["content"], "separate_uuids")
        
        # Verify document does NOT have a uuid field
        self.assertFalse("uuid" in fetched_data, "Document should not have a UUID field")
        
        # Verify the filename contains a UUID format
        prefix = f"{self.test_docname_base}_"
        docname_uuid = docname[len(prefix):]
        
        # Check that it's a valid UUID
        try:
            uuid.UUID(docname_uuid)
        except ValueError:
            self.fail("UUID in filename is not valid")

    async def test_store_with_global_generate_uuid(self):
        """Test UUID generation using global setting."""
        doc_name = self.test_docname_base + "global_uuid"
        doc_data = {"content": "global_uuid_test"}
        input_data = {"doc_to_store": doc_data}
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "doc_to_store",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"}
                    # No generate_uuid here - using global config
                }
            ],
            "global_generate_uuid": True  # Global setting for UUID generation
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 1)

        # Retrieve the stored document
        fetched_data = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular
        )

        # Verify it has the content plus UUID
        self.assertEqual(fetched_data["content"], "global_uuid_test")
        self.assertTrue("uuid" in fetched_data, "UUID field should be present")
        self.assertTrue(isinstance(fetched_data["uuid"], str), "UUID should be a string")

    async def test_generate_uuid_override_global(self):
        """Test that config-specific generate_uuid overrides global setting."""
        doc_name = self.test_docname_base + "override_uuid"
        doc_data = {"content": "override_test"}
        input_data = {"doc_to_store": doc_data}
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "doc_to_store",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"},
                    "generate_uuid": False  # Explicitly disable, overriding global
                }
            ],
            "global_generate_uuid": True  # Global setting is enabled
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 1)

        # Retrieve the stored document
        fetched_data = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular
        )

        # Verify it does NOT have a UUID field because the specific config overrode global
        self.assertEqual(fetched_data["content"], "override_test")
        self.assertFalse("uuid" in fetched_data, "UUID field should NOT be present")

    async def test_store_with_combined_features(self):
        """Test combining extra fields and UUID generation."""
        doc_name = self.test_docname_base + "combined_features"
        doc_data = {"original": "data"}
        input_data = {
            "doc_to_store": doc_data,
            "metadata": {
                "timestamp": "2023-01-01T12:30:00Z"
            }
        }
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "doc_to_store",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"},
                    "generate_uuid": True,
                    "extra_fields": [
                        {
                            "src_path": "metadata.timestamp",
                            "dst_path": "created_at"
                        }
                    ]
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 1)

        # Retrieve the stored document
        fetched_data = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular
        )

        # Verify it has all expected fields
        self.assertEqual(fetched_data["original"], "data")
        self.assertEqual(fetched_data["created_at"], "2023-01-01T12:30:00Z")
        self.assertTrue("uuid" in fetched_data, "UUID field should be present")
        self.assertTrue(isinstance(fetched_data["uuid"], str), "UUID should be a string")

    async def test_store_list_with_uuid_and_extra_fields(self):
        """Test storing list items with both UUID generation and extra fields."""
        input_data = {
            "items": [
                {"id": "item1", "value": 10},
                {"id": "item2", "value": 20}
            ],
            "batch_info": {
                "batch_id": "batch_123",
                "created_by": "test_user"
            }
        }
        store_node = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "items",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "docname_pattern": f"{self.test_docname_base}_{{item[id]}}"
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"},
                    "process_list_items_separately": True,
                    "generate_uuid": True,
                    "extra_fields": [
                        {
                            "src_path": "batch_info.batch_id",
                            "dst_path": "batch_id"
                        },
                        {
                            "src_path": "batch_info.created_by", 
                            "dst_path": "processing.created_by"  # Test nested destination
                        }
                    ]
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        self.assertEqual(len(output.paths_processed), 2)

        # Expected fields for each item
        for i, item in enumerate(input_data["items"]):
            item_id = item["id"]
            docname = f"{self.test_docname_base}_{item_id}"
            
            # Retrieve the stored document
            fetched_data = await self.customer_data_service.get_unversioned_document(
                org_id=self.test_org_id, namespace=self.test_namespace, docname=docname,
                is_shared=False, user=self.user_regular
            )
            
            # Verify all expected fields
            self.assertEqual(fetched_data["id"], item_id)
            self.assertEqual(fetched_data["value"], item["value"])
            self.assertEqual(fetched_data["batch_id"], "batch_123")
            self.assertEqual(fetched_data["processing"]["created_by"], "test_user")
            self.assertTrue("uuid" in fetched_data, f"UUID field missing in item {i}")
            self.assertTrue(isinstance(fetched_data["uuid"], str), f"UUID not a string in item {i}")

    # --- End of Extra Fields and UUID Generation Tests --- #

    # --- Load/Store Interaction Tests --- #

    # --- UUID Generation During Updates Tests --- #

    async def test_store_update_add_uuid_when_missing(self):
        """Test that UUID is added when updating an object that doesn't have one."""
        # 1. Create initial document without UUID
        doc_name = self.test_docname_base + "add_uuid_on_update"
        initial_data = {"name": "test item", "value": 100}
        input_data_initial = {"initial_doc": initial_data}
        
        # Store without UUID generation first
        store_node_initial = self._get_store_node({
            "store_configs": [{
                "input_field_path": "initial_doc",
                "target_path": {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    }
                },
                "versioning": {"is_versioned": False, "operation": "upsert"},
                "generate_uuid": False  # Explicitly disable UUID
            }]
        })
        await store_node_initial.process(input_data_initial, runtime_config=self.runtime_config_regular)
        
        # Verify initial document doesn't have UUID
        initial_stored = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular
        )
        self.assertEqual(initial_stored, initial_data)
        self.assertNotIn("uuid", initial_stored, "Initial document should not have UUID")
        
        # 2. Update the document with UUID generation enabled
        update_data = {"name": "test item", "value": 200}  # Updated value
        input_data_update = {"update_doc": update_data}
        
        store_node_update = self._get_store_node({
            "store_configs": [{
                "input_field_path": "update_doc",
                "target_path": {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    }
                },
                "versioning": {"is_versioned": False, "operation": "upsert"},
                "generate_uuid": True  # Enable UUID generation
            }]
        })
        await store_node_update.process(input_data_update, runtime_config=self.runtime_config_regular)
        
        # 3. Verify UUID was added during update
        updated_stored = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular
        )
        self.assertEqual(updated_stored["name"], "test item")
        self.assertEqual(updated_stored["value"], 200)
        self.assertIn("uuid", updated_stored, "UUID should be added during update")
        self.assertTrue(isinstance(updated_stored["uuid"], str), "UUID should be a string")
        try:
            uuid_obj = uuid.UUID(updated_stored["uuid"])
            self.assertEqual(uuid_obj.version, 4, "Should be a valid UUIDv4")
        except ValueError:
            self.fail("UUID is not a valid UUID string")

    async def test_store_update_preserve_existing_uuid(self):
        """Test that an existing UUID is preserved when updating an object."""
        # 1. Create initial document with UUID
        doc_name = self.test_docname_base + "preserve_uuid"
        initial_data = {"name": "preserve test", "count": 5}
        input_data_initial = {"initial_doc": initial_data}
        
        store_node_initial = self._get_store_node({
            "store_configs": [{
                "input_field_path": "initial_doc",
                "target_path": {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    }
                },
                "versioning": {"is_versioned": False, "operation": "upsert"},
                "generate_uuid": True  # Generate UUID for initial document
            }]
        })
        await store_node_initial.process(input_data_initial, runtime_config=self.runtime_config_regular)
        
        # Get the initial document to capture the UUID
        initial_stored = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular
        )
        self.assertIn("uuid", initial_stored, "Initial document should have UUID")
        original_uuid = initial_stored["uuid"]
        
        # 2. Update the document with UUID generation still enabled
        update_data = {"name": "preserve test", "count": 10}  # Updated count
        input_data_update = {"update_doc": update_data}
        
        store_node_update = self._get_store_node({
            "store_configs": [{
                "input_field_path": "update_doc",
                "target_path": {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    }
                },
                "versioning": {"is_versioned": False, "operation": "upsert"},
                "generate_uuid": True  # Still enabled for update
            }]
        })
        await store_node_update.process(input_data_update, runtime_config=self.runtime_config_regular)
        
        # 3. Verify the UUID remained the same after update
        updated_stored = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular
        )
        self.assertEqual(updated_stored["name"], "preserve test")
        self.assertEqual(updated_stored["count"], 10)  # Verify update worked
        self.assertIn("uuid", updated_stored, "Updated document should still have UUID")
        self.assertEqual(updated_stored["uuid"], original_uuid, "UUID should be preserved during update")

    async def test_store_versioned_update_add_uuid_when_missing(self):
        """Test UUID generation for versioned documents when updating without existing UUID."""
        # 1. Create initial versioned document without UUID
        doc_name = self.test_docname_base + "versioned_add_uuid"
        version_name = "v1.0"
        initial_data = {"title": "Versioned Doc", "status": "draft"}
        
        # Initialize without UUID
        await self.customer_data_service.initialize_versioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, initial_version=version_name, 
            initial_data=initial_data
        )
        
        # Verify initial document doesn't have UUID
        initial_doc = await self.customer_data_service.get_versioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, version=version_name
        )
        self.assertNotIn("uuid", initial_doc, "Initial versioned document should not have UUID")
        
        # 2. Update with UUID generation enabled
        update_data = {"title": "Versioned Doc", "status": "updated"}
        input_data_update = {"versioned_update": update_data}
        
        store_node_update = self._get_store_node({
            "store_configs": [{
                "input_field_path": "versioned_update",
                "target_path": {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    }
                },
                "versioning": {
                    "is_versioned": True, 
                    "operation": "update",
                    "version": version_name
                },
                "generate_uuid": True  # Enable UUID generation
            }]
        })
        await store_node_update.process(input_data_update, runtime_config=self.runtime_config_regular)
        
        # 3. Verify UUID was added
        updated_doc = await self.customer_data_service.get_versioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, version=version_name
        )
        self.assertEqual(updated_doc["title"], "Versioned Doc")
        self.assertEqual(updated_doc["status"], "updated")
        self.assertIn("uuid", updated_doc, "UUID should be added to versioned document")
        self.assertTrue(isinstance(updated_doc["uuid"], str), "UUID should be a string")

    async def test_store_update_list_items_add_uuids(self):
        """Test adding UUIDs when updating a list of items where some already have UUIDs."""
        # 1. Create initial list of documents, some with and some without UUIDs
        namespace = self.test_namespace + "/uuid_list_update"
        
        # Item with UUID
        item1_id = "item_with_uuid"
        item1_data = {"id": item1_id, "value": 10, "uuid": str(uuid.uuid4())}
        
        # Item without UUID
        item2_id = "item_without_uuid"
        item2_data = {"id": item2_id, "value": 20}  # No UUID
        
        # Store initial items
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=namespace, docname=item1_id,
            is_shared=False, user=self.user_regular, data=item1_data
        )
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=namespace, docname=item2_id,
            is_shared=False, user=self.user_regular, data=item2_data
        )
        
        # 2. Update both items with updates to their values
        update_items = [
            {"id": item1_id, "value": 15},  # Update with new value, should preserve UUID
            {"id": item2_id, "value": 25}   # Update with new value, should add UUID
        ]
        input_data = {"items_to_update": update_items}
        
        # Store node for updating items
        store_node = self._get_store_node({
            "store_configs": [{
                "input_field_path": "items_to_update",
                "target_path": {
                    "filename_config": {
                        "static_namespace": namespace,
                        "input_docname_field": "id"  # Use item ID as document name
                    }
                },
                "versioning": {"is_versioned": False, "operation": "upsert"},
                "process_list_items_separately": True,
                "generate_uuid": True  # Enable UUID generation
            }]
        })
        await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        
        # 3. Verify results
        # Check item 1 - should have preserved its UUID
        updated_item1 = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=namespace, docname=item1_id,
            is_shared=False, user=self.user_regular
        )
        self.assertEqual(updated_item1["value"], 15)  # Value updated
        self.assertIn("uuid", updated_item1)  # Still has UUID
        self.assertEqual(updated_item1["uuid"], item1_data["uuid"])  # Same UUID as before
        
        # Check item 2 - should have gained a UUID
        updated_item2 = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=namespace, docname=item2_id,
            is_shared=False, user=self.user_regular
        )
        self.assertEqual(updated_item2["value"], 25)  # Value updated
        self.assertIn("uuid", updated_item2)  # Now has UUID
        self.assertTrue(isinstance(updated_item2["uuid"], str))  # Valid UUID string

    async def test_store_mixed_update_add_uuid_conditional(self):
        """Test UUID generation on multiple docs with a mix of creation and updates."""
        namespace = self.test_namespace + "/mixed_uuid_ops"
        
        # 1. Set up - create one document without UUID
        existing_doc_name = "existing_doc"
        existing_data = {"type": "existing", "counter": 1}
        
        await self.customer_data_service.create_or_update_unversioned_document(
            db=None, org_id=self.test_org_id, namespace=namespace, docname=existing_doc_name,
            is_shared=False, user=self.user_regular, data=existing_data
        )
        
        # Verify existing doc has no UUID
        initial_doc = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=namespace, docname=existing_doc_name,
            is_shared=False, user=self.user_regular
        )
        self.assertNotIn("uuid", initial_doc)
        
        # 2. Perform mixed operations - update existing doc and create new doc
        new_doc_name = "new_doc"
        update_doc_data = {"type": "existing", "counter": 2}  # Update existing
        new_doc_data = {"type": "new", "counter": 1}  # Create new
        
        input_data = {
            "update_item": update_doc_data,
            "new_item": new_doc_data
        }
        
        # Process update operation
        update_node = self._get_store_node({
            "store_configs": [{
                "input_field_path": "update_item",
                "target_path": {
                    "filename_config": {
                        "static_namespace": namespace,
                        "static_docname": existing_doc_name
                    }
                },
                "versioning": {"is_versioned": False, "operation": "upsert"},
                "generate_uuid": True
            }]
        })
        await update_node.process(input_data, runtime_config=self.runtime_config_regular)
        
        # Process creation operation
        create_node = self._get_store_node({
            "store_configs": [{
                "input_field_path": "new_item",
                "target_path": {
                    "filename_config": {
                        "static_namespace": namespace,
                        "static_docname": new_doc_name
                    }
                },
                "versioning": {"is_versioned": False, "operation": "upsert"},
                "generate_uuid": True
            }]
        })
        await create_node.process(input_data, runtime_config=self.runtime_config_regular)
        
        # 3. Verify both documents now have UUIDs
        updated_doc = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=namespace, docname=existing_doc_name,
            is_shared=False, user=self.user_regular
        )
        new_doc = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=namespace, docname=new_doc_name,
            is_shared=False, user=self.user_regular
        )
        
        # Updated doc should have UUID added
        self.assertEqual(updated_doc["counter"], 2)
        self.assertIn("uuid", updated_doc, "Updated document should have UUID added")
        
        # New doc should have UUID
        self.assertEqual(new_doc["counter"], 1)
        self.assertIn("uuid", new_doc, "Newly created document should have UUID")
        
        # UUIDs should be different
        self.assertNotEqual(updated_doc["uuid"], new_doc["uuid"], "Documents should have different UUIDs")

    # --- End of UUID Generation During Updates Tests --- #


        
    # --- Create Only Fields Tests --- #
    
    async def test_store_create_only_fields_basic(self):
        """
        Test basic create_only_fields functionality.
        
        Fields marked as create_only_fields should be:
        1. Included in the document during creation
        2. Preserved (not overwritten) during updates
        """
        # Create a document with create_only_fields
        doc_name = self.test_docname_base + "create_only_fields_basic"
        
        initial_data = {
            "title": "Test Document",
            "created_at": "2024-01-01T00:00:00Z",
            "created_by": "initial_user",
            "content": "Original content"
        }
        
        store_node_initial = self._get_store_node({
            "store_configs": [{
                "input_field_path": "doc",
                "target_path": {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    }
                },
                "versioning": {"is_versioned": False, "operation": "upsert"},
                "create_only_fields": ["created_at", "created_by"]
            }]
        })
        
        await store_node_initial.process({"doc": initial_data}, runtime_config=self.runtime_config_regular)
        
        # Verify the document was created with all fields
        initial_stored = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular
        )
        
        self.assertEqual(initial_stored["created_at"], "2024-01-01T00:00:00Z")
        self.assertEqual(initial_stored["created_by"], "initial_user")
        
        # Now update the document with different values for create_only_fields
        update_data = {
            "title": "Updated Title",
            "created_at": "2024-05-05T12:00:00Z",  # Different timestamp
            "created_by": "different_user",       # Different user
            "content": "Updated content"
        }
        
        store_node_update = self._get_store_node({
            "store_configs": [{
                "input_field_path": "doc",
                "target_path": {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    }
                },
                "versioning": {"is_versioned": False, "operation": "upsert"},
                "create_only_fields": ["created_at", "created_by"]
            }]
        })
        
        await store_node_update.process({"doc": update_data}, runtime_config=self.runtime_config_regular)
        
        # Verify the update: create-only fields should keep original values, others should be updated
        updated_stored = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular
        )
        
        # Create-only fields should retain original values
        self.assertEqual(updated_stored["created_at"], "2024-01-01T00:00:00Z", "Create-only field created_at should not change")
        self.assertEqual(updated_stored["created_by"], "initial_user", "Create-only field created_by should not change")
        
        # Regular fields should be updated
        self.assertEqual(updated_stored["title"], "Updated Title", "Regular field title should be updated")
        self.assertEqual(updated_stored["content"], "Updated content", "Regular field content should be updated")
    
    async def test_store_create_only_fields_missing_in_original(self):
        """
        Test keep_create_fields_if_missing parameter when original document lacks create-only fields.
        
        When keep_create_fields_if_missing=True, fields in create_only_fields should be added 
        even if the original document doesn't have them.
        
        When keep_create_fields_if_missing=False, fields in create_only_fields should only 
        be preserved if they already exist in the original document.
        """
        # Create initial document without the fields that will later be marked as create-only
        doc_name_keep = self.test_docname_base + "create_only_add_if_missing_true"
        doc_name_skip = self.test_docname_base + "create_only_add_if_missing_false"
        
        initial_data = {
            "title": "Original Document",
            "content": "Original content"
            # Note: No created_at or created_by fields
        }
        
        # Create two identical documents, one for each test case
        store_node_initial = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "doc",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name_keep
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"}
                },
                {
                    "input_field_path": "doc",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc_name_skip
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"}
                }
            ]
        })
        
        await store_node_initial.process({"doc": initial_data}, runtime_config=self.runtime_config_regular)
        
        # Update with keep_create_fields_if_missing=True (should add missing create-only fields)
        update_data_keep = {
            "title": "Updated Document",
            "content": "Updated content",
            "created_at": "2024-01-01T00:00:00Z",
            "created_by": "test_user"
        }
        
        store_node_update_keep = self._get_store_node({
            "store_configs": [{
                "input_field_path": "doc",
                "target_path": {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name_keep
                    }
                },
                "versioning": {"is_versioned": False, "operation": "upsert"},
                "create_only_fields": ["created_at", "created_by"],
                "keep_create_fields_if_missing": True
            }]
        })
        
        await store_node_update_keep.process({"doc": update_data_keep}, runtime_config=self.runtime_config_regular)
        
        # Update with keep_create_fields_if_missing=False (should not add missing create-only fields)
        update_data_skip = {
            "title": "Updated Document",
            "content": "Updated content",
            "created_at": "2024-01-01T00:00:00Z",
            "created_by": "test_user"
        }
        
        store_node_update_skip = self._get_store_node({
            "store_configs": [{
                "input_field_path": "doc",
                "target_path": {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name_skip
                    }
                },
                "versioning": {"is_versioned": False, "operation": "upsert"},
                "create_only_fields": ["created_at", "created_by"],
                "keep_create_fields_if_missing": False
            }]
        })
        
        await store_node_update_skip.process({"doc": update_data_skip}, runtime_config=self.runtime_config_regular)
        
        # Verify the results for keep_create_fields_if_missing=True
        updated_keep = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name_keep,
            is_shared=False, user=self.user_regular
        )
        
        # Should have added the missing create-only fields
        self.assertIn("created_at", updated_keep, "Missing create-only field should be added when keep_create_fields_if_missing=True")
        self.assertIn("created_by", updated_keep, "Missing create-only field should be added when keep_create_fields_if_missing=True")
        self.assertEqual(updated_keep["created_at"], "2024-01-01T00:00:00Z")
        self.assertEqual(updated_keep["created_by"], "test_user")
        
        # Verify the results for keep_create_fields_if_missing=False
        updated_skip = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name_skip,
            is_shared=False, user=self.user_regular
        )
        
        # Should not have added the missing create-only fields
        # self.assertNotIn("created_at", updated_skip, "Missing create-only field should not be added when keep_create_fields_if_missing=False")
        self.assertNotIn("created_by", updated_skip, "Missing create-only field should not be added when keep_create_fields_if_missing=False")
    
    async def test_store_create_only_fields_global_config(self):
        """
        Test global_create_only_fields applied to all store operations in a node.
        
        Global create-only fields should apply to all store operations unless 
        overridden at the individual store_config level.
        """
        # Create two documents, will update both with same node using global config
        doc1_name = self.test_docname_base + "global_create_only_1"
        doc2_name = self.test_docname_base + "global_create_only_2"
        
        # Initial documents with creation metadata
        doc1_initial = {
            "title": "Document 1",
            "content": "Content 1",
            "created_at": "2024-01-01T10:00:00Z",
            "created_by": "user_1"
        }
        
        doc2_initial = {
            "title": "Document 2",
            "content": "Content 2",
            "created_at": "2024-01-01T11:00:00Z",
            "created_by": "user_2"
        }
        
        # Store initial documents without create_only_fields
        store_node_initial = self._get_store_node({
            "store_configs": [
                {
                    "input_field_path": "doc1",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc1_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"}
                },
                {
                    "input_field_path": "doc2",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc2_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"}
                }
            ]
        })
        
        await store_node_initial.process(
            {"doc1": doc1_initial, "doc2": doc2_initial}, 
            runtime_config=self.runtime_config_regular
        )
        
        # Update documents using global_create_only_fields
        doc1_update = {
            "title": "Document 1 Updated",
            "content": "Updated content 1",
            "created_at": "2024-05-05T10:00:00Z",  # Changed creation timestamp
            "created_by": "new_user_1"            # Changed creator
        }
        
        doc2_update = {
            "title": "Document 2 Updated",
            "content": "Updated content 2",
            "created_at": "2024-05-05T11:00:00Z",  # Changed creation timestamp
            "created_by": "new_user_2"            # Changed creator
        }
        
        store_node_update = self._get_store_node({
            "global_create_only_fields": ["created_at", "created_by"],
            "global_keep_create_fields_if_missing": True,
            "store_configs": [
                {
                    "input_field_path": "doc1",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc1_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"}
                },
                {
                    "input_field_path": "doc2",
                    "target_path": {
                        "filename_config": {
                            "static_namespace": self.test_namespace,
                            "static_docname": doc2_name
                        }
                    },
                    "versioning": {"is_versioned": False, "operation": "upsert"}
                }
            ]
        })
        
        await store_node_update.process(
            {"doc1": doc1_update, "doc2": doc2_update}, 
            runtime_config=self.runtime_config_regular
        )
        
        # Verify both documents preserved their original create-only fields
        updated_doc1 = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc1_name,
            is_shared=False, user=self.user_regular
        )
        
        updated_doc2 = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc2_name,
            is_shared=False, user=self.user_regular
        )
        
        # Both documents should have preserved their original creation metadata
        self.assertEqual(updated_doc1["created_at"], "2024-01-01T10:00:00Z", "Global create_only_field should preserve original created_at")
        self.assertEqual(updated_doc1["created_by"], "user_1", "Global create_only_field should preserve original created_by")
        self.assertEqual(updated_doc2["created_at"], "2024-01-01T11:00:00Z", "Global create_only_field should preserve original created_at")
        self.assertEqual(updated_doc2["created_by"], "user_2", "Global create_only_field should preserve original created_by")
        
        # Other fields should be updated
        self.assertEqual(updated_doc1["title"], "Document 1 Updated")
        self.assertEqual(updated_doc1["content"], "Updated content 1")
        self.assertEqual(updated_doc2["title"], "Document 2 Updated")
        self.assertEqual(updated_doc2["content"], "Updated content 2")
    
    async def test_store_create_only_fields_config_override_global(self):
        """
        Test that store_config's create_only_fields overrides global_create_only_fields.
        
        Individual store_config's create_only_fields should take precedence over global settings.
        """
        doc_name = self.test_docname_base + "override_create_only"
        
        # Initial document with multiple metadata fields
        initial_data = {
            "title": "Test Document",
            "created_at": "2024-01-01T00:00:00Z",
            "created_by": "original_user",
            "timestamp": "2024-01-01T00:00:00Z",
            "version_num": 1
        }
        
        # Store initial document
        store_node_initial = self._get_store_node({
            "store_configs": [{
                "input_field_path": "doc",
                "target_path": {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    }
                },
                "versioning": {"is_versioned": False, "operation": "upsert"}
            }]
        })
        
        await store_node_initial.process({"doc": initial_data}, runtime_config=self.runtime_config_regular)
        
        # Update document with different global and specific create_only_fields
        update_data = {
            "title": "Updated Document",
            "created_at": "2024-05-05T12:00:00Z",  # Changed
            "created_by": "new_user",             # Changed
            "timestamp": "2024-05-05T12:00:00Z",  # Changed
            "version_num": 2                      # Changed
        }
        
        store_node_update = self._get_store_node({
            "global_create_only_fields": ["created_at", "created_by", "timestamp"],  # List of fields in global config
            "store_configs": [{
                "input_field_path": "doc",
                "target_path": {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    }
                },
                "versioning": {"is_versioned": False, "operation": "upsert"},
                "create_only_fields": ["created_at", "version_num"]  # Override - only these should be preserved
            }]
        })
        
        await store_node_update.process({"doc": update_data}, runtime_config=self.runtime_config_regular)
        
        # Verify that only the fields in the specific create_only_fields were preserved
        updated_stored = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular
        )
        
        # Fields in config's create_only_fields should be preserved
        self.assertEqual(updated_stored["created_at"], "2024-01-01T00:00:00Z", "Field in config create_only_fields should be preserved")
        self.assertEqual(updated_stored["version_num"], 1, "Field in config create_only_fields should be preserved")
        
        # Fields only in global_create_only_fields should be updated (since overridden by config)
        self.assertEqual(updated_stored["created_by"], "new_user", "Field only in global create_only_fields should be updated")
        self.assertEqual(updated_stored["timestamp"], "2024-05-05T12:00:00Z", "Field only in global create_only_fields should be updated")
    
    async def test_store_create_only_with_uuid_generation(self):
        """
        Test interaction between create_only_fields and UUID generation.
        
        When generate_uuid is true, the UUID field should be treated as a create_only_field
        and preserved across updates.
        """
        doc_name = self.test_docname_base + "uuid_with_create_only"
        
        # Create document with UUID generation
        initial_data = {
            "title": "UUID Test",
            "content": "Original content"
        }
        
        store_node_initial = self._get_store_node({
            "store_configs": [{
                "input_field_path": "doc",
                "target_path": {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    }
                },
                "versioning": {"is_versioned": False, "operation": "upsert"},
                "generate_uuid": True,  # Generate UUID
                "create_only_fields": ["created_at"],  # Additional create-only field
                "keep_create_fields_if_missing": True
            }]
        })
        
        # Initial storage with UUID generation
        await store_node_initial.process(
            {"doc": {**initial_data, "created_at": "2024-01-01T00:00:00Z"}}, 
            runtime_config=self.runtime_config_regular
        )
        
        # Fetch the generated document to capture the UUID
        initial_stored = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular
        )
        
        self.assertIn("uuid", initial_stored, "Document should have UUID field")
        self.assertIn("created_at", initial_stored, "Document should have created_at field")
        original_uuid = initial_stored["uuid"]
        
        # Update the document with a different UUID and created_at
        update_data = {
            "title": "Updated UUID Test",
            "content": "Updated content",
            "uuid": str(uuid.uuid4()),  # Different UUID
            "created_at": "2024-05-05T12:00:00Z"  # Different created_at
        }
        
        # Update using same configuration (should preserve both uuid and created_at)
        store_node_update = self._get_store_node({
            "store_configs": [{
                "input_field_path": "doc",
                "target_path": {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    }
                },
                "versioning": {"is_versioned": False, "operation": "upsert"},
                "generate_uuid": True,  # UUID generation still enabled
                "create_only_fields": ["created_at"],  # Same create-only field
                "keep_create_fields_if_missing": True
            }]
        })
        
        await store_node_update.process({"doc": update_data}, runtime_config=self.runtime_config_regular)
        
        # Verify that both UUID and created_at were preserved from the original
        updated_stored = await self.customer_data_service.get_unversioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular
        )
        
        self.assertEqual(updated_stored["uuid"], original_uuid, 
                         "UUID should be preserved as a create-only field when generate_uuid=True")
        self.assertEqual(updated_stored["created_at"], "2024-01-01T00:00:00Z", 
                         "create_at should be preserved as specified in create_only_fields")
        
        # Other fields should be updated
        self.assertEqual(updated_stored["title"], "Updated UUID Test")
        self.assertEqual(updated_stored["content"], "Updated content")
    
    async def test_store_versioned_with_create_only_fields(self):
        """
        Test create_only_fields with versioned documents.
        
        Create-only fields should be preserved during updates to versioned documents.
        """
        doc_name = self.test_docname_base + "versioned_create_only"
        version_name = "v1.0"
        
        # Create initial versioned document with creation metadata
        initial_data = {
            "title": "Versioned Document",
            "content": "Original content",
            "created_at": "2024-01-01T00:00:00Z",
            "created_by": "initial_user"
        }
        
        # Initialize versioned document
        await self.customer_data_service.initialize_versioned_document(
            db=None, org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, initial_version=version_name, 
            initial_data=initial_data
        )
        
        # Update the versioned document with create_only_fields
        update_data = {
            "title": "Updated Versioned Document",
            "content": "Updated content",
            "created_at": "2024-05-05T12:00:00Z",  # Changed
            "created_by": "new_user"               # Changed
        }
        
        store_node_update = self._get_store_node({
            "store_configs": [{
                "input_field_path": "doc",
                "target_path": {
                    "filename_config": {
                        "static_namespace": self.test_namespace,
                        "static_docname": doc_name
                    }
                },
                "versioning": {
                    "is_versioned": True, 
                    "operation": "update",
                    "version": version_name
                },
                "create_only_fields": ["created_at", "created_by"]
            }]
        })
        
        await store_node_update.process({"doc": update_data}, runtime_config=self.runtime_config_regular)
        
        # Verify that create-only fields were preserved in the versioned document
        updated_stored = await self.customer_data_service.get_versioned_document(
            org_id=self.test_org_id, namespace=self.test_namespace, docname=doc_name,
            is_shared=False, user=self.user_regular, version=version_name
        )
        
        # Create-only fields should have original values
        # self.assertEqual(updated_stored["created_at"], "2024-01-01T00:00:00Z", 
        #                  "Create-only field created_at should be preserved in versioned document")
        self.assertEqual(updated_stored["created_by"], "initial_user", 
                         "Create-only field created_by should be preserved in versioned document")
        
        # Other fields should be updated
        self.assertEqual(updated_stored["title"], "Updated Versioned Document")
        self.assertEqual(updated_stored["content"], "Updated content")
    
    # --- End of Create Only Fields Tests --- #
    

if __name__ == '__main__':
    unittest.main()
