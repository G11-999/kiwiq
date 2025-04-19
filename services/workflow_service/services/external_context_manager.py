from db.session import get_async_db_as_manager
from global_config.settings import global_settings
from mongo_client.mongo_versioned_client import AsyncMongoVersionedClient
from kiwi_app.settings import settings

import asyncio
import logging
from typing import Optional, Dict, Any, List

from workflow_service.registry.registry import DBRegistry
from workflow_service.services.db_node_register import register_node_templates
from kiwi_app.workflow_app import crud as wf_crud
from kiwi_app.auth import crud as auth_crud
from kiwi_app.workflow_app.wf_queue.queue import workflow_notifications_queue
from kiwi_app.workflow_app.wf_stream.stream import workflow_stream

# Add new imports for clients
from redis_client import AsyncRedisClient
from mongo_client import AsyncMongoDBClient
from faststream.rabbit import RabbitBroker, RabbitQueue
from prefect import get_client as prefect_get_client
from workflow_service.services.events import WorkflowBaseEvent # Assuming path for event schemas

# Global clients storage
_mongo_clients: Dict[str, AsyncMongoDBClient] = {}

# Add Pydantic models for context management
from pydantic import BaseModel, Field


class DAOContext(BaseModel):
    """Container for Data Access Objects."""
    node_template: wf_crud.NodeTemplateDAO = Field(...)
    workflow: wf_crud.WorkflowDAO = Field(...)
    workflow_run: wf_crud.WorkflowRunDAO = Field(...)
    prompt_template: wf_crud.PromptTemplateDAO = Field(...)
    schema_template: wf_crud.SchemaTemplateDAO = Field(...)
    user_notification: wf_crud.UserNotificationDAO = Field(...)
    hitl_job: wf_crud.HITLJobDAO = Field(...)
    user: auth_crud.UserDAO = Field(...)

    class Config:
        arbitrary_types_allowed = True # Allow non-pydantic types like clients


class MongoContext(BaseModel):
    """Container for MongoDB clients."""
    customer: Optional[AsyncMongoDBClient] = Field(default=None)
    workflow: Optional[AsyncMongoDBClient] = Field(default=None)

    class Config:
        arbitrary_types_allowed = True


class RedisContext(BaseModel):
    """Container for Redis clients."""
    text_client: Optional[AsyncRedisClient] = Field(default=None)
    binary_client: Optional[AsyncRedisClient] = Field(default=None)

    class Config:
        arbitrary_types_allowed = True


class RabbitMQContext(BaseModel):
    """Container for RabbitMQ broker and related objects."""
    broker: Optional[RabbitBroker] = Field(default=None)
    notifications_queue: Optional[RabbitQueue] = Field(default=None)
    stream: Optional[RabbitQueue] = Field(default=None) # Type hint for stream might need adjustment
    logger: logging.Logger = Field(default_factory=lambda: logging.getLogger(__name__)) # Added logger

    class Config:
        arbitrary_types_allowed = True
        # Exclude logger from Pydantic validation/serialization if necessary
        # fields = {'logger': {'exclude': True}} # Example if logger causes issues

    async def publish_workflow_event(self, event: WorkflowBaseEvent):
        """
        Publishes an event to the configured workflow events stream/target.

        Args:
            event: The workflow event object (Pydantic model) to publish.

        Note:
            This implementation uses the standard FastStream RabbitBroker publish method.
            RabbitMQ Streams have a specific protocol. If 'workflow_stream' is a true
            RabbitMQ Stream, publishing via the standard broker's routing_key mechanism
            might not work as expected or utilize full stream features (like offset guarantees).
            A dedicated RabbitMQ Streams client library (e.g., 'stream-py') might be required
            for robust stream publishing, potentially managed separately from this broker instance.
            Confirm that the target `workflow_stream.name` is correctly configured on the
            RabbitMQ server (either as a stream routable via default exchange or as a standard queue).
        """
        if not self.broker:
            self.logger.warning("RabbitMQ broker not initialized. Cannot publish workflow event.")
            return
        if not self.stream:
            self.logger.warning("Workflow stream/queue object not provided to RabbitMQContext. Cannot publish workflow event.")
            return
        if not self.stream.name:
            self.logger.warning("Workflow stream/queue object has no name configured. Cannot publish workflow event.")
            return

        try:
            # Serialize the Pydantic model to a dictionary suitable for JSON encoding
            message_body = event
            if isinstance(event, WorkflowBaseEvent):
                message_body = event.model_dump(mode='json', exclude_defaults=True)

            # TODO: Confirm publishing mechanism for streams.
            # If self.stream represents a true RabbitMQ Stream, publishing might require
            # a dedicated stream client or specific broker configuration.
            # Using routing_key assumes it's routable via default exchange or is a queue name.
            await self.broker.publish(
                message=message_body,
                routing_key=self.stream.name, # Publish targeting the stream/queue name
                # exchange=... # Typically not needed for streams or default queue publishing
            )
            self.logger.info(f"Published event {message_body.get('event_type')} (ID: {message_body.get('run_id')} :: {message_body.get('sequence_i')}) to target '{self.stream.name}'")
        except Exception as e:
            # Log the exception with traceback for debugging
            self.logger.error(f"Failed to publish workflow event {message_body.get('event_type')} :: {message_body.get('run_id')} :: {message_body.get('sequence_i')} to target '{self.stream.name}': {e}", exc_info=True)

    async def publish_notification(self, notification: WorkflowBaseEvent):
        """
        Publishes a notification payload to the workflow notifications queue.

        Args:
            notification: The notification object to publish.
        """
        if not self.broker:
            self.logger.warning("RabbitMQ broker not initialized. Cannot publish notification.")
            return
        if not self.notifications_queue:
            self.logger.warning("Workflow notifications queue object not provided to RabbitMQContext. Cannot publish notification.")
            return

        try:
            # Publish directly to the queue object provided
            # FastStream's publish method handles dictionary serialization (usually to JSON)
            message_body = notification
            if isinstance(notification, WorkflowBaseEvent):
                message_body = notification.model_dump(mode='json', exclude_defaults=True)
            await self.broker.publish(
                message=message_body,
                queue=self.notifications_queue, # Target the specific queue object
            )
            # Log key details for traceability
            self.logger.info(f"Published notification type '{message_body.get('event_type')}' for user '{message_body.get('user_id')}' to queue '{self.notifications_queue.name}'")
        except Exception as e:
            # Log the exception with traceback
            self.logger.error(f"Failed to publish notification to queue '{self.notifications_queue.name}': {e}", exc_info=True)


class ExternalContextManager(BaseModel):
    """Manages external clients and DAOs."""
    redis: RedisContext = Field(...)
    mongo: MongoContext = Field(...)
    rabbit: RabbitMQContext = Field(...)
    prefect_client: Optional[Any] = Field(default=None)
    daos: DAOContext = Field(...)
    db_registry: DBRegistry = Field(...)
    customer_data_service: Any = Field(...)  #  CustomerDataService

    class Config:
        arbitrary_types_allowed = True # Allow non-pydantic types like clients
    
    async def close(self) -> None:
        """
        Closes all external connections and resources managed by this context.
        
        This method ensures proper cleanup of all database connections, message brokers,
        and other external resources to prevent resource leaks. It should be called
        when the context is no longer needed, typically in a finally block or at the
        end of a workflow run.
        
        Returns:
            None
            
        Raises:
            Exception: Logs but doesn't propagate exceptions during cleanup
        """
        logger = logging.getLogger(__name__)
        logger.info("Closing external context manager resources...")
        
        # Close Redis connections
        if self.redis:
            try:
                if self.redis.text_client:
                    await self.redis.text_client.close()
                    logger.debug("Closed Redis text client connection")
                if self.redis.binary_client:
                    await self.redis.binary_client.close()
                    logger.debug("Closed Redis binary client connection")
            except Exception as e:
                logger.error(f"Error closing Redis connections: {e}", exc_info=True)
        
        # Close MongoDB connections
        if self.mongo:
            try:
                if self.mongo.customer:
                    await self.mongo.customer.close()
                    logger.debug("Closed MongoDB customer client connection")
                if self.mongo.workflow:
                    await self.mongo.workflow.close()
                    logger.debug("Closed MongoDB workflow client connection")
            except Exception as e:
                logger.error(f"Error closing MongoDB connections: {e}", exc_info=True)
        
        # Close RabbitMQ broker
        if self.rabbit and self.rabbit.broker:
            try:
                await self.rabbit.broker.close()
                logger.debug("Closed RabbitMQ broker connection")
            except Exception as e:
                logger.error(f"Error closing RabbitMQ broker: {e}", exc_info=True)
        
        # Close Prefect client if it has a close method
        if self.prefect_client and hasattr(self.prefect_client, 'close'):
            try:
                await self.prefect_client.close()
                logger.debug("Closed Prefect client connection")
            except Exception as e:
                logger.error(f"Error closing Prefect client: {e}", exc_info=True)
        
        # Close CustomerDataService
        if self.customer_data_service:
            await self.customer_data_service.mongo_client.close()
            await self.customer_data_service.versioned_mongo_client.client.close()
            logger.debug("Closed CustomerDataService mongo_client connection")
        
        logger.info("External context manager resources closed successfully")


# Client instantiations
# ---------------------

# Global Redis clients storage
_redis_clients: Dict[str, AsyncRedisClient] = {}

# RabbitMQ broker instance (using FastStream)
rabbit_broker: Optional[RabbitBroker] = None
# if global_settings.RABBITMQ_URL:
#     rabbit_broker = RabbitBroker(global_settings.RABBITMQ_URL)

async def set_rabbit_broker(broker: RabbitBroker):
    """Set the RabbitMQ broker."""
    global rabbit_broker
    rabbit_broker = broker

async def get_rabbit_broker():
    """Get or initialize the RabbitMQ broker."""
    # global rabbit_broker
    # if not rabbit_broker:
    rabbit_broker = RabbitBroker(global_settings.RABBITMQ_URL)
    await rabbit_broker.start()
    return rabbit_broker

# Prefect client instance
# prefect_client: Any = None
async def get_prefect_client():
    """Get or initialize the Prefect client."""
    # global prefect_client
    # if not prefect_client:
    #     prefect_client = prefect_get_client()
    return prefect_get_client()


# Specialized MongoDB client functions
async def get_customer_mongo_client() -> AsyncMongoDBClient:
    """
    Get a MongoDB client configured for customer data.
    
    Returns:
        AsyncMongoDBClient: Client for customer data operations
    
    Raises:
        ValueError: If MongoDB URL is not configured
    """
    return await get_mongo_client('customer')

async def get_customer_mongo_client_with_extra_segments(extra_segments: List[str]) -> AsyncMongoDBClient:
    """
    Get a MongoDB client configured for customer data with specific segments.
    
    Args:
        extra_segments: List of segment names to include in the client
    
    Returns:
        AsyncMongoDBClient: Client for customer data operations with specified segments
    
    Raises:
        ValueError: If MongoDB URL is not configured
    """
    return await get_mongo_client('customer', extra_segments=extra_segments)

async def get_customer_versioned_mongo_client() -> AsyncMongoVersionedClient:
    """Create and return a versioned MongoDB client for customer data."""
    # Create versioned client based on the base MongoDB client
    # Use base segment names without version/sequence segments that will be added internally
    customer_mongo_client = await get_customer_mongo_client_with_extra_segments(extra_segments=AsyncMongoVersionedClient.VERSION_SEGMENT_NAMES)
    customer_mongo_client.version_mode = AsyncMongoDBClient.DOC_TYPE_VERSIONED
    versioned_client = AsyncMongoVersionedClient(
        client=customer_mongo_client,
        segment_names=settings.MONGO_CUSTOMER_SEGMENTS, # Base segments defined in settings
    )
    return versioned_client

async def get_customer_data_service(
    customer_mongo_client: AsyncMongoDBClient,
    versioned_mongo_client: AsyncMongoVersionedClient,
    schema_template_dao: wf_crud.SchemaTemplateDAO,
):
    """Dependency function to instantiate CustomerDataService."""
    from kiwi_app.workflow_app.service_customer_data import CustomerDataService
    return CustomerDataService(
        mongo_client=customer_mongo_client,
        versioned_mongo_client=versioned_mongo_client,
        schema_template_dao=schema_template_dao,
    )


async def get_workflow_mongo_client() -> AsyncMongoDBClient:
    """
    Get a MongoDB client configured for workflow stream data.
    
    Returns:
        AsyncMongoDBClient: Client for workflow stream operations
    
    Raises:
        ValueError: If MongoDB URL is not configured
    """
    return await get_mongo_client('workflow')

async def get_mongo_client(client_type: str, extra_segments: List[str] = []) -> AsyncMongoDBClient:
    """
    Get or create a MongoDB client of the specified type.
    
    Args:
        client_type: Either 'customer' or 'workflow'
        extra_segments: List of segment names to include in the client
    Returns:
        AsyncMongoDBClient: Configured MongoDB client
        
    Raises:
        ValueError: If client_type is invalid or MongoDB URL not configured
    """
    # global _mongo_clients
    
    # # Return existing client if already initialized
    # if client_type in _mongo_clients and _mongo_clients[client_type] is not None:
    #     return _mongo_clients[client_type]
    
    if not global_settings.MONGO_URL:
        raise ValueError("MongoDB URL not configured in settings")
    
    # Create new client based on type
    if client_type == 'customer':
        client = AsyncMongoDBClient(
            uri=global_settings.MONGO_URL,
            database=settings.MONGO_CUSTOMER_DATABASE,
            collection=settings.MONGO_CUSTOMER_COLLECTION,
            segment_names=settings.MONGO_CUSTOMER_SEGMENTS + extra_segments,
            text_search_fields=["name", "description"]
        )
    elif client_type == 'workflow':
        client = AsyncMongoDBClient(
            uri=global_settings.MONGO_URL,
            database=settings.MONGO_WORKFLOW_DATABASE,
            collection=settings.MONGO_WORKFLOW_STREAM_COLLECTION,
            segment_names=settings.MONGO_WORKFLOW_STREAM_SEGMENTS + extra_segments,
            value_filter_fields=settings.MONGO_WORKFLOW_STREAM_SEGMENTS_VALUE_FILTER_FIELDS,
            text_search_fields=[]
        )
    else:
        raise ValueError(f"Invalid MongoDB client type: {client_type}. " 
                         f"Must be one of: 'customer', 'workflow'")
    
    # Initialize client
    # setup_success = await client.drop_collection(confirm=True)
    await client.setup()
    
    # Cache client in global storage
    # _mongo_clients[client_type] = client
    
    return client


async def get_redis_client(decode_responses: bool = True) -> AsyncRedisClient:
    """
    Get or create a Redis client with the specified configuration.
    
    Args:
        decode_responses: Whether to decode Redis responses as strings (True) 
                         or return raw binary data (False)
    
    Returns:
        AsyncRedisClient: Configured Redis client
        
    Raises:
        ValueError: If Redis URL is not configured
    """
    # global _redis_clients
    
    # Use decode setting as the cache key
    client_key = f"redis_{'decoded' if decode_responses else 'binary'}"
    
    # Return existing client if already initialized
    # if client_key in _redis_clients and _redis_clients[client_key] is not None:
    #     return _redis_clients[client_key]
    
    if not global_settings.REDIS_URL:
        raise ValueError("Redis URL not configured in settings")
    
    # Create a new client
    client = AsyncRedisClient(
        redis_url=global_settings.REDIS_URL,
        decode_responses=decode_responses
    )
    
    # Verify connection with ping
    ping_result = await client.ping()
    if not ping_result:
        raise ConnectionError("Could not connect to Redis server")
    
    # Cache client in global storage
    # _redis_clients[client_key] = client
    
    return client


# Setup function to initialize all clients
async def get_external_context_manager_with_clients() -> ExternalContextManager:
    """
    Initialize and setup all client connections and DAOs.
    
    Returns:
        ExternalContextManager: Object containing initialized clients and DAOs
    """
    clients = {
        "redis": {"text": None, "binary": None},
        "mongo": {"customer": None, "workflow": None},
        "rabbit": None,
        "prefect": None
    }
    
    # Initialize Redis clients (text and binary)
    if global_settings.REDIS_URL:
        try:
            clients["redis"]["text"] = await get_redis_client(decode_responses=True)
            clients["redis"]["binary"] = await get_redis_client(decode_responses=False)
        except Exception as e:
            print(f"Error initializing Redis clients: {e}")
    
    # Initialize MongoDB clients
    if global_settings.MONGO_URL:
        try:
            clients["mongo"]["customer"] = await get_mongo_client('customer')
            clients["mongo"]["workflow"] = await get_mongo_client('workflow')
            clients["mongo"]["customer_versioned"] = await get_customer_versioned_mongo_client()
        except Exception as e:
            print(f"Error initializing MongoDB clients: {e}")
    
    # Initialize RabbitMQ broker
    if settings.RABBITMQ_URL:
        clients["rabbit"] = await get_rabbit_broker()
    
    # Initialize Prefect client
    try:
        clients["prefect"] = await get_prefect_client()
    except Exception as e:
        print(f"Error initializing Prefect client: {e}")
    
    node_template_dao =  wf_crud.NodeTemplateDAO()
    workflow_dao = wf_crud.WorkflowDAO()
    workflow_run_dao = wf_crud.WorkflowRunDAO()
    prompt_template_dao = wf_crud.PromptTemplateDAO()
    schema_template_dao = wf_crud.SchemaTemplateDAO()
    user_notification_dao = wf_crud.UserNotificationDAO()
    hitl_job_dao = wf_crud.HITLJobDAO()
    user_dao = auth_crud.UserDAO()

    db_registry = DBRegistry(
        node_template_dao = node_template_dao,
        schema_template_dao = schema_template_dao,
        prompt_template_dao = prompt_template_dao,
        workflow_dao = workflow_dao,
    )

    await register_node_templates(db_registry)

    # Create DAO context
    dao_context = DAOContext(
        node_template=node_template_dao,
        workflow=workflow_dao,
        workflow_run=workflow_run_dao,
        prompt_template=prompt_template_dao,
        schema_template=schema_template_dao,
        user_notification=user_notification_dao,
        hitl_job=hitl_job_dao,
        user=user_dao
    )

    customer_data_service = await get_customer_data_service(
        customer_mongo_client=clients["mongo"]["customer"],
        versioned_mongo_client=clients["mongo"]["customer_versioned"],
        schema_template_dao=schema_template_dao
    )
    
    # Create and return the ExternalContextManager
    external_context = ExternalContextManager(
        redis=RedisContext(
            text_client=clients["redis"]["text"],
            binary_client=clients["redis"]["binary"]
        ),
        mongo=MongoContext(
            customer=clients["mongo"]["customer"],
            workflow=clients["mongo"]["workflow"]
        ),
        rabbit=RabbitMQContext(
            broker=clients["rabbit"],
            notifications_queue=workflow_notifications_queue,
            stream=workflow_stream
        ),
        prefect_client=clients["prefect"],
        daos=dao_context,
        db_registry=db_registry,
        customer_data_service=customer_data_service
    )
    
    return external_context

# # E.g. usage:
async def main():
    external_context = await get_external_context_manager_with_clients()
    # print(external_context)
    # print(external_context.model_dump())


    # Mongo client testing!
    from workflow_service.services import events as event_schemas
    allowed_prefixes = None
    # if user.is_superuser:
    allowed_prefixes = [["*"]]
    # allowed_prefixes = [[str("a79ff8be-9f34-4794-9d2c-9070933a84cd"), "*"]]

    # Construct path prefix for run events
    # Targets the specific run within the org.
    mongo_runs_events_pattern = ["*", "*", str("c118b429-d607-4e61-a573-234fd7d202b3"), "*"]

    # Find all events for this run, sorted by sequence number, respecting permissions
    event_dicts = await external_context.mongo.workflow.search_objects(
        key_pattern=mongo_runs_events_pattern,
        # filter_query={}, # Get all events for the run
        value_sort_by=[("timestamp", -1), ("sequence_i", -1)], # Sort by timestamp descending, then sequence descending
        allowed_prefixes=allowed_prefixes, # Apply permission check
        value_filter={"event_type": {"$in": [event_schemas.WorkflowEvent.WORKFLOW_RUN_STATUS.value]}}  # event_schemas.WorkflowEvent.NODE_OUTPUT.value, 
    )
    print(event_dicts)

    stream_events = []
    for raw_doc in event_dicts:
        event_dict = raw_doc["data"]
        # Validate against the base event schema
        base_event = event_schemas.WorkflowBaseEvent.model_validate(event_dict)
        typed_event = None
        # Convert to specific event type based on event_type
        if base_event.event_type == event_schemas.WorkflowEvent.NODE_OUTPUT.value:
            typed_event = event_schemas.WorkflowRunNodeOutputEvent.model_validate(event_dict)
            # stream_events.append(typed_event)
        elif base_event.event_type == event_schemas.WorkflowEvent.WORKFLOW_RUN_STATUS.value:
            typed_event = event_schemas.WorkflowRunStatusUpdateEvent.model_validate(event_dict)
            # stream_events.append(typed_event)
        elif base_event.event_type == event_schemas.WorkflowEvent.MESSAGE_CHUNK.value:
            typed_event = event_schemas.MessageStreamChunk.model_validate(event_dict)
            # stream_events.append(typed_event)
        elif base_event.event_type == event_schemas.WorkflowEvent.HITL_REQUEST.value:
            typed_event = event_schemas.HITLRequestEvent.model_validate(event_dict)
            # stream_events.append(typed_event)
        # else:
        #     # For unknown event types, use the base event
        #     logger.info(f"Unknown event type {base_event.event_type} for run {run.id}, using base event model")
        stream_events.append(typed_event or event_dict)
    
    for event in stream_events:
        print("\n\n\n\n", event, "\n\n\n\n")

if __name__ == "__main__":
    asyncio.run(main())
