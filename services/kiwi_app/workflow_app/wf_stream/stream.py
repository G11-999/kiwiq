from faststream.rabbit import RabbitBroker, RabbitQueue, QueueType
from kiwi_app.settings import settings

workflow_stream = RabbitQueue(
    name=settings.WORKFLOW_EVENTS_STREAM,
    # Parameters below might not be directly used by Stream protocol client,
    # but are good practice for queue-like behavior if needed.
    durable=True, 
    auto_delete=False, 
    queue_type=QueueType.STREAM,
    arguments={
        "x-max-length-bytes": settings.WORKFLOW_STREAM_EVENTS_MAX_LENGTH_BYTES,
        "x-max-age": settings.WORKFLOW_STREAM_EVENTS_MAX_AGE,
        "x-prefetch-count": 3,
    },
    # prefetch_count=3,
)
