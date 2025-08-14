import asyncio
import logging
from uuid import UUID
from typing import Optional, Dict, Any, Union
from dataclasses import dataclass
from pydantic import BaseModel, Field

from kiwi_client.customer_data_client import CustomerDataTestClient
from kiwi_client.auth_client import AuthenticatedClient
from kiwi_client.schemas.workflow_api_schemas import CustomerDataVersionedUpsert, CustomerDataVersionedUpsertResponse

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class JSONSerializableCustomerDataVersionedUpsert(CustomerDataVersionedUpsert):
    """Custom wrapper that ensures model_dump always uses mode='json' for UUID serialization"""
    
    def model_dump(self, **kwargs):
        # Always use mode='json' to ensure UUID objects are serialized as strings
        kwargs['mode'] = 'json'
        return super().model_dump(**kwargs)


@dataclass
class DocumentConfig:
    """Configuration for document storage"""
    namespace: str
    docname: str
    is_shared: bool = False
    is_system_entity: bool = False
    version: str = "v1"
    schema_template_name: Optional[str] = None
    schema_template_version: Optional[str] = None


class SimpleDataUploader:
    """Simple, clean data uploader that takes config and data as input"""
    
    def __init__(self):
        self.client: Optional[CustomerDataTestClient] = None

    async def authenticate(self) -> None:
        """Authenticate with the service"""
        try:
            auth_client = await AuthenticatedClient().__aenter__()
            logger.info("Authenticated successfully.")
            self.client = CustomerDataTestClient(auth_client)
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise

    async def store_data_simple(
        self, 
        config: DocumentConfig, 
        data: Any,
        user_id: Optional[UUID] = None,
    ) -> Optional[CustomerDataVersionedUpsertResponse]:
        """
        Store data with simple configuration
        
        Args:
            config: DocumentConfig object with storage configuration
            data: The data to store (can be dict, list, string, etc.)
            user_id: Optional user ID (required for non-system entities)
        
        Returns:
            Response from the upsert operation or None if failed
        """
        if not self.client:
            await self.authenticate()

        try:
            # Prepare the upsert payload
            payload_data = {
                "version": config.version,
                "is_shared": config.is_shared,
                "data": data,
                "is_system_entity": config.is_system_entity,
                "schema_template_name": config.schema_template_name,
                "schema_template_version": config.schema_template_version,
                "set_active_version": True
            }
            
            # Add user ID only for non-system entities
            if not config.is_system_entity and user_id:
                payload_data["on_behalf_of_user_id"] = user_id

            # Use custom class that ensures proper JSON serialization of UUID objects
            payload = JSONSerializableCustomerDataVersionedUpsert(**payload_data)
            
            # Perform the upsert
            response = await self.client.upsert_versioned_document(
                namespace=config.namespace, 
                docname=config.docname, 
                data=payload
            )
            
            if response:
                logger.info(f"Successfully stored data for {config.docname}")
                logger.debug(f"Response: {response.model_dump_json(indent=2)}")
            else:
                logger.error(f"Failed to store data for {config.docname}")
            
            return response
            
        except Exception as e:
            logger.error(f"Error storing data for {config.docname}: {e}")
            return None

    async def store_data_with_predefined_config(
        self,
        docname: str,
        data: Any,
        user_id: UUID,
        version: str = "v1"
    ) -> Optional[CustomerDataVersionedUpsertResponse]:
        """
        Store data using predefined document configurations from DocumentConfigManager
        
        Args:
            docname: Name of the document type (must be in DocumentConfigManager._configs)
            data: The data to store
            user_id: User ID
            version: Version string (default: "v1")
        
        Returns:
            Response from the upsert operation or None if failed
        """
        if not self.client:
            await self.authenticate()

        try:
            
            # Use custom class that ensures proper JSON serialization
            payload = JSONSerializableCustomerDataVersionedUpsert(version=version, **config)
            
            # Perform the upsert
            response = await self.client.upsert_versioned_document(
                namespace=namespace, 
                docname=docname, 
                data=payload
            )
            
            if response:
                logger.info(f"Successfully stored predefined config data for {docname}")
                logger.debug(f"Response: {response.model_dump_json(indent=2)}")
            else:
                logger.error(f"Failed to store predefined config data for {docname}")
            
            return response
            
        except Exception as e:
            logger.error(f"Error storing predefined config data for {docname}: {e}")
            return None

    async def store_multiple_simple(
        self,
        data_configs: list[tuple[DocumentConfig, Any]],
        user_id: Optional[UUID] = None,
    ) -> list[Optional[CustomerDataVersionedUpsertResponse]]:
        """
        Store multiple documents with their configurations
        
        Args:
            data_configs: List of (DocumentConfig, data) tuples
            user_id: Optional user ID
        
        Returns:
            List of responses from upsert operations
        """
        results = []
        for config, data in data_configs:
            result = await self.store_data_simple(config, data, user_id)
            results.append(result)
        return results


# Example usage functions
async def example_simple_usage():
    """Example of using the simple configuration approach"""
    uploader = SimpleDataUploader()
    
    user_config = DocumentConfig(
        namespace="user_strategy_johndoe",
        docname="user_dna_doc",
        is_shared=False,
        is_system_entity=False,
        version="v1.0"
    )
    
    user_data = {
        "name": "John Doe",
        "preferences": ["tech", "ai", "programming"],
        "goals": ["Build AI applications", "Learn new technologies"]
    }
    
    user_id = UUID("3fa85f64-5717-4562-b3fc-2c963f66afa1")
    
    response = await uploader.store_data_simple(
        config=user_config,
        data=user_data,
        user_id=user_id,
    )
    
    system_config = DocumentConfig(
        namespace="system_strategy_docs_namespace",
        docname="ai_guidelines",
        is_shared=True,
        is_system_entity=True,
        version="v2.0"
    )
    
    system_data = {
        "guidelines": [
            "Always validate user input",
            "Use appropriate error handling",
            "Document your code clearly"
        ],
        "best_practices": {
            "security": "Never expose sensitive data",
            "performance": "Optimize for scalability"
        }
    }
    
    system_response = await uploader.store_data_simple(
        config=system_config,
        data=system_data
    )


async def example_predefined_config_usage():
    """Example of using predefined configurations from DocumentConfigManager"""
    uploader = SimpleDataUploader()
    
    user_id = UUID("3fa85f64-5717-4562-b3fc-2c963f66afa1")
    
    # Store user DNA document using predefined config
    user_dna_data = {
        "name": "John Doe",
        "company": "Tech Corp",
        "role": "Software Engineer",
        "interests": ["AI", "Machine Learning", "Cloud Computing"]
    }
    
    response = await uploader.store_data_with_predefined_config(
        docname="user_dna_doc",
        data=user_dna_data,
        user_id=user_id,
    )


if __name__ == "__main__":
    # Run the examples
    print("Running simple configuration example...")
    asyncio.run(example_simple_usage())
    
    print("\nRunning predefined configuration example...")
    asyncio.run(example_predefined_config_usage()) 