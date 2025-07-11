"""
Consumes events from RabbitMQ queues and streams defined in the workflow service.

This service listens for notifications and raw workflow events, logging them
using the configured global logger.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from faststream.rabbit import RabbitBroker, RabbitMessage
from faststream import ContextRepo  # , BrokerAnnotation
# from faststream.log import Logger as FSLogger

# Import settings and logger setup
from kiwi_app.settings import settings # Assuming settings path
from global_config.logger import get_logger
from db.session import get_async_db_as_manager

# Import queue/stream definitions
from kiwi_app.workflow_app.wf_queue.queue import workflow_notifications_queue
from kiwi_app.workflow_app.wf_stream.stream import workflow_stream


# --- Logger Setup ---
# Configure logging based on global settings
# You might adjust log levels or destinations here if needed specifically for the consumer
# setup_logging(
#     log_level=logging.INFO, # Or use settings.LOG_LEVEL
#     log_to_console=True,
#     log_to_file=True,
#     log_dir=settings.LOG_DIR, # Use log directory from settings
#     log_filename='event_consumer.log' # Specific log file for this service
# )

# Get a logger instance specific to this module
logger = get_logger(__name__)


# --- RabbitMQ Broker Setup ---
# Connect to RabbitMQ using settings
# Ensure RabbitMQ connection details (host, port, user, password) are in settings
broker = RabbitBroker(settings.RABBITMQ_URL, max_consumers=5)


# --- Placeholder for Actual Processing Logic ---
async def process_notification(payload: Dict, db_session: Any):
    """
    Placeholder function to handle the actual processing of a notification.
    Replace this with your logic (e.g., write to DB, push to WebSocket).

    Args:
        payload (Dict): The validated notification data.
        db_session (Any): The active database session/connection.
    """
    logger.info(f"Processing notification (placeholder): {payload.get('notification_type')}")
    # Example: await db_session.exec(...)
    # Example: await websocket_manager.send(...)
    await asyncio.sleep(0.1) # Simulate async work
    logger.debug("Notification processing complete (placeholder).")


# --- Queue Consumer ---
@broker.subscriber(
        workflow_notifications_queue, 
        # consume_args=dict(prefetch_count=5)
        )
async def handle_workflow_notification(
    msg: Any, # The raw message payload, FastStream tries to decode based on content type
    message: RabbitMessage, # Provides access to raw message details and ACK/NACK/Reject
    context: ContextRepo, # Provides access to dependencies, state (if configured)
    # fs_logger: FSLogger, # FastStream's specific logger instance for this handler
    # broker_annotation: BrokerAnnotation # Access to the broker instance if needed
):
    """
    Consumes and logs messages from the standard workflow notifications queue.
    Uses explicit ACK/reject for message handling.

    Args:
        msg (Any): The decoded message payload.
        message (RabbitMessage): The raw RabbitMQ message object.
        context (ContextRepo): FastStream context repository.
        logger (FSLogger): FastStream logger instance.
        broker_annotation (BrokerAnnotation): Annotation for broker access.
    """
    notification_payload: Optional[Dict] = None
    try:
        # Decode message - Assuming JSON payload primarily
        # FastStream might attempt decoding based on content_type, but we add explicit checks
        if isinstance(msg, dict):
            notification_payload = msg
        elif isinstance(msg, (str, bytes)):
             try:
                 notification_payload = json.loads(msg)
                 logger.debug("Successfully decoded JSON message from string/bytes.")
             except json.JSONDecodeError:
                 logger.error(f"Failed to decode JSON message: {msg!r}", exc_info=True)
                 await message.reject(requeue=False) # Reject non-JSON messages permanently
                 return
        else:
            logger.warning(f"Received notification message in unexpected format: {type(msg)}")
            await message.reject(requeue=False) # Reject unexpected formats
            return

        if not notification_payload:
             logger.warning(f"Received empty or non-decodable notification payload: {msg!r}")
             await message.reject(requeue=False) # Reject empty/invalid messages
             return

        logger.info(f"Received notification payload: {notification_payload}")

        # --- Process the notification ---
        # Use a try/except block to catch processing errors and potentially NACK/requeue
        try:
            # Example: Access dependencies via context if needed
            # db_pool = context.get("db_pool") # If db_pool was added to context

            # Get a DB session for this specific message processing
            async with get_async_db_as_manager() as db_session:
                await process_notification(notification_payload, db_session)

            # Acknowledge the message only after successful processing
            await message.ack()
            logger.debug(f"Successfully processed and ACKed notification: ID {message.message_id}")

        except Exception as processing_error:
            logger.error(f"Error processing notification: {notification_payload}", exc_info=True)
            # Decide whether to NACK (requeue) or Reject (dead-letter/discard)
            # For transient errors (DB connection issues), requeue might be appropriate.
            # For permanent errors (bad data), reject.
            # Example: Requeue once? Requires tracking retry count (not shown here)
            # await message.nack(requeue=True)
            await message.reject(requeue=False) # Default to rejecting on processing error

    except Exception as e:
        # Catch unexpected errors during initial decoding or message handling
        logger.critical(f"Critical error in notification handler for message {message.message_id}: {e}", exc_info=True)
        # Try to reject the message if possible, otherwise it might remain unacked
        try:
            await message.reject(requeue=False)
        except Exception as reject_err:
            logger.error(f"Failed to reject message {message.message_id} after critical handler error: {reject_err}", exc_info=True)


# --- Stream Consumer ---
# Note: FastStream handles stream consumption transparently when the queue
# is defined with queue_type=QueueType.STREAM.
# Offset management is handled by RabbitMQ Streams and the client library.
# FastStream's default behavior usually starts consuming from the 'next' available offset
# unless specific subscription arguments are provided (more advanced).
@broker.subscriber(workflow_stream  # , consume_args=dict(prefetch_count=5)
                   )
async def handle_workflow_event(msg: Any, 
    # rmq_logger: Logger, 
    message: RabbitMessage,  # NOTE: Offset will be available in message header! message.properties.headers.get("x-stream-offset")
    context: ContextRepo,
    # broker: BrokerAnnotation,
    ):
    """
    Consumes and logs messages from the workflow events stream.

    Args:
        message (Any): The message payload received from the stream.
                       The type depends on what is published (e.g., WorkflowBaseEvent subclasses).
    """
    # Note: Stream messages might have additional metadata like offset,
    # but FastStream typically abstracts this unless you delve deeper into the context object.
    # For simple logging, the message content is usually sufficient.
    loaded_msg = json.loads(message.body)
    text_msges = []
    text_keys = ["text", "partial_json", "json", "thinking", "reasoning", "reason", "think"]
    if loaded_msg.get("event_type") == "message_chunk":
        content_or_content_list = loaded_msg.get("message", {}).get("content", {})
        if not isinstance(content_or_content_list, list):
            content_or_content_list = [content_or_content_list]
        for content in content_or_content_list:
            if isinstance(content, str):
                text_msges.append(content)
            elif isinstance(content, dict):
                for text_key in text_keys:
                    text_msg = content.get(text_key)
                    if text_msg:
                        text_msges.append(str(text_msg))
                        break
    text_msg = "\n".join(text_msges)
        
    logger.info(f"Received stream event message (event Type: {loaded_msg.get('event_type')}): \n{text_msg}\n")
    logger.info(f"Received stream event message OFFSET: {message.headers.get('x-stream-offset')}")
    # Add further processing (e.g., writing to MongoDB, WebSocket push)


# --- Main Execution ---
async def main():
    """Starts the FastStream broker to begin consuming messages."""
    logger.info("Starting event consumer service...")
    # The broker will connect and start listening based on the defined subscribers
    await broker.start()
    # Keep the service running indefinitely (or until interrupted)
    # In a real service, you might have more robust lifecycle management
    await asyncio.Event().wait() # Keep running until interrupted

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Event consumer service stopped.")

