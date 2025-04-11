import asyncio
import uuid
import json
from typing import List, Optional, Dict, Any, Set, Tuple, AsyncGenerator

from fastapi import (
    APIRouter, Depends, HTTPException, status, Query, WebSocket,
    WebSocketDisconnect, Path
)
from sqlalchemy.ext.asyncio import AsyncSession

# Core Dependencies
from db.session import get_async_db_dependency
from global_config.logger import get_logger

# Auth Dependencies - using standard auth instead of custom tokens
from kiwi_app.auth.dependencies import get_current_active_verified_user, get_active_org_id
from kiwi_app.auth.models import User

# Workflow App Dependencies
from kiwi_app.workflow_app import crud, models, dependencies as wf_deps
from kiwi_app.workflow_app.dependencies import get_workflow_run_for_org

# Setup Router
websocket_router = APIRouter(prefix="/ws", tags=["WebSocket Connections"])

logger = get_logger(__name__)


class ConnectionManager:
    """
    Manages active WebSocket connections for users and runs.
    
    Tracks connections by user ID and run ID, allowing targeted message delivery
    to specific users, specific runs, or combinations of both.
    """
    def __init__(self):
        # Store connections per user ID
        # key: user_id (str) -> Set[WebSocket]
        self.user_connections: Dict[str, Set[WebSocket]] = {}
        
        # Store connections per run ID
        # key: run_id (str) -> Set[WebSocket]
        self.run_connections: Dict[str, Set[WebSocket]] = {}
        
        # Store connections per user ID and run ID
        # key: (user_id, run_id) (tuple of str) -> Set[WebSocket]
        self.user_run_connections: Dict[str, Dict[str, Set[WebSocket]]] = {}
        
        # Map from WebSocket -> list of (user_id, run_id) tuples for easier cleanup
        self.socket_subscriptions: Dict[WebSocket, List[Tuple[str, Optional[str]]]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        """
        Registers a new WebSocket connection for a user.
        
        Args:
            websocket: The WebSocket connection to register
            user_id: The ID of the user connecting
        """
        await websocket.accept()
        
        # Add to user connections
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(websocket)
        
        # Initialize user's subscription tracking
        if user_id not in self.user_run_connections:
            self.user_run_connections[user_id] = {}
        
        # Initialize socket's subscription tracking
        self.socket_subscriptions[websocket] = [(user_id, None)]
        
        logger.info(f"WebSocket connected for user: {user_id}. Total connections: {len(self.user_connections[user_id])}")

    async def subscribe_to_run(self, websocket: WebSocket, user_id: str, run_id: str):
        """
        Subscribes a WebSocket connection to a specific run.
        
        Args:
            websocket: The WebSocket connection to subscribe
            user_id: The ID of the user
            run_id: The ID of the run to subscribe to
        """
        # Add to run connections
        if run_id not in self.run_connections:
            self.run_connections[run_id] = set()
        self.run_connections[run_id].add(websocket)
        
        # Add to user-run connections
        if run_id not in self.user_run_connections[user_id]:
            self.user_run_connections[user_id][run_id] = set()
        self.user_run_connections[user_id][run_id].add(websocket)
        
        # Update socket's subscription tracking
        self.socket_subscriptions[websocket].append((user_id, run_id))
        
        logger.info(f"User {user_id} subscribed to run {run_id}")

    async def unsubscribe_from_run(self, websocket: WebSocket, user_id: str, run_id: str):
        """
        Unsubscribes a WebSocket connection from a specific run.
        
        Args:
            websocket: The WebSocket connection to unsubscribe
            user_id: The ID of the user
            run_id: The ID of the run to unsubscribe from
        """
        # Remove from run connections
        if run_id in self.run_connections:
            self.run_connections[run_id].discard(websocket)
            if not self.run_connections[run_id]:
                del self.run_connections[run_id]
        
        # Remove from user-run connections
        if user_id in self.user_run_connections and run_id in self.user_run_connections[user_id]:
            self.user_run_connections[user_id][run_id].discard(websocket)
            if not self.user_run_connections[user_id][run_id]:
                del self.user_run_connections[user_id][run_id]
                if not self.user_run_connections[user_id]:
                    del self.user_run_connections[user_id]
        
        # Update socket's subscription tracking
        if websocket in self.socket_subscriptions:
            self.socket_subscriptions[websocket] = [
                sub for sub in self.socket_subscriptions[websocket] 
                if sub != (user_id, run_id)
            ]
        
        logger.info(f"User {user_id} unsubscribed from run {run_id}")

    def disconnect(self, websocket: WebSocket):
        """
        Removes a WebSocket connection and cleans up all associated subscriptions.
        
        Args:
            websocket: The WebSocket connection to disconnect
        """
        # Get all subscriptions for this socket
        subscriptions = self.socket_subscriptions.pop(websocket, [])
        
        for user_id, run_id in subscriptions:
            # Clean up user connections
            if user_id in self.user_connections:
                self.user_connections[user_id].discard(websocket)
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]
            
            # Clean up run connections if this socket was subscribed to runs
            if run_id:
                if run_id in self.run_connections:
                    self.run_connections[run_id].discard(websocket)
                    if not self.run_connections[run_id]:
                        del self.run_connections[run_id]
                
                # Clean up user-run connections
                if user_id in self.user_run_connections and run_id in self.user_run_connections[user_id]:
                    self.user_run_connections[user_id][run_id].discard(websocket)
                    if not self.user_run_connections[user_id][run_id]:
                        del self.user_run_connections[user_id][run_id]
                        if not self.user_run_connections[user_id]:
                            del self.user_run_connections[user_id]
        
        if subscriptions:
            logger.info(f"WebSocket disconnected with {len(subscriptions)} subscriptions cleaned up")

    def is_user_connected(self, user_id: str) -> bool:
        """
        Checks if a user has any active WebSocket connections.
        
        Args:
            user_id: The user ID to check
            
        Returns:
            True if the user has at least one active connection, False otherwise
        """
        user_id_str = str(user_id)  # Ensure user_id is a string
        return user_id_str in self.user_connections and len(self.user_connections[user_id_str]) > 0

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """
        Sends a text message to a specific WebSocket.
        
        Args:
            message: The message to send
            websocket: The WebSocket to send to
        """
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.warning(f"Error sending personal message: {e}")
            self.disconnect(websocket)

    async def send_json(self, data: Dict[str, Any], user_id: Optional[str] = None, run_id: Optional[str] = None):
        """
        Sends a JSON message to WebSockets based on user_id and/or run_id filters.
        
        Args:
            data: The data to send as JSON
            user_id: Optional user ID to filter recipients
            run_id: Optional run ID to filter recipients
        
        Behavior:
            - If both user_id and run_id are specified: send to that user's connections for that run
            - If only user_id is specified: send to all of that user's connections
            - If only run_id is specified: send to all connections subscribed to that run
            - If neither is specified: no messages are sent (invalid case)
        """
        if not user_id and not run_id:
            logger.warning("Cannot send message: neither user_id nor run_id specified")
            return
        
        # Convert IDs to strings for consistency
        user_id_str = str(user_id) if user_id else None
        run_id_str = str(run_id) if run_id else None
        
        # Determine target connections
        target_connections: Set[WebSocket] = set()
        
        if user_id_str and run_id_str:
            # Send to specific user's connections for specific run
            if (user_id_str in self.user_run_connections and 
                run_id_str in self.user_run_connections[user_id_str]):
                target_connections = self.user_run_connections[user_id_str][run_id_str]
        elif user_id_str:
            # Send to all of user's connections
            if user_id_str in self.user_connections:
                target_connections = self.user_connections[user_id_str]
        elif run_id_str:
            # Send to all connections subscribed to run
            if run_id_str in self.run_connections:
                target_connections = self.run_connections[run_id_str]
        
        if not target_connections:
            logger.debug(f"No active connections found for filters: user_id={user_id_str}, run_id={run_id_str}")
            return
        
        # Send the message to all target connections
        disconnected_sockets = []
        logger.debug(f"Sending JSON to {len(target_connections)} connections with filters: user_id={user_id_str}, run_id={run_id_str}")
        
        try:
            message = json.dumps(data)
            for connection in target_connections:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    logger.warning(f"WebSocket send error: {e}")
                    disconnected_sockets.append(connection)
        except Exception as e:
            logger.error(f"Error sending JSON: {e}", exc_info=True)
        
        # Clean up disconnected sockets
        for socket in disconnected_sockets:
            self.disconnect(socket)

# Global instance of the connection manager
websocket_manager = ConnectionManager()


@websocket_router.websocket("/{run_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    run_id: uuid.UUID = Path(..., description="The ID of the workflow run to subscribe to"),
    # user: User = Depends(get_current_active_verified_user),
    run: models.WorkflowRun = Depends(wf_deps.get_workflow_run_for_org),
    current_user: User = Depends(wf_deps.RequireRunReadActiveOrg),
    # active_org_id: uuid.UUID = Depends(get_active_org_id),
    # db_manager: AsyncGenerator[AsyncSession, None] = Depends(get_async_db_as_manager),
):
    """
    WebSocket endpoint for real-time notifications for a specific workflow run.
    
    Verifies the user has access to the run (run belongs to active org and user has run:read permission).
    Allows subscribing to specific run events.
    
    Args:
        websocket: The WebSocket connection
        run_id: The ID of the workflow run to subscribe to
        user: The authenticated user
        active_org_id: The active organization ID
        db_manager: The database session manager
    """
    user_id = str(current_user.id)
    run_id_str = str(run_id)
    
    # # Verify the run exists and belongs to the active organization
    # try:
    #     # This dependency checks if run belongs to active org and user has permission
    #     # run = await get_workflow_run_for_org(
    #     #     run_id=run_id,
    #     #     active_org_id=active_org_id,
    #     #     user=current_user,
    #     #     db_manager=db_manager
    #     # )
    #     if not run:
    #         logger.warning(f"Run {run_id} not found or not accessible by user {user_id}")
    #         await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    #         return
    # except HTTPException as e:
    #     logger.warning(f"Access denied: User {user_id} cannot access run {run_id}: {e.detail}")
    #     await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    #     return
    # except Exception as e:
    #     logger.error(f"Error verifying run access: {e}", exc_info=True)
    #     await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
    #     return
    
    try:
        # Register the connection
        await websocket_manager.connect(websocket, user_id)
        
        # Automatically subscribe to the run specified in the path
        await websocket_manager.subscribe_to_run(websocket, user_id, run_id_str)
        
        # Send a connection confirmation
        await websocket_manager.send_personal_message(
            json.dumps({
                "event": "connected",
                "user_id": user_id,
                "subscribed_run_id": run_id_str
            }),
            websocket
        )
        
        # Process client messages
        while True:
            data = await websocket.receive_json()
            
            if data.get("request") == "ping":
                await websocket_manager.send_personal_message(
                    json.dumps({"event_type": "status_update", "message": "pong"}),
                    websocket
                )
            # elif data.get("request") == "subscribe_to_run":
            #     # Verify the run exists and user has access before subscribing
            #     try:
            #         additional_run_id = data.get("run_id")
            #         if not additional_run_id:
            #             continue
                    
            #         additional_run = await get_workflow_run_for_org(
            #             run_id=uuid.UUID(additional_run_id),
            #             active_org_id=active_org_id,
            #             user=user,
            #             db=db
            #         )
            #         if additional_run:
            #             await websocket_manager.subscribe_to_run(websocket, user_id, str(additional_run_id))
            #             await websocket_manager.send_personal_message(
            #                 json.dumps({
            #                     "event": "subscribed",
            #                     "run_id": str(additional_run_id)
            #                 }),
            #                 websocket
            #             )
            #     except Exception as e:
            #         logger.warning(f"Error subscribing to run: {e}")
            #         await websocket_manager.send_personal_message(
            #             json.dumps({
            #                 "event": "error",
            #                 "message": "Failed to subscribe to run"
            #             }),
            #             websocket
            #         )
            # elif data.get("request") == "unsubscribe_from_run":
            #     run_id_to_unsub = data.get("run_id")
            #     if run_id_to_unsub:
            #         await websocket_manager.unsubscribe_from_run(websocket, user_id, str(run_id_to_unsub))
            #         await websocket_manager.send_personal_message(
            #             json.dumps({
            #                 "event": "unsubscribed",
            #                 "run_id": str(run_id_to_unsub)
            #             }),
            #             websocket
            #         )
            
            # Small delay to prevent tight loops
            await asyncio.sleep(0.1)
            
    except WebSocketDisconnect:
        # Handle client disconnecting gracefully
        websocket_manager.disconnect(websocket)
        logger.info(f"WebSocket disconnected: User {user_id}")
        
    except Exception as e:
        # Handle unexpected errors
        logger.error(f"WebSocket error for user {user_id}: {e}", exc_info=True)
        websocket_manager.disconnect(websocket)
        # Attempt to close WebSocket if not already closed
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except RuntimeError:
            # Connection might already be closed
            pass


@websocket_router.websocket("/notifications")
async def notifications_websocket_endpoint(
    websocket: WebSocket,
    user: User = Depends(get_current_active_verified_user),
    # active_org_id: uuid.UUID = Depends(get_active_org_id),
    db: AsyncSession = Depends(get_async_db_dependency),
):
    """
    WebSocket endpoint for general user notifications not tied to a specific workflow run.
    
    Establishes a persistent connection for sending real-time notifications to the user.
    This endpoint is used for system-wide notifications, alerts, and updates that are
    not specific to any particular workflow run.
    
    Args:
        websocket: The WebSocket connection
        user: The authenticated user
        active_org_id: The active organization ID
        db: The database session
    """
    user_id = str(user.id)
    
    try:
        # Register the connection for the user
        await websocket_manager.connect(websocket, user_id)
        
        # Send a connection confirmation
        await websocket_manager.send_personal_message(
            json.dumps({
                "event_type": "status_update",
                "user_id": user_id,
                "connection_type": "general_notifications",
                "message": "Connected to general notifications"
            }),
            websocket
        )
        
        # Process client messages
        while True:
            data = await websocket.receive_json()
            
            # Handle ping/pong for connection health checks
            if data.get("request") == "ping":
                await websocket_manager.send_personal_message(
                    json.dumps({"event": "pong"}),
                    websocket
                )
            
            # Add other message handlers as needed
            
            # Small delay to prevent tight loops
            await asyncio.sleep(0.1)
            
    except WebSocketDisconnect:
        # Handle client disconnecting gracefully
        websocket_manager.disconnect(websocket)
        logger.info(f"Notifications WebSocket disconnected: User {user_id}")
        
    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Notifications WebSocket error for user {user_id}: {e}", exc_info=True)
        websocket_manager.disconnect(websocket)
        # Attempt to close WebSocket if not already closed
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except RuntimeError:
            # Connection might already be closed
            pass



# Export the connection manager for use by event consumers
def get_websocket_manager() -> ConnectionManager:
    """Returns the global websocket connection manager instance."""
    return websocket_manager
