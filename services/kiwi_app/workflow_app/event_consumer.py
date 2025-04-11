"""
Event Consumer for Workflow Service.

This module:
1. Consumes messages from RabbitMQ workflow notification queues and workflow event streams
2. Pushes messages directly to connected WebSockets based on user/org subscriptions
3. Provides utility functions for managing the consumers

Implementation follows FastAPI WebSocket best practices and ensures efficient
message routing to the appropriate connected clients.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional, List, Set, Union

from faststream.rabbit import RabbitBroker, RabbitMessage
from faststream import ContextRepo

# Import settings and logger setup
from kiwi_app.settings import settings
from global_config.logger import get_logger
from db.session import get_async_db_as_manager

# Import WebSocket connection manager
from kiwi_app.workflow_app.websockets import get_websocket_manager, ConnectionManager

# Import queue/stream definitions
try:
    from kiwi_app.workflow_app.wf_queue.queue import workflow_notifications_queue
    from kiwi_app.workflow_app.wf_stream.stream import workflow_stream
except ImportError:
    # Fallback if module structure is different
    workflow_notifications_queue = "workflow_notifications"
    workflow_stream = "workflow_events"
    logging.warning(
        "Could not import queue/stream definitions, using default names. "
        "Please adjust imports in event_consumer.py"
    )

# Configure logger
logger = get_logger(__name__)

# Initialize broker with settings
broker = RabbitBroker(
    settings.RABBITMQ_URL, 
    max_consumers=5
)

# Get WebSocket connection manager
websocket_manager: ConnectionManager = get_websocket_manager()

# ==========================================
# Message routing and dispatch functions
# ==========================================

async def route_notification_to_websockets(notification: Dict[str, Any]) -> int:
    """
    Routes a notification to the appropriate WebSocket connections.
    
    Args:
        notification: The notification data dictionary
        
    Returns:
        Number of connections the notification was sent to
    """
    # Extract routing information from notification
    user_id = notification.get("user_id")
    run_id = notification.get("run_id")
    
    if not user_id and not run_id:
        logger.warning("Notification without user_id or run_id cannot be routed")
        return 0
    
    try:
        # Send notification based on routing information
        # If both user_id and run_id are provided, use user_run connections
        count = 0
        if user_id and run_id:
            await websocket_manager.send_json(notification, user_id=user_id, run_id=run_id)
            # For broadcast to all connections that match either user_id or run_id
            # Send to all user connections (regardless of run)
            # await websocket_manager.send_json(notification, user_id=user_id)
            # Send to all run connections (regardless of user)
            # await websocket_manager.send_json(notification, run_id=run_id)
            count += 1
        
        # If only user_id is provided, send to all user's connections
        if user_id:
            await websocket_manager.send_json(notification, user_id=user_id)
            count += 1
        
        # If only run_id is provided, send to all run's connections
        if run_id:
            await websocket_manager.send_json(notification, run_id=run_id)
            count += 1
        
        return count
    
    except Exception as e:
        logger.error(f"Error routing notification: {e}", exc_info=True)
        return 0

async def route_event_to_websockets(event: Dict[str, Any], stream_offset: Optional[int] = None) -> int:
    """
    Routes a workflow stream event to appropriate WebSocket connections.
    
    Args:
        event: The event data dictionary
        stream_offset: Optional stream offset for the event
        
    Returns:
        Number of connections the event was sent to
    """
    # Extract routing information
    run_id = event.get("run_id")
    user_id = event.get("user_id")
    
    # # Add stream offset to the event if available
    # if stream_offset is not None:
    #     event["stream_offset"] = stream_offset
    
    if not user_id and not run_id:
        logger.warning("Event without user_id or run_id cannot be routed")
        return 0
    
    try:
        # Send event based on routing information
        # For events that target a specific user and run
        count = 0
        if user_id and run_id:
            await websocket_manager.send_json(event, user_id=user_id, run_id=run_id)
            # Also send to run subscribers who might not be the target user
            await websocket_manager.send_json(event, run_id=run_id)
            count += 2  # representing the three send operations
        
        # For run-specific events
        if run_id:
            await websocket_manager.send_json(event, run_id=run_id)
            count += 1
        
        return count
    
    except Exception as e:
        logger.error(f"Error routing event: {e}", exc_info=True)
        return 0

# ==========================================
# Queue and Stream consumers
# ==========================================

@broker.subscriber(workflow_notifications_queue)
async def handle_workflow_notification(
    msg: Any,
    message: RabbitMessage,
    context: ContextRepo
):
    """
    Consumes messages from the workflow notifications queue and routes them to WebSockets.
    
    Args:
        msg: The decoded message payload
        message: The raw RabbitMQ message object
        context: FastStream context repository
    """
    notification_payload: Optional[Dict] = None
    
    try:
        # Decode message if needed
        if isinstance(msg, dict):
            notification_payload = msg
        elif isinstance(msg, (str, bytes)):
            try:
                notification_payload = json.loads(msg)
                logger.debug("Successfully decoded notification JSON")
            except json.JSONDecodeError:
                logger.error(f"Failed to decode notification JSON: {msg!r}", exc_info=True)
                await message.reject(requeue=False)
                return
        else:
            logger.warning(f"Received notification in unexpected format: {type(msg)}")
            await message.reject(requeue=False)
            return
        
        if not notification_payload:
            logger.warning(f"Empty notification payload: {msg!r}")
            await message.reject(requeue=False)
            return
        
        # Log the notification
        logger.info(f"Processing notification: {notification_payload.get('notification_type', 'unknown')}")
        
        # Check for targets to route to
        user_id = notification_payload.get("user_id")
        run_id = notification_payload.get("run_id")
        
        if not user_id and not run_id:
            logger.warning("Notification missing both user_id and run_id, cannot route")
            await message.ack()  # Still ack so we don't reprocess
            return
        
        # Check if any matching users are connected before trying to route
        if user_id and not websocket_manager.is_user_connected(user_id):
            logger.debug(f"No active connections for user {user_id}, skipping routing")
            await message.ack()
            return
        
        # Route notification to WebSockets
        sent_count = await route_notification_to_websockets(notification_payload)
        
        if sent_count > 0:
            logger.info(f"Notification sent to {sent_count} destination(s)")
        else:
            logger.debug("No active WebSocket connections for this notification")
        
        # Acknowledge successful processing
        await message.ack()
        
    except Exception as e:
        logger.error(f"Error processing notification: {e}", exc_info=True)
        try:
            # Reject message on error (don't requeue to avoid infinite retry loops)
            await message.reject(requeue=False)
        except Exception as reject_err:
            logger.error(f"Failed to reject message after error: {reject_err}")


@broker.subscriber(workflow_stream)
async def handle_workflow_event(
    msg: Any, 
    message: RabbitMessage,
    context: ContextRepo
):
    """
    Consumes events from the workflow events stream and routes them to WebSockets.
    
    Args:
        msg: The message payload received from the stream
        message: The raw RabbitMQ message object
        context: FastStream context repository
    """
    try:
        # Get stream offset if available
        stream_offset = message.headers.get('x-stream-offset')
        
        # Decode event if needed
        event_payload: Optional[Dict] = None
        
        if isinstance(msg, dict):
            event_payload = msg
        elif isinstance(msg, (str, bytes)):
            try:
                event_payload = json.loads(msg)
            except json.JSONDecodeError:
                logger.error(f"Failed to decode stream event JSON: {msg!r}", exc_info=True)
                # For streams, rejecting doesn't make sense as offset moves forward
                return
        else:
            logger.warning(f"Received event in unexpected format: {type(msg)}")
            return
        
        if not event_payload:
            logger.warning(f"Empty event payload: {msg!r}")
            return
        
        # Log the event
        logger.info(f"Processing stream event: {event_payload.get('event_type', 'unknown')}, offset: {stream_offset}")
        
        # Check for targets to route to
        user_id = event_payload.get("user_id")
        run_id = event_payload.get("run_id")
        
        if not user_id and not run_id:
            logger.warning("Event missing both user_id and run_id, cannot route")
            return
        
        # For user-targeted events, check if the user is connected first
        if user_id and not run_id and not websocket_manager.is_user_connected(user_id):
            logger.debug(f"No active connections for user {user_id}, skipping routing")
            return
        
        # Route event to WebSockets
        sent_count = await route_event_to_websockets(event_payload, stream_offset)
        
        if sent_count > 0:
            logger.info(f"Event sent to {sent_count} destination(s)")
        else:
            logger.debug("No active WebSocket connections for this event")
            
    except Exception as e:
        logger.error(f"Error processing stream event: {e}", exc_info=True)
        # For streams, we just log the error and continue

# ==========================================
# Startup and shutdown management
# ==========================================

async def start_event_consumer():
    """
    Starts the event consumer broker to begin consuming messages.
    
    Returns:
        The running broker instance
    """
    logger.info("Starting workflow event consumer service...")
    await broker.start()
    logger.info("Workflow event consumer service started")
    return broker

async def stop_event_consumer(broker):
    """
    Stops the event consumer broker.
    """
    if not broker:
        return
    logger.info("Stopping workflow event consumer service...")
    await broker.close()
    logger.info("Workflow event consumer service stopped")

# ==========================================
# Main execution for standalone mode
# ==========================================

# async def main():
#     """Runs the event consumer as a standalone service."""
#     try:
#         broker_instance = await start_event_consumer()
        
#         # Keep the service running indefinitely
#         stop_event = asyncio.Event()
#         await stop_event.wait()
#     except KeyboardInterrupt:
#         logger.info("Event consumer service interrupted")
#     finally:
#         await stop_event_consumer(broker_instance)

# if __name__ == "__main__":
#     asyncio.run(main())
