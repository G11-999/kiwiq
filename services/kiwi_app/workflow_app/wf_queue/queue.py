from faststream.rabbit import RabbitQueue
from kiwi_app.settings import settings

# Define the queue for important, actionable workflow notifications
# This is a standard queue, not a stream.
workflow_notifications_queue = RabbitQueue(
    name=settings.WORKFLOW_NOTIFICATIONS_QUEUE,
    durable=True,       # Ensure queue survives broker restarts
    auto_delete=False,  # Keep queue even when no consumers are connected
    arguments={
        # Queue-level message TTL (in milliseconds)
        "x-message-ttl": settings.WORKFLOW_NOTIFICATIONS_TTL_MS, 
        # Max size of the queue in bytes
        "x-max-length-bytes": settings.WORKFLOW_NOTIFICATIONS_MAX_LENGTH_BYTES,
        "x-prefetch-count": 3,
    }
)

# NOTE: If you need more complex policies like dead-lettering, 
# those are typically configured on the queue itself via RabbitMQ management
# or policies, rather than just through FastStream's declaration arguments.
