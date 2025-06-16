"""
API Test client for WebSocket endpoints defined in /services/kiwi_app/workflow_app/websockets.py.

Tests connections and basic interactions with:
- /ws/{run_id} (run-specific notifications)
- /ws/notifications (general user notifications)
- /ws (simple echo test endpoint)

Using websocket-client library (https://github.com/websocket-client/websocket-client)
"""
import json
import logging
import uuid
import time
import threading
from typing import Dict, Any, Optional, List, Callable, Union
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

import websocket
import rel

# Import authenticated client and config
from kiwi_client.auth_client import AuthenticatedClient, AuthenticationError
from kiwi_client.test_config import (
    CLIENT_LOG_LEVEL,
    WS_RUN_BASE_URL,
    WS_NOTIFICATIONS_URL,
    TEST_USER_EMAIL,
    API_BASE_URL,
    BASE_HOST,
    # EXAMPLE_RUN_ID,
)

EXAMPLE_RUN_ID = ""
ENABLE_WEBSOCKET_TRACE = False

# Setup logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=CLIENT_LOG_LEVEL)

class WebSocketTestClient:
    """
    Provides methods to test WebSocket endpoints using websocket-client library.
    Uses callback-based event handling and supports automatic reconnection.
    """
    def __init__(self, auth_client: AuthenticatedClient, enable_trace: bool = False):
        """
        Initializes the WebSocketTestClient.

        Args:
            auth_client (AuthenticatedClient): An instance of AuthenticatedClient,
                                              assumed to be logged in (cookies are set).
            enable_trace (bool): Whether to enable websocket debug tracing.
        """
        self._auth_client: AuthenticatedClient = auth_client
        self._active_connections: List[websocket.WebSocketApp] = []
        self._enable_trace = enable_trace
        
        # Configure tracing if enabled
        if self._enable_trace:
            websocket.enableTrace(True)
            
        logger.info(f"WebSocketTestClient initialized for user: {self._auth_client._email}")



    def _get_active_org_id(self) -> Optional[str]:
        """
        Extracts the active organization ID from the AuthenticatedClient's headers.
        
        Returns:
            Optional[str]: The active organization ID, or None if not available
        """
        if not self._auth_client.client or "X-Active-Org" not in self._auth_client.client.headers:
            logger.warning("No X-Active-Org header found in AuthenticatedClient")
            return None
            
        active_org_id = self._auth_client.client.headers.get("X-Active-Org", "")
        logger.debug(f"Extracted active org ID: {active_org_id}")
        return active_org_id

    def _add_params_to_url(self, url: str, include_active_org: bool = True) -> str:
        """
        Adds required parameters to the WebSocket URL:
        - active_org_id: organization ID from X-Active-Org header (optional)
        
        Note: JWT token is now passed via cookies instead of query parameters.
        
        Args:
            url (str): The original WebSocket URL
            include_active_org (bool): Whether to include the active_org_id parameter
            
        Returns:
            str: The URL with query parameters added
        """
        # Parse URL into components
        parsed = urlparse(url)
        
        # Parse existing query parameters
        query_dict = dict(parse_qsl(parsed.query))
        
        # Add active_org_id parameter if requested
        if include_active_org:
            active_org_id = self._get_active_org_id()
            if active_org_id:
                query_dict['active_org_id'] = active_org_id
        
        # Rebuild the URL with the new query string
        new_query = urlencode(query_dict)
        new_url = urlunparse((
            parsed.scheme, 
            parsed.netloc, 
            parsed.path, 
            parsed.params, 
            new_query, 
            parsed.fragment
        ))
        
        logger.debug(f"URL with parameters: {new_url}")
        return new_url

    def _get_header_dict(self) -> Dict[str, str]:
        """
        Creates a header dictionary for the WebSocket connection.
        Includes all cookies from the authenticated client, including the access_token cookie.
        
        Returns:
            Dict[str, str]: A dictionary of headers to include in the WebSocket connection
        """
        # Initialize headers with any needed ones for WebSocket connection
        headers = {}
        
        # Add any custom headers needed for authentication
        if self._auth_client.client:
            # Add X-Active-Org header if present in the httpx client
            if "X-Active-Org" in self._auth_client.client.headers:
                headers["X-Active-Org"] = self._auth_client.client.headers["X-Active-Org"]
            
            # Add all cookies from the httpx client (which includes access_token and refresh_token)
            if self._auth_client.client.cookies:
                cookie_parts = []
                for name, value in self._auth_client.client.cookies.items():
                    cookie_parts.append(f"{name}={value}")
                
                if cookie_parts:
                    headers["Cookie"] = "; ".join(cookie_parts)
                    logger.debug(f"WebSocket cookies: {headers['Cookie']}")
                    
        return headers

    def create_websocket_app(
        self, 
        url: str,
        include_active_org: bool = True,
        include_auth: bool = True,
        on_message: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_close: Optional[Callable] = None,
        on_open: Optional[Callable] = None,
        on_ping: Optional[Callable] = None,
        on_pong: Optional[Callable] = None,
    ) -> websocket.WebSocketApp:
        """
        Creates a WebSocketApp for the given URL with authentication parameters and callbacks.
        
        Args:
            url (str): The WebSocket URL to connect to
            include_active_org (bool): Whether to include active_org_id in the URL parameters
            include_auth (bool): Whether to include authentication parameters
            on_message: Callback for message events
            on_error: Callback for error events
            on_close: Callback for connection close events
            on_open: Callback for connection open events
            on_ping: Callback for ping events
            on_pong: Callback for pong events
            
        Returns:
            websocket.WebSocketApp: The configured WebSocketApp instance
        """
        # Add parameters to URL and prepare headers if authentication is needed
        if include_auth:
            url_with_params = self._add_params_to_url(url, include_active_org)
            headers = self._get_header_dict()  # This includes JWT token as access_token cookie
        else:
            url_with_params = url
            headers = {}
        
        logger.info(f"Creating WebSocketApp for URL: {url_with_params}")
        if headers:
            logger.debug(f"WebSocket headers: {headers}")
        
        # Create WebSocketApp with callbacks
        ws_app = websocket.WebSocketApp(
            url_with_params,
            header=headers,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
            on_ping=on_ping,
            on_pong=on_pong
        )
        
        # Track the connection
        self._active_connections.append(ws_app)
        
        return ws_app
    
    def connect_to_run_notifications(
        self, 
        run_id: Union[str, uuid.UUID],
        on_message: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_close: Optional[Callable] = None,
        on_open: Optional[Callable] = None
    ) -> websocket.WebSocketApp:
        """
        Creates a WebSocketApp for the run-specific notifications endpoint.
        
        Args:
            run_id: The ID of the workflow run to subscribe to
            on_message: Callback for message events
            on_error: Callback for error events
            on_close: Callback for connection close events
            on_open: Callback for connection open events
            
        Returns:
            websocket.WebSocketApp: The configured WebSocketApp instance
        """
        run_id_str = str(run_id)
        url = WS_RUN_BASE_URL(run_id_str)
        
        logger.info(f"Connecting to run-specific notifications for run ID: {run_id_str}")
        return self.create_websocket_app(
            url=url,
            include_active_org=True,  # Run endpoint requires active_org_id
            include_auth=True,
            on_message=on_message or default_on_message,
            on_error=on_error or default_on_error,
            on_close=on_close or default_on_close,
            on_open=on_open or default_on_open
        )
    
    def connect_to_general_notifications(
        self,
        on_message: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_close: Optional[Callable] = None,
        on_open: Optional[Callable] = None
    ) -> websocket.WebSocketApp:
        """
        Creates a WebSocketApp for the general notifications endpoint.
        
        Args:
            on_message: Callback for message events
            on_error: Callback for error events
            on_close: Callback for connection close events
            on_open: Callback for connection open events
            
        Returns:
            websocket.WebSocketApp: The configured WebSocketApp instance
        """
        url = WS_NOTIFICATIONS_URL
        
        logger.info("Connecting to general notifications")
        return self.create_websocket_app(
            url=url,
            include_active_org=False,  # General notifications endpoint doesn't require active_org_id
            include_auth=True,         # Still needs token for authentication
            on_message=on_message or default_on_message,
            on_error=on_error or default_on_error,
            on_close=on_close or default_on_close,
            on_open=on_open or default_on_open
        )
        
    def connect_to_test_endpoint(
        self,
        on_message: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_close: Optional[Callable] = None,
        on_open: Optional[Callable] = None
    ) -> websocket.WebSocketApp:
        """
        Creates a WebSocketApp for the simple test endpoint at /ws.
        This endpoint doesn't require authentication and just echoes messages back.
        It's useful for testing basic WebSocket functionality.
        
        Args:
            on_message: Callback for message events
            on_error: Callback for error events
            on_close: Callback for connection close events
            on_open: Callback for connection open events
            
        Returns:
            websocket.WebSocketApp: The configured WebSocketApp instance
        """
        # Construct the simple WebSocket URL at /ws (no authentication required)
        # Note: /ws is at the root level, not under /api/v1
        ws_url = BASE_HOST.replace("http", "ws").replace("https", "wss") + "/ws"
        
        logger.info(f"Connecting to simple test WebSocket at {ws_url}")
        
        return self.create_websocket_app(
            url=ws_url,
            include_active_org=False,  # No org ID needed
            include_auth=False,        # No authentication needed
            on_message=on_message or default_on_message_echo,
            on_error=on_error or default_on_error,
            on_close=on_close or default_on_close,
            on_open=on_open or default_on_open_echo
        )
    
    def connect_to_debug_endpoint(
        self,
        on_message: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_close: Optional[Callable] = None,
        on_open: Optional[Callable] = None
    ) -> websocket.WebSocketApp:
        """
        Creates a WebSocketApp for the debug endpoint.
        
        This endpoint helps troubleshoot cookie and authentication issues.
        
        Args:
            on_message: Callback for message events
            on_error: Callback for error events
            on_close: Callback for connection close events
            on_open: Callback for connection open events
            
        Returns:
            websocket.WebSocketApp: The configured WebSocketApp instance
        """
        # Construct the debug WebSocket URL (similar to WS_NOTIFICATIONS_URL pattern)
        debug_url = API_BASE_URL.replace("https", "wss").replace("http", "ws") + "/ws/debug"
        
        logger.info(f"Connecting to debug WebSocket endpoint at {debug_url}")
        
        # Default on_message handler for debug endpoint
        def debug_on_message(ws, message):
            logger.info(f"Debug endpoint message: {message}")
            try:
                data = json.loads(message)
                if data.get("event") == "debug_info":
                    logger.info("=== Debug Info from Server ===")
                    logger.info(f"Headers received: {data.get('headers', {})}")
                    logger.info(f"Cookie header: {data.get('cookie_header', 'None')}")
                    logger.info(f"Access token present: {data.get('access_token_present', False)}")
                    logger.info(f"Access token preview: {data.get('access_token_first_10', 'None')}")
            except json.JSONDecodeError:
                pass
        
        return self.create_websocket_app(
            url=debug_url,
            include_active_org=False,  # Debug endpoint doesn't need org ID
            include_auth=True,         # Include auth to test cookie passing
            on_message=on_message or debug_on_message,
            on_error=on_error or default_on_error,
            on_close=on_close or default_on_close,
            on_open=on_open or default_on_open
        )
    
    def run_websocket(
        self, 
        ws: websocket.WebSocketApp, 
        reconnect_interval: int = 5,
        use_dispatcher: bool = True
    ) -> None:
        """
        Start running the WebSocketApp either with a dispatcher or in a new thread.
        
        Args:
            ws (websocket.WebSocketApp): The WebSocketApp to run
            reconnect_interval (int): Seconds to wait before reconnecting on unexpected closure
            use_dispatcher (bool): Whether to use the rel dispatcher for automatic reconnection
        """
        if use_dispatcher:
            # Using rel dispatcher for automatic reconnection
            ws.run_forever(dispatcher=rel, reconnect=reconnect_interval)
        else:
            # Run in a separate thread without automatic reconnection
            threading.Thread(target=ws.run_forever).start()
    
    def close_connection(self, ws: websocket.WebSocketApp) -> None:
        """
        Closes a specific WebSocket connection.
        
        Args:
            ws (websocket.WebSocketApp): The WebSocket to close
        """
        if ws in self._active_connections:
            logger.info("Closing WebSocket connection")
            ws.close()
            self._active_connections.remove(ws)
            
    def close_all_connections(self) -> None:
        """
        Closes all active WebSocket connections managed by this client.
        """
        logger.info(f"Closing all {len(self._active_connections)} active WebSocket connections...")
        
        # Make a copy of the list since we'll be modifying it during iteration
        for ws in list(self._active_connections):
            self.close_connection(ws)
            
        logger.info("All WebSocket connections closed.")
    
    @staticmethod
    def send_json_message(ws: websocket.WebSocketApp, message: Dict[str, Any]) -> None:
        """
        Sends a JSON message over the WebSocket.
        
        Args:
            ws (websocket.WebSocketApp): The WebSocket to send the message through
            message (Dict[str, Any]): The message to send as JSON
        """
        if not ws:
            logger.warning("Cannot send message: WebSocket is None")
            return
            
        try:
            json_message = json.dumps(message)
            ws.send(json_message)
            logger.debug(f"Sent message: {json_message}")
        except Exception as e:
            logger.error(f"Error sending JSON message: {e}")
            
    @staticmethod
    def send_text_message(ws: websocket.WebSocketApp, message: str) -> None:
        """
        Sends a text message over the WebSocket.
        
        Args:
            ws (websocket.WebSocketApp): The WebSocket to send the message through
            message (str): The text message to send
        """
        if not ws:
            logger.warning("Cannot send message: WebSocket is None")
            return
            
        try:
            ws.send(message)
            logger.debug(f"Sent text message: {message}")
        except Exception as e:
            logger.error(f"Error sending text message: {e}")


# --- Default Callback Handlers ---
def default_on_message(ws, message):
    """Default handler for WebSocket messages"""
    try:
        # Try to parse as JSON for prettier logging
        parsed = json.loads(message)
        logger.info(f"Received message: {json.dumps(parsed, indent=2)}")
    except (json.JSONDecodeError, TypeError):
        # If not JSON or other error, print as is
        logger.info(f"Received message: {message}")

def default_on_message_echo(ws, message):
    """Default handler for echo WebSocket messages - prints and responds"""
    logger.info(f"Received echo message: {message}")
    
    # For the test endpoint, automatically send a response
    response = f"Reply to: {message}"
    try:
        ws.send(response)
        logger.info(f"Sent echo response: {response}")
    except Exception as e:
        logger.error(f"Error sending echo response: {e}")

def default_on_error(ws, error):
    """Default handler for WebSocket errors"""
    logger.error(f"WebSocket error: {error}")
    
    # Extract more details from the error if possible
    if hasattr(error, "status_code"):
        logger.error(f"Status code: {error.status_code}")
    if hasattr(error, "headers"):
        logger.error(f"Headers: {error.headers}")
    if hasattr(error, "body"):
        logger.error(f"Response body: {error.body}")

def default_on_close(ws, close_status_code, close_msg):
    """Default handler for WebSocket closure"""
    logger.info(f"WebSocket closed: status={close_status_code}, message={close_msg}")

def default_on_open(ws):
    """Default handler for WebSocket opening"""
    logger.info("WebSocket connection established")
    
    # Send a ping message when the connection is established to ensure it's working
    try:
        ws.send(json.dumps({"request": "ping"}))
        logger.info("Sent initial ping message")
    except Exception as e:
        logger.error(f"Error sending initial ping: {e}")

def default_on_open_echo(ws):
    """Default handler for simple echo WebSocket opening"""
    logger.info("Echo WebSocket connection established")
    
    # Send a simple text message for the echo endpoint
    try:
        ws.send("Hello from WebSocketTestClient!")
        logger.info("Sent initial hello message to echo endpoint")
    except Exception as e:
        logger.error(f"Error sending initial echo message: {e}")


# --- Example Usage ---
def example_usage():
    """
    Example of how to use the WebSocketTestClient.
    
    This demonstrates:
    1. Creating a test client
    2. Connecting to general notifications
    3. Setting up custom handlers
    4. Running the connection with automatic reconnection
    """
    # Callback when a message is received
    def on_message(ws, message):
        try:
            data = json.loads(message)

            text_msges = []
            text_keys = ["text", "partial_json", "json", "thinking", "reasoning", "reason", "think"]
            if data.get("event_type") == "message_chunk":
                content_or_content_list = data.get("message", {}).get("content", {})
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

            if text_msg:
                print(text_msg, end="")
            else:
                print(f"\n\nReceived: {data}\n\n")
            
            # Example of how to respond to specific messages
            if data.get("event_type") == "status_update" and "Connected" in data.get("message", ""):
                print("Connection confirmed, sending ping")
                ws.send(json.dumps({"request": "ping"}))
        except json.JSONDecodeError:
            print(f"Received non-JSON message: {message}")
    
    # Callback when the connection is established
    def on_open(ws):
        print("Connection opened!")
        # Send a ping right away
        ws.send(json.dumps({"request": "ping"}))
    
    # Callback for errors with more detailed logging
    def on_error(ws, error):
        print(f"WebSocket error: {error}")
        # Print details from the error
        if hasattr(error, "status_code"):
            print(f"Status code: {error.status_code}")
        if hasattr(error, "headers"):
            print(f"Headers: {error.headers}")
        if hasattr(error, "body"):
            print(f"Response body: {error.body}")
    
    async def run_example():
        # Create authenticated client
        async with AuthenticatedClient() as auth_client:
            # Verify auth client has the access_token cookie
            if not auth_client.access_token:
                print("Failed to get access_token cookie. Check your credentials.")
                return
                
            print(f"Access token cookie: {auth_client.access_token[:10]}...")
            print(f"Active Org ID: {auth_client.active_org_id}")
            print(f"All cookies: {list(auth_client.client.cookies.keys())}")
            
            # Create WebSocket test client
            ws_client = WebSocketTestClient(auth_client, enable_trace=ENABLE_WEBSOCKET_TRACE)
            
            try:
                # # Connect to the simple test endpoint first (no auth required)
                # print("\n=== Testing simple echo WebSocket ===")
                # echo_ws = ws_client.connect_to_test_endpoint(
                #     on_message=on_echo_message,
                #     on_error=on_error,
                #     on_close=default_on_close,
                #     on_open=on_echo_open
                # )
                
                # # Run in a separate thread without rel dispatcher
                # ws_client.run_websocket(echo_ws, use_dispatcher=False)
                
                # # Wait a bit to see echo results
                # print("Waiting for echo responses...")
                # await asyncio.sleep(5)
                # print("Echo test completed.\n")
                
                # Now try the authenticated endpoints
                print("\n=== Testing authenticated WebSocket ===")
                # Connect to general notifications
                
                ########################

                if EXAMPLE_RUN_ID:

                    run_ws = ws_client.connect_to_run_notifications(
                        run_id=EXAMPLE_RUN_ID,
                        on_message=on_message,
                        on_error=on_error,
                        on_close=default_on_close,
                        on_open=on_open
                    )
                    ws_client.run_websocket(run_ws, reconnect_interval=5)

                ########################


                
                notifications_ws = ws_client.connect_to_general_notifications(
                    on_message=on_message,
                    on_error=on_error,
                    on_close=default_on_close,
                    on_open=on_open
                )

                # Run with rel dispatcher for automatic reconnection
                ws_client.run_websocket(notifications_ws, reconnect_interval=5)

                # Use rel dispatcher to maintain connections
                rel.signal(2, rel.abort)  # Allow keyboard interrupt to stop
                rel.dispatch()
                
            finally:
                # Clean up connections
                ws_client.close_all_connections()
    
    # Run the example
    import asyncio
    asyncio.run(run_example())


def test_simple_endpoint():
    """
    Simple test function for the basic /ws endpoint only.
    This function doesn't require authentication or the full client setup.
    
    This is a good first test to run to verify that basic WebSocket 
    functionality is working properly.
    """
    import asyncio
    import time
    import websocket
    import rel
    
    # Construct the WebSocket URL
    ws_url = BASE_HOST.replace("http", "ws").replace("https", "wss") + "/ws"
    
    print(f"=== Testing Simple WebSocket at {ws_url} ===")
    
    # Enable detailed logging
    websocket.enableTrace(True)
    
    # Define message handler function
    message_count = 0
    
    def on_message(ws, message):
        nonlocal message_count
        print(f"RECEIVED: {message}")
        message_count += 1
        
        # Send a few test messages
        if message_count < 3:
            time.sleep(1)
            next_message = f"Test message #{message_count + 1}" 
            ws.send(next_message)
            print(f"SENT: {next_message}")
        else:
            print("Test complete - received 3 messages.")
            # Close the connection
            ws.close()
            rel.abort()
    
    def on_error(ws, error):
        print(f"ERROR: {error}")
    
    def on_close(ws, close_status_code, close_msg):
        print(f"CONNECTION CLOSED: {close_status_code} - {close_msg}")
    
    def on_open(ws):
        print("CONNECTION ESTABLISHED")
        # Send first test message
        first_message = "Test message #1"
        ws.send(first_message)
        print(f"SENT: {first_message}")
    
    # Create WebSocket connection
    ws = websocket.WebSocketApp(
        ws_url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )
    
    # Run with rel dispatcher for clean exit
    ws.run_forever(dispatcher=rel)
    rel.dispatch()


def test_debug_endpoint():
    """
    Test function for the debug WebSocket endpoint.
    This helps troubleshoot cookie and authentication issues.
    """
    import asyncio
    
    async def run_debug_test():
        # Create authenticated client
        async with AuthenticatedClient() as auth_client:
            # Verify auth client has the access_token cookie
            if not auth_client.access_token:
                print("Failed to get access_token cookie. Check your credentials.")
                return
                
            print(f"Access token cookie: {auth_client.access_token[:10]}...")
            print(f"Active Org ID: {auth_client.active_org_id}")
            print(f"All cookies: {list(auth_client.client.cookies.keys())}")
            
            # Create WebSocket test client
            ws_client = WebSocketTestClient(auth_client, enable_trace=ENABLE_WEBSOCKET_TRACE)
            
            print("\n=== Testing Debug WebSocket Endpoint ===")
            
            # Connect to debug endpoint
            debug_ws = ws_client.connect_to_debug_endpoint()
            
            # Run without dispatcher for simple test
            ws_client.run_websocket(debug_ws, use_dispatcher=False)
            
            # Wait a bit to see results
            await asyncio.sleep(3)
            
            # Send a test message
            WebSocketTestClient.send_text_message(debug_ws, "Test message from client")
            
            await asyncio.sleep(2)
            
            # Close connection
            ws_client.close_connection(debug_ws)
            
            print("\n=== Debug Test Complete ===")
    
    # Run the test
    import asyncio
    asyncio.run(run_debug_test())


if __name__ == "__main__":
    import sys

    # test_simple_endpoint()
    
    # Check for command-line arguments to determine which test to run
    if len(sys.argv) > 1:
        if sys.argv[1] == "simple":
            # Just test the simple /ws endpoint without authentication
            print("Running simple WebSocket test (no authentication required)")
            test_simple_endpoint()
        elif sys.argv[1] == "debug":
            # Test the debug endpoint to troubleshoot cookie issues
            print("Running debug WebSocket test to check cookie passing")
            test_debug_endpoint()
        else:
            print("Unknown test option. Available options: simple, debug")
    else:
        # Run the full example with authentication
        print("Attempting to run full WebSocket test client...")
        print("To test only the simple endpoint without authentication, run:")
        print("PYTHONPATH=. python standalone_test_client/kiwi_client/websocket_client.py simple")
        print("To test cookie passing and authentication, run:")
        print("PYTHONPATH=. python standalone_test_client/kiwi_client/websocket_client.py debug")
        example_usage() 
