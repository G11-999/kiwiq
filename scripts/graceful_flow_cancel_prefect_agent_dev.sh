#!/bin/bash

# ============================================
# FIXED SCRIPT - MAIN VERSION
# ============================================

#!/bin/bash
set -e  # Exit on error

# Configuration
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose-dev.yml}"
CONTAINER_NAME="${CONTAINER_NAME:-prefect-agent}"
GRACE_PERIOD="${GRACE_PERIOD:-10}"

echo "========================================="
echo "Prefect Agent Graceful Restart"
echo "========================================="

#!/bin/bash
echo "Cancelling all running flows..."

docker-compose -f $COMPOSE_FILE exec -T $CONTAINER_NAME python3 << 'EOF'
import asyncio
import subprocess
from prefect import get_client
from prefect.client.schemas.filters import FlowRunFilter, FlowRunFilterState, FlowRunFilterStateType
from prefect.states import Cancelled, StateType

from prefect import get_client
from prefect.client.schemas.filters import FlowRunFilter, FlowRunFilterState, FlowRunFilterStateType
from prefect.states import Cancelled, StateType

async def graceful_cancel_all():
    async with get_client() as client:
        flows = await client.read_flow_runs(
            flow_run_filter=FlowRunFilter(
                state=FlowRunFilterState(
                    type=FlowRunFilterStateType(any_=[StateType.RUNNING])
                )
            ),
            limit=200
        )
        
        print(f"Found {len(flows)} running flows")
        
        # Phase 1: Request graceful cancellation (NO force flag)
        print("Phase 1: Requesting graceful cancellation...")
        for flow in flows:
            flow_id = flow.id
            print(f"Cancelling flow: {flow_id}")
            # Execute: prefect flow-run cancel 'flow_id'
            cancel_result = subprocess.run(
                ["prefect", "flow-run", "cancel", str(flow_id)],
                capture_output=True,
                text=True
            )
            
            if cancel_result.returncode == 0:
                print(f"  ✅ Cancelled successfully")
            else:
                print(f"  ❌ Failed: {cancel_result.stderr}")
    await asyncio.sleep(10)

asyncio.run(graceful_cancel_all())
EOF

# echo "Waiting for cancellations..."
# sleep 5

# echo "Restarting $CONTAINER_NAME..."
# docker-compose -f $COMPOSE_FILE restart $CONTAINER_NAME

# echo "Done!"
