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
from kiwi_app.auth.dependencies import _check_permissions_for_org, get_current_user_non_dependency, get_user_dao
from kiwi_app.workflow_app.constants import WorkflowPermissions
from kiwi_app.auth.models import User

# Workflow App Dependencies
from kiwi_app.workflow_app import crud, models, dependencies as wf_deps
from kiwi_app.workflow_app.dependencies import get_workflow_run_for_org

from kiwi_app.utils import get_kiwi_logger

logger = get_kiwi_logger(name="kiwi.websockets")

# Setup Router
websocket_router = APIRouter(tags=["WebSocket Stream & Notifications"])




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
        # logger.debug(f"Sending JSON to {len(target_connections)} connections with filters: user_id={user_id_str}, run_id={run_id_str}")
        
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


@websocket_router.websocket("/ws/runs/{run_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    run_id: uuid.UUID = Path(..., description="The ID of the workflow run to subscribe to"),
    token: str = Query(..., description="The JWT token for the user"),
    active_org_id: uuid.UUID = Query(..., description="The active organization ID"),
    db: AsyncSession = Depends(get_async_db_dependency),
):
    """
    WebSocket endpoint for real-time notifications for a specific workflow run.
    
    Verifies the user has access to the run (run belongs to active org and user has run:read permission).
    Allows subscribing to specific run events.
    
    Args:
        websocket: The WebSocket connection
        run_id: The ID of the workflow run to subscribe to
        token: The JWT token for authentication
        active_org_id: The active organization ID
        db: The database session
    """
    # Log connection attempt with details
    # logger.debug(f"WebSocket connection attempt to run {run_id}")
    # logger.debug(f"Request headers: {websocket.headers}")
    # logger.debug(f"Active org ID from query: {active_org_id}")
    # logger.debug(f"Token received (first 10 chars): {token[:10]}...")
    
    # Authenticate the user from the token
    try:
        # logger.debug(f"Attempting to authenticate user with token")
        user = await get_current_user_non_dependency(db, token)
        if not user:
            logger.warning(f"Invalid token for WebSocket connection to run {run_id}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # logger.debug(f"User authenticated successfully: {user.email} (ID: {user.id})")
            
        # Verify user is active and verified
        if not user.is_active:
            logger.warning(f"Inactive user {user.id} attempted WebSocket connection")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # logger.debug(f"User is active: {user.is_active}")
            
        if not user.is_verified:
            logger.warning(f"Unverified user {user.id} attempted WebSocket connection")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # logger.debug(f"User is verified: {user.is_verified}")
            
        # Check permission directly using _check_permissions_for_org
        user_dao = get_user_dao()
        # logger.debug(f"Checking permissions for user {user.id} in org {active_org_id}")
        try:
            await _check_permissions_for_org(
                db=db,
                user_dao=user_dao,
                user=user,
                org_id=active_org_id,
                required_permissions=[WorkflowPermissions.RUN_READ]
            )
            # logger.debug(f"Permission check passed for user {user.id} in org {active_org_id}")
        except Exception as e:
            logger.warning(f"Permission denied: User {user.id} cannot access run {run_id}: {str(e)}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Verify the run exists and belongs to the active organization
        workflow_run_dao = crud.WorkflowRunDAO()
        # logger.debug(f"Verifying run {run_id} exists and belongs to org {active_org_id}")
        run = await workflow_run_dao.get_run_by_id_and_org(db, run_id=run_id, org_id=active_org_id)
        if not run:
            logger.warning(f"Run {run_id} not found or not accessible by user {user.id}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # logger.debug(f"Run {run_id} found and belongs to org {active_org_id}")
    except Exception as e:
        logger.error(f"Error during WebSocket authentication or permission check: {e}", exc_info=True)
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return
    
    user_id = str(user.id)
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
    # logger.debug(f"All authentication and permission checks passed. Accepting WebSocket connection for user {user_id}")
    
    try:
        # Register the connection
        await websocket_manager.connect(websocket, user_id)
        # logger.debug(f"WebSocket connection registered for user {user_id}")
        
        # Automatically subscribe to the run specified in the path
        await websocket_manager.subscribe_to_run(websocket, user_id, run_id_str)
        # logger.debug(f"User {user_id} subscribed to run {run_id_str}")
        
        # Send a connection confirmation
        await websocket_manager.send_personal_message(
            json.dumps({
                "event": "connected",
                "user_id": user_id,
                "subscribed_run_id": run_id_str
            }),
            websocket
        )
        # logger.debug(f"Connection confirmation sent to user {user_id}")
        
        # Process client messages
        while True:
            data = await websocket.receive_json()
            # logger.debug(f"Received message from user {user_id}: {data}")
            
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
                # logger.debug(f"Sent pong response to user {user_id}")
            
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


@websocket_router.websocket("/ws/notifications")
async def notifications_websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="The JWT token for the user"),
    db: AsyncSession = Depends(get_async_db_dependency),
):
    """
    WebSocket endpoint for general user notifications not tied to a specific workflow run.
    
    Establishes a persistent connection for sending real-time notifications to the user.
    This endpoint is used for system-wide notifications, alerts, and updates that are
    not specific to any particular workflow run.
    
    Args:
        websocket: The WebSocket connection
        token: The JWT token for authentication
        db: The database session
    """
    # Log connection attempt with details
    # logger.debug(f"WebSocket connection attempt to general notifications")
    # logger.debug(f"Request headers: {websocket.headers}")
    # logger.debug(f"Token received (first 10 chars): {token[:10]}...")
    
    # Authenticate the user from the token
    try:
        # logger.debug(f"Attempting to authenticate user with token")
        user = await get_current_user_non_dependency(db, token)
        if not user:
            logger.warning("Invalid token for WebSocket general notifications connection")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # logger.debug(f"User authenticated successfully: {user.email} (ID: {user.id})")
            
        # Verify user is active and verified
        if not user.is_active:
            logger.warning(f"Inactive user {user.id} attempted WebSocket connection")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # logger.debug(f"User is active: {user.is_active}")
            
        if not user.is_verified:
            logger.warning(f"Unverified user {user.id} attempted WebSocket connection")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # logger.debug(f"User is verified: {user.is_verified}")
            
    except Exception as e:
        logger.error(f"Error during WebSocket authentication: {e}", exc_info=True)
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return
        
    user_id = str(user.id)
    # logger.debug(f"All authentication checks passed. Accepting WebSocket connection for user {user_id}")
    
    try:
        # Register the connection for the user
        await websocket_manager.connect(websocket, user_id)
        # logger.debug(f"WebSocket connection registered for user {user_id}")
        
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
        # logger.debug(f"Connection confirmation sent to user {user_id}")
        
        # Process client messages
        while True:
            data = await websocket.receive_json()
            # logger.debug(f"Received message from user {user_id}: {data}")
            
            # Handle ping/pong for connection health checks
            if data.get("request") == "ping":
                await websocket_manager.send_personal_message(
                    json.dumps({"event": "pong"}),
                    websocket
                )
                # logger.debug(f"Sent pong response to user {user_id}")
            
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
