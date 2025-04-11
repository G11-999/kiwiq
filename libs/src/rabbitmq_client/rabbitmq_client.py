import asyncio
import json
import logging
import uuid
import time
from typing import Any, Dict, List, Optional, Union, Callable, Awaitable, TypeVar, Generic, Tuple

import aio_pika
from aio_pika import ExchangeType, Message, connect_robust
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustChannel, AbstractRobustConnection
from aio_pika.exceptions import MessageProcessError

from global_config.logger import get_logger
logger = get_logger(__name__)

T = TypeVar('T')

class RabbitMQClient:
    """
    Asynchronous RabbitMQ client for inter-service communication using aio-pika.
    
    Features:
    - Robust connection and channel handling
    - Message publishing with JSON serialization
    - Consumer setup for receiving messages
    - Exchange and queue management
    - Support for RPC patterns
    - Dead letter queue setup
    - Delayed message delivery
    """
    
    def __init__(
        self,
        url: str = "amqp://guest:guest@localhost/",
        connection_name: str = "python-aio-client",
        reconnect_delay: float = 5.0,
        heartbeat: int = 60,
        **kwargs
    ):
        """
        Initialize RabbitMQ client with connection parameters.
        
        Args:
            url: AMQP connection URL
            connection_name: Client identifier
            reconnect_delay: Seconds to wait between reconnection attempts
            heartbeat: Heartbeat interval in seconds
            **kwargs: Additional connection parameters
        """
        self.logger = logger
        self.url = url
        self.connection_name = connection_name
        self.reconnect_delay = reconnect_delay
        self.heartbeat = heartbeat
        self.connection_params = kwargs
        
        # Connection state
        self.connection: Optional[AbstractRobustConnection] = None
        self.channel: Optional[AbstractRobustChannel] = None
        
        # Cache for exchanges and queues
        self.exchange_cache: Dict[str, aio_pika.Exchange] = {}
        self.queue_cache: Dict[str, aio_pika.Queue] = {}
        
        # Track active consumers for cleanup
        self.consumer_tags: List[str] = []
        self.consumer_queues: Dict[str, aio_pika.Queue] = {}  # Map consumer tag to queue
        
        self.logger.info(f"RabbitMQ client initialized for {url}")
    
    # Connection Management
    
    async def connect(self) -> None:
        """
        Establish connection to RabbitMQ server with automatic reconnection.
        """
        if self.connection and not self.connection.is_closed:
            return
            
        try:
            # Create robust connection with auto-reconnect capability
            self.connection = await connect_robust(
                self.url,
                client_properties={"connection_name": self.connection_name},
                heartbeat=self.heartbeat,
                **self.connection_params
            )
            
            # Create channel
            self.channel = await self.connection.channel()
            
            # Configure QoS (prefetch)
            await self.channel.set_qos(prefetch_count=10)
            
            self.logger.info(f"Connected to RabbitMQ server")
        except Exception as e:
            self.logger.error(f"Failed to connect to RabbitMQ: {e}")
            self.connection = None
            self.channel = None
            raise
    
    async def close(self) -> None:
        """
        Close connection to RabbitMQ server.
        """
        try:
            # Cancel all consumers
            for tag, queue in list(self.consumer_queues.items()):  # Use a copy to avoid modification during iteration
                try:
                    # Try without checking if closed
                    await queue.cancel(tag)
                    if tag in self.consumer_tags:
                        self.consumer_tags.remove(tag)
                except Exception as e:
                    self.logger.warning(f"Error cancelling consumer {tag}: {e}")
            
            # Close channel
            if self.channel and not self.channel.is_closed:
                try:
                    await self.channel.close()
                except Exception as e:
                    self.logger.warning(f"Error closing channel: {e}")
                
            # Close connection
            if self.connection and not self.connection.is_closed:
                try:
                    await self.connection.close()
                except Exception as e:
                    self.logger.warning(f"Error closing connection: {e}")
                
            self.logger.info("Disconnected from RabbitMQ server")
        except Exception as e:
            self.logger.error(f"Error closing RabbitMQ connection: {e}")
        finally:
            # Ensure variables are reset even if exceptions occur
            self.channel = None
            self.connection = None
            self.consumer_tags = []
            self.consumer_queues = {}
            self.exchange_cache = {}
            self.queue_cache = {}
    
    # Queue Management
    
    async def declare_queue(
        self,
        queue_name: str,
        durable: bool = True,
        exclusive: bool = False,
        auto_delete: bool = False,
        arguments: Optional[Dict[str, Any]] = None
    ) -> aio_pika.Queue:
        """
        Declare a queue with specified parameters.
        
        Args:
            queue_name: Name of the queue
            durable: Whether queue survives broker restart
            exclusive: Whether queue is exclusive to this connection
            auto_delete: Whether queue is deleted when last consumer disconnects
            arguments: Additional queue arguments like message TTL, max length, etc.
            
        Returns:
            Queue object
        """
        if not self.channel:
            await self.connect()
            
        # Check cache first
        if queue_name in self.queue_cache:
            return self.queue_cache[queue_name]
            
        queue = await self.channel.declare_queue(
            name=queue_name,
            durable=durable,
            exclusive=exclusive,
            auto_delete=auto_delete,
            arguments=arguments
        )
        
        # Cache the queue
        self.queue_cache[queue_name] = queue
        self.logger.debug(f"Declared queue: {queue_name}")
        
        return queue
    
    async def delete_queue(self, queue_name: str) -> None:
        """
        Delete a queue.
        
        Args:
            queue_name: Name of the queue
        """
        if not self.channel:
            await self.connect()
            
        await self.channel.queue_delete(queue_name)
        
        # Remove from cache
        if queue_name in self.queue_cache:
            del self.queue_cache[queue_name]
            
        self.logger.debug(f"Deleted queue: {queue_name}")
    
    async def purge_queue(self, queue_name: str) -> None:
        """
        Purge all messages from a queue.
        
        Args:
            queue_name: Name of the queue
        """
        if not self.channel:
            await self.connect()
            
        queue = await self.declare_queue(queue_name)
        await queue.purge()
        self.logger.debug(f"Purged queue: {queue_name}")
    
    async def get_queue_info(self, queue_name: str) -> Dict[str, Any]:
        """
        Get information about a queue (message count, consumer count, etc.).
        
        Args:
            queue_name: Name of the queue
            
        Returns:
            Dictionary with queue information
        """
        if not self.channel:
            await self.connect()
            
        # Declare queue passively to get info
        queue = await self.channel.declare_queue(
            name=queue_name,
            passive=True
        )
        
        return {
            "message_count": queue.declaration_result.message_count,
            "consumer_count": queue.declaration_result.consumer_count
        }
    
    # Exchange Management
    
    async def declare_exchange(
        self,
        exchange_name: str,
        exchange_type: Union[ExchangeType, str] = ExchangeType.DIRECT,
        durable: bool = True,
        auto_delete: bool = False,
        internal: bool = False,
        arguments: Optional[Dict[str, Any]] = None
    ) -> aio_pika.Exchange:
        """
        Declare an exchange with specified parameters.
        
        Args:
            exchange_name: Name of the exchange
            exchange_type: Type of exchange (direct, topic, fanout, headers)
            durable: Whether exchange survives broker restart
            auto_delete: Whether exchange is deleted when last queue is unbound
            internal: Whether exchange can be published to directly
            arguments: Additional exchange arguments
            
        Returns:
            Exchange object
        """
        if not self.channel:
            await self.connect()
            
        # Handle default exchange specially
        if exchange_name == "":
            return self.channel.default_exchange
            
        # Check cache first
        if exchange_name in self.exchange_cache:
            return self.exchange_cache[exchange_name]
            
        # Convert string type to enum if needed
        if isinstance(exchange_type, str):
            exchange_type = {
                "direct": ExchangeType.DIRECT,
                "topic": ExchangeType.TOPIC,
                "fanout": ExchangeType.FANOUT,
                "headers": ExchangeType.HEADERS
            }.get(exchange_type.lower(), ExchangeType.DIRECT)
            
        exchange = await self.channel.declare_exchange(
            name=exchange_name,
            type=exchange_type,
            durable=durable,
            auto_delete=auto_delete,
            internal=internal,
            arguments=arguments
        )
        
        # Cache the exchange
        self.exchange_cache[exchange_name] = exchange
        self.logger.debug(f"Declared exchange: {exchange_name} ({exchange_type.name})")
        
        return exchange
    
    async def delete_exchange(self, exchange_name: str) -> None:
        """
        Delete an exchange.
        
        Args:
            exchange_name: Name of the exchange
        """
        if not self.channel:
            await self.connect()
            
        # Skip trying to delete the default exchange
        if exchange_name == "":
            return
            
        await self.channel.exchange_delete(exchange_name)
        
        # Remove from cache
        if exchange_name in self.exchange_cache:
            del self.exchange_cache[exchange_name]
            
        self.logger.debug(f"Deleted exchange: {exchange_name}")
    
    async def bind_queue_to_exchange(
        self,
        queue_name: str,
        exchange_name: str,
        routing_key: str = ""
    ) -> None:
        """
        Bind a queue to an exchange with routing key.
        
        Args:
            queue_name: Name of the queue
            exchange_name: Name of the exchange
            routing_key: The routing key to use for binding
        """
        if not self.channel:
            await self.connect()
            
        # Get or declare queue and exchange
        queue = await self.declare_queue(queue_name)
        exchange = await self.declare_exchange(exchange_name)
        
        # Bind queue to exchange
        await queue.bind(exchange, routing_key=routing_key)
        self.logger.debug(f"Bound queue '{queue_name}' to exchange '{exchange_name}' with key '{routing_key}'")
    
    async def unbind_queue_from_exchange(
        self,
        queue_name: str,
        exchange_name: str,
        routing_key: str = ""
    ) -> None:
        """
        Unbind a queue from an exchange.
        
        Args:
            queue_name: Name of the queue
            exchange_name: Name of the exchange
            routing_key: The routing key used for binding
        """
        if not self.channel:
            await self.connect()
            
        # Get queue and exchange
        queue = await self.declare_queue(queue_name)
        exchange = await self.declare_exchange(exchange_name)
        
        # Unbind queue from exchange
        await queue.unbind(exchange, routing_key=routing_key)
        self.logger.debug(f"Unbound queue '{queue_name}' from exchange '{exchange_name}'")
    
    # Message Publishing
    
    async def publish_message(
        self,
        exchange_name: str,
        routing_key: str,
        message: Any,
        headers: Optional[Dict[str, Any]] = None,
        content_type: str = "application/json",
        correlation_id: Optional[str] = None,
        reply_to: Optional[str] = None,
        expiration: Optional[int] = None,
        message_id: Optional[str] = None,
        timestamp: Optional[int] = None,
        delivery_mode: int = 2,  # 2 = persistent
        priority: Optional[int] = None
    ) -> None:
        """
        Publish a message to specified exchange with routing key.
        Automatically serializes JSON data.
        
        Args:
            exchange_name: Name of the exchange
            routing_key: Message routing key
            message: Message body (dict will be converted to JSON)
            headers: Message headers
            content_type: Message content type
            correlation_id: Correlation ID for RPC
            reply_to: Queue name for response in RPC
            expiration: Message expiration time in seconds or Must be DateType - int seconds/timedelta/datetime
            message_id: Unique message identifier
            timestamp: Message timestamp
            delivery_mode: 1 = non-persistent, 2 = persistent
            priority: Message priority (0-9, higher is more priority)
        """
        if not self.channel:
            await self.connect()
            
        # Serialize message if it's a dict
        body = message
        if isinstance(message, dict) or isinstance(message, list):
            body = json.dumps(message).encode('utf-8')
        elif not isinstance(message, bytes):
            body = str(message).encode('utf-8')
        
        # Handle default exchange specially
        if exchange_name == "":
            exchange = self.channel.default_exchange
        else:
            # Ensure exchange exists
            exchange = await self.declare_exchange(exchange_name)
        
        # Create message
        message_obj = Message(
            body=body,
            content_type=content_type,
            headers=headers,
            correlation_id=correlation_id,
            reply_to=reply_to,
            expiration=expiration,  # Must be DateType - int/timedelta/datetime
            message_id=message_id or str(uuid.uuid4()),
            timestamp=timestamp or int(time.time()),
            delivery_mode=delivery_mode,
            priority=priority
        )
        
        # Publish message
        await exchange.publish(
            message=message_obj,
            routing_key=routing_key
        )
        
        self.logger.debug(
            f"Published message to exchange '{exchange_name or 'default'}' with routing key '{routing_key}'"
        )
    
    async def publish_batch(
        self,
        exchange_name: str,
        messages: List[Tuple[str, Any, Optional[Dict[str, Any]]]],
        batch_size: int = 100
    ) -> None:
        """
        Publish batch of messages atomically.
        
        Args:
            exchange_name: Name of the exchange
            messages: List of (routing_key, message, properties) tuples
            batch_size: Maximum batch size
        """
        if not self.channel:
            await self.connect()
            
        # Handle default exchange specially
        if exchange_name == "":
            exchange = self.channel.default_exchange
        else:
            # Ensure exchange exists
            exchange = await self.declare_exchange(exchange_name)
        
        # Process in batches without using transactions (which conflict with publisher confirms)
        for i in range(0, len(messages), batch_size):
            batch = messages[i:i+batch_size]
            
            for routing_key, message, properties in batch:
                props = properties or {}
                
                # Serialize message if it's a dict
                body = message
                if isinstance(message, dict) or isinstance(message, list):
                    body = json.dumps(message).encode('utf-8')
                elif not isinstance(message, bytes):
                    body = str(message).encode('utf-8')
                
                # Handle expiration properly (convert to string)
                expiration = props.get('expiration')
                if expiration is not None:
                    expiration = str(expiration)
                
                # Create message
                message_obj = Message(
                    body=body,
                    content_type=props.get('content_type', 'application/json'),
                    headers=props.get('headers'),
                    correlation_id=props.get('correlation_id'),
                    reply_to=props.get('reply_to'),
                    expiration=expiration,
                    message_id=props.get('message_id', str(uuid.uuid4())),
                    timestamp=props.get('timestamp', int(time.time())),
                    delivery_mode=props.get('delivery_mode', 2),
                    priority=props.get('priority')
                )
                
                # Publish message
                await exchange.publish(
                    message=message_obj,
                    routing_key=routing_key
                )
            
            self.logger.debug(
                f"Published batch of {len(batch)} messages to exchange '{exchange_name or 'default'}'"
            )
    
    async def publish_with_retry(
        self,
        exchange_name: str,
        routing_key: str,
        message: Any,
        retry_count: int = 3,
        retry_delay: float = 1.0,
        **kwargs
    ) -> bool:
        """
        Publish message with retry on failure.
        
        Args:
            exchange_name: Name of the exchange
            routing_key: Message routing key
            message: Message body
            retry_count: Number of retries
            retry_delay: Initial delay between retries (will be increased exponentially)
            **kwargs: Additional publish_message arguments
            
        Returns:
            True if successful, False after all retries fail
        """
        last_exception = None
        current_retry = 0
        current_delay = retry_delay
        
        # Special handling for non-existent exchanges
        if exchange_name != "" and exchange_name not in self.exchange_cache:
            try:
                # Try to check if the exchange exists
                if self.channel:
                    try:
                        await self.channel.exchange_declare(exchange_name, passive=True)
                    except Exception:
                        # Exchange doesn't exist and we're not using the default exchange
                        self.logger.error(f"Exchange '{exchange_name}' does not exist")
                        return False
            except Exception as e:
                self.logger.error(f"Error checking exchange '{exchange_name}': {e}")
                return False
        
        while current_retry <= retry_count:
            try:
                await self.publish_message(
                    exchange_name=exchange_name,
                    routing_key=routing_key,
                    message=message,
                    **kwargs
                )
                return True
            except Exception as e:
                last_exception = e
                current_retry += 1
                
                if current_retry <= retry_count:
                    self.logger.warning(
                        f"Publish failed, retrying {current_retry}/{retry_count} "
                        f"after {current_delay:.2f}s: {str(e)}"
                    )
                    await asyncio.sleep(current_delay)
                    current_delay *= 2  # Exponential backoff
        
        self.logger.error(
            f"Failed to publish message after {retry_count} retries: {last_exception}"
        )
        return False
    
    # Message Consumption
    
    async def consume(
        self,
        queue_name: str,
        callback: Callable[[AbstractIncomingMessage], Awaitable[None]],
        prefetch_count: int = 10,
        auto_ack: bool = False,
        exclusive: bool = False,
        consumer_tag: Optional[str] = None,
        arguments: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Start consuming messages from a queue.
        The callback should be an async function that takes a message parameter.
        
        Args:
            queue_name: Name of the queue to consume from
            callback: Async function to call for each message
            prefetch_count: Maximum number of unacknowledged messages
            auto_ack: Whether to auto-acknowledge messages
            exclusive: Whether this consumer has exclusive access to the queue
            consumer_tag: Consumer identifier
            arguments: Additional consumer arguments
        
        Returns:
            Consumer tag that can be used to cancel the consumer
        """
        if not self.channel:
            await self.connect()
            
        # Set QoS for this consumer
        await self.channel.set_qos(prefetch_count=prefetch_count)
        
        # Create a wrapper callback that handles acks based on auto_ack
        async def wrapper_callback(message: AbstractIncomingMessage) -> None:
            try:
                await callback(message)
                if not auto_ack:
                    try:
                        await message.ack()
                    except MessageProcessError:
                        # Message was already processed, ignore
                        pass
            except Exception as e:
                self.logger.error(f"Error processing message: {e}")
                if not auto_ack:
                    try:
                        await message.reject(requeue=True)
                    except MessageProcessError:
                        # Message was already processed, ignore
                        pass
                raise
        
        # Get or declare queue
        queue = await self.declare_queue(queue_name)
        
        # Start consuming
        consumer_tag = consumer_tag or f"consumer-{uuid.uuid4()}"
        await queue.consume(
            wrapper_callback,
            consumer_tag=consumer_tag,
            exclusive=exclusive,
            arguments=arguments
        )
        
        # Track consumer tag and queue for cleanup
        self.consumer_tags.append(consumer_tag)
        self.consumer_queues[consumer_tag] = queue
        
        self.logger.debug(f"Started consuming from queue '{queue_name}' with tag '{consumer_tag}'")
        return consumer_tag
    
    async def cancel_consumer(self, consumer_tag: str) -> None:
        """
        Cancel a consumer by its tag.
        
        Args:
            consumer_tag: Consumer identifier
        """
        if not self.channel or consumer_tag not in self.consumer_queues:
            return
            
        try:
            queue = self.consumer_queues[consumer_tag]
            # Simply try to cancel without checking if closed
            await queue.cancel(consumer_tag)
            
            if consumer_tag in self.consumer_tags:
                self.consumer_tags.remove(consumer_tag)
            if consumer_tag in self.consumer_queues:
                del self.consumer_queues[consumer_tag]
                
            self.logger.debug(f"Cancelled consumer with tag '{consumer_tag}'")
        except Exception as e:
            self.logger.warning(f"Error cancelling consumer '{consumer_tag}': {e}")
    
    # RPC Pattern Implementation
    
    async def rpc_call(
        self,
        exchange_name: str,
        routing_key: str,
        message: Any,
        timeout: float = 30.0,
        **kwargs
    ) -> Optional[Any]:
        """
        Make an RPC call and wait for response.
        
        Args:
            exchange_name: Name of the exchange
            routing_key: Message routing key
            message: Message body
            timeout: Maximum time to wait for response in seconds
            **kwargs: Additional publish_message arguments
            
        Returns:
            Response message
        """
        if not self.channel:
            await self.connect()
            
        # Create temporary callback queue
        callback_queue = await self.channel.declare_queue(
            name="",  # Empty name for server-generated name
            exclusive=True,
            auto_delete=True
        )
        
        # Generate correlation ID
        correlation_id = str(uuid.uuid4())
        
        # Future to store the response
        future = asyncio.Future()
        
        # Create response handler
        async def on_response(message: AbstractIncomingMessage) -> None:
            if message.correlation_id == correlation_id:
                # Parse response based on content type
                if message.content_type == 'application/json':
                    try:
                        payload = json.loads(message.body.decode())
                    except:
                        payload = message.body.decode()
                else:
                    payload = message.body
                
                future.set_result(payload)
                try:
                    await message.ack()
                except MessageProcessError:
                    # Message already acknowledged, ignore
                    pass
        
        # Start consuming from callback queue
        consumer_tag = await callback_queue.consume(on_response)
        self.consumer_queues[consumer_tag] = callback_queue
        
        try:
            # Publish request
            await self.publish_message(
                exchange_name=exchange_name,
                routing_key=routing_key,
                message=message,
                correlation_id=correlation_id,
                reply_to=callback_queue.name,
                **kwargs
            )
            
            # Wait for response with timeout
            try:
                return await asyncio.wait_for(future, timeout=timeout)
            except asyncio.TimeoutError:
                self.logger.warning(
                    f"RPC call to '{routing_key}' timed out after {timeout}s"
                )
                return None
                
        finally:
            # Clean up temporary queue and consumer
            try:
                if not callback_queue.is_closed:
                    await callback_queue.cancel(consumer_tag)
                if consumer_tag in self.consumer_queues:
                    del self.consumer_queues[consumer_tag]
            except Exception:
                pass  # Ignore cleanup errors
                
            try:
                if not callback_queue.is_closed:
                    await callback_queue.delete()
            except Exception:
                pass  # Ignore cleanup errors
    
    # Advanced Patterns
    
    async def setup_dlq(
        self,
        queue_name: str,
        dlq_suffix: str = "_failed",
        max_retries: Optional[int] = None
    ) -> Tuple[str, str]:
        """
        Set up a Dead Letter Queue for the specified queue.
        
        Args:
            queue_name: Name of the main queue
            dlq_suffix: Suffix for the DLQ name
            max_retries: Maximum number of retries before message goes to DLQ
            
        Returns:
            Tuple of (main queue name, DLQ name)
        """
        if not self.channel:
            await self.connect()
            
        # Create DLQ exchange
        dlx_name = f"{queue_name}.dlx"
        await self.declare_exchange(dlx_name)
        
        # Create DLQ queue
        dlq_name = f"{queue_name}{dlq_suffix}"
        dlq = await self.declare_queue(dlq_name, durable=True)
        
        # Bind DLQ to DLX
        await dlq.bind(dlx_name, routing_key=queue_name)
        
        # Create main queue with DLX configuration
        arguments = {
            "x-dead-letter-exchange": dlx_name,
            "x-dead-letter-routing-key": queue_name
        }
        
        # Add retry limit if specified
        if max_retries is not None:
            arguments["x-max-retries"] = max_retries
        
        await self.declare_queue(queue_name, durable=True, arguments=arguments)
        
        self.logger.info(f"Set up DLQ for queue '{queue_name}': '{dlq_name}'")
        return queue_name, dlq_name
    
    async def setup_delayed_queue(
        self,
        queue_name: str,
        delay_ms: int = 5000,
        exchange_name: Optional[str] = None
    ) -> Tuple[str, str, str]:
        """
        Set up a queue for delayed message processing.
        
        Args:
            queue_name: Name of the queue
            delay_ms: Delay in milliseconds
            exchange_name: Custom exchange name (or derived from queue name)
            
        Returns:
            Tuple of (exchange name, delay queue name, target queue name)
        """
        if not self.channel:
            await self.connect()
            
        # Create exchange for delayed messages
        exchange_name = exchange_name or f"{queue_name}.delay.exchange"
        await self.declare_exchange(exchange_name)
        
        # Create target queue
        await self.declare_queue(queue_name, durable=True)
        
        # Create delay queue with TTL and DLX to target queue
        delay_queue_name = f"{queue_name}.delay.{delay_ms}"
        arguments = {
            "x-dead-letter-exchange": "",  # Default exchange
            "x-dead-letter-routing-key": queue_name,
            "x-message-ttl": delay_ms
        }
        
        delay_queue = await self.declare_queue(
            delay_queue_name,
            durable=True,
            arguments=arguments
        )
        
        # Bind delay queue to exchange
        await delay_queue.bind(exchange_name, routing_key="#")
        
        self.logger.info(
            f"Set up delayed queue '{delay_queue_name}' -> '{queue_name}' with {delay_ms}ms delay"
        )
        return exchange_name, delay_queue_name, queue_name
    
    async def setup_fanout(
        self,
        exchange_name: str,
        queue_prefix: str,
        queue_count: int
    ) -> Tuple[str, List[str]]:
        """
        Set up a fanout exchange with multiple queues for load balancing.
        
        Args:
            exchange_name: Name of the fanout exchange
            queue_prefix: Prefix for queue names
            queue_count: Number of queues to create
            
        Returns:
            Tuple of (exchange name, list of queue names)
        """
        if not self.channel:
            await self.connect()
            
        # Create fanout exchange
        await self.declare_exchange(exchange_name, exchange_type=ExchangeType.FANOUT)
        
        # Create multiple queues and bind to exchange
        queue_names = []
        for i in range(queue_count):
            queue_name = f"{queue_prefix}_{i}"
            queue = await self.declare_queue(queue_name, durable=True)
            await queue.bind(exchange_name)
            queue_names.append(queue_name)
        
        self.logger.info(
            f"Set up fanout exchange '{exchange_name}' with {queue_count} queues"
        )
        return exchange_name, queue_names
    
    # Health Check and Monitoring
    
    async def health_check(self) -> bool:
        """
        Check if connection is healthy.
        
        Returns:
            True if connection is healthy
        """
        try:
            if not self.connection or self.connection.is_closed:
                await self.connect()
                
            if not self.channel or self.channel.is_closed:
                # Create a new channel
                self.channel = await self.connection.channel()
                await self.channel.set_qos(prefetch_count=10)
                
            # Just check if we can perform a simple operation
            # Create a temp queue and immediately delete it
            temp_queue_name = f"health_check_{uuid.uuid4().hex}"
            temp_queue = await self.channel.declare_queue(
                name=temp_queue_name,
                auto_delete=True,
                exclusive=True
            )
            await temp_queue.delete()
            
            return True
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False
    
    async def get_queue_length(self, queue_name: str) -> int:
        """
        Get the current length of a queue.
        
        Args:
            queue_name: Name of the queue
            
        Returns:
            Number of messages in the queue
        """
        info = await self.get_queue_info(queue_name)
        return info["message_count"]
    
    # Context manager support
    
    async def __aenter__(self) -> "RabbitMQClient":
        """Async context manager entry."""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
