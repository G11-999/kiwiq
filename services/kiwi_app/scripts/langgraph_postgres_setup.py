import asyncio
from db.session import get_pool, get_async_pool
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def main():
    async with get_async_pool() as async_pool:
        async_checkpointer = AsyncPostgresSaver(async_pool)
        # NOTE: you need to call .setup() the first time you're using your checkpointer
        await async_checkpointer.setup()

if __name__ == "__main__":
    with get_pool() as pool:
        checkpointer = PostgresSaver(pool)
        # NOTE: you need to call .setup() the first time you're using your checkpointer
        checkpointer.setup()
    asyncio.run(main())
