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
    user_regular: MockUser
    user_superuser: MockUser
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

        self.user_regular = MockUser(id=self.test_user_id, is_superuser=False)
        self.user_superuser = MockUser(id=self.test_superuser_id, is_superuser=True)

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
            APPLICATION_CONTEXT_KEY: {
                "user": self.user_regular,
                "workflow_run_job": self.run_job_regular
            },
            EXTERNAL_CONTEXT_MANAGER_KEY: self.external_context
        }
        self.runtime_config_superuser = {
            APPLICATION_CONTEXT_KEY: {
                "user": self.user_superuser,
                "workflow_run_job": self.run_job_superuser
            },
            EXTERNAL_CONTEXT_MANAGER_KEY: self.external_context
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
        return StoreCustomerDataNode(config=node_config, node_id="test-store-node")

    def _get_load_node(self, config: Dict[str, Any]) -> LoadCustomerDataNode:
        """Instantiate LoadCustomerDataNode with given config."""
        node_config = LoadCustomerDataConfig(**config)
        return LoadCustomerDataNode(config=node_config, node_id="test-load-node")

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
        version_to_check: Optional[str] = None
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
        """Test storing a list of items with path derived from item patterns."""
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
                    "versioning": {"is_versioned": False, "operation": "upsert"}
                }
            ]
        })

        output = await store_node.process(input_data, runtime_config=self.runtime_config_regular)
        await self._assert_doc_exists("items_widget", "A_0", False, False, self.user_regular, input_data["item_list"][0])
        await self._assert_doc_exists("items_gadget", "B_1", False, False, self.user_regular, input_data["item_list"][1])
        await self._assert_doc_exists("items_widget", "C_2", False, False, self.user_regular, input_data["item_list"][2])

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


# Remove original TODO comment block
# ... existing code ...
# - Schema validation during store (if implemented in service)
# - Loading multiple paths in one node

if __name__ == '__main__':
    unittest.main()
