import logging
import logging.handlers
import queue
import threading
import os
import atexit
from typing import List, Optional, Union

from prefect.exceptions import MissingContextError

from global_config.settings import global_settings, LOG_ROOT

# --- Global Queue and Listener ---
# Using a single global queue simplifies setup.
# The listener is also global to manage its lifecycle (start/stop).
log_queue: queue.Queue = queue.Queue()
listener: Optional[logging.handlers.QueueListener] = None

# --- Default Configuration ---
# Sensible defaults for common use cases. Can be overridden via setup_logging.
DEFAULT_LOG_LEVEL: int = logging.INFO
DEFAULT_CONSOLE_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DEFAULT_FILE_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - [%(pathname)s:%(lineno)d] - %(message)s'
DEFAULT_LOG_DIR: str = './logs' # Relative to current working directory
DEFAULT_LOG_FILENAME: str = 'app.log'
DEFAULT_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB
DEFAULT_BACKUP_COUNT: int = 5


def get_prefect_or_regular_python_logger(name: str, log_level: int = global_settings.LOG_LEVEL, return_non_prefect_logger: bool = True) -> logging.Logger:
    """
    Returns the appropriate logger based on the environment.
    """
    from prefect.logging import get_run_logger
    try:
        logger = get_run_logger()
        logger.setLevel(log_level)
        return logger
    except MissingContextError:
        return get_logger(name) if return_non_prefect_logger else None


def setup_logging(
    log_level: int = DEFAULT_LOG_LEVEL,
    console_format: str = DEFAULT_CONSOLE_FORMAT,
    file_format: str = DEFAULT_FILE_FORMAT,
    log_to_console: bool = True,
    log_to_file: bool = True,
    log_dir: str = DEFAULT_LOG_DIR,
    log_filename: str = DEFAULT_LOG_FILENAME,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> None:
    """
    Configures asynchronous, non-blocking logging for the application.

    Uses a QueueHandler to send log records to a background QueueListener
    thread, which then dispatches them to configured handlers (console, file).
    This prevents logging I/O from blocking the main application threads.

    It's recommended to call this function once at application startup.
    Subsequent calls will stop the existing listener and reconfigure.

    Args:
        log_level (int): The minimum logging level for the root logger
                         (e.g., logging.DEBUG, logging.INFO).
                         Defaults to logging.INFO.
        console_format (str): The format string for console log messages.
        file_format (str): The format string for file log messages.
        log_to_console (bool): If True, enables logging to standard output (stderr).
                               Defaults to True.
        log_to_file (bool): If True, enables logging to a rotating file.
                            Defaults to True.
        log_dir (str): The directory where log files will be stored.
                       It will be created if it doesn't exist.
                       Defaults to './logs'.
        log_filename (str): The name of the log file. Defaults to 'app.log'.
        max_bytes (int): The maximum size (in bytes) a log file can reach
                         before rotating. Defaults to 10MB.
        backup_count (int): The number of old log files to keep. Defaults to 5.

    Raises:
        OSError: If the log directory cannot be created.
    """
    global listener
    global log_queue # Ensure we are using the global queue

    # --- Create Target Handlers ---
    handlers: List[logging.Handler] = []
    console_formatter = logging.Formatter(console_format)
    file_formatter = logging.Formatter(file_format)

    if log_to_console:
        # Logs to stderr by default
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)
        # Set level on the handler itself to potentially filter
        # messages even if the root logger level is lower.
        # However, typically filtering is done at the logger level.
        # console_handler.setLevel(log_level) # Optional: filter at handler level
        handlers.append(console_handler)
        # print("Console logging enabled.") # Use print, logger not fully setup yet

    if log_to_file:
        try:
            # Ensure the log directory exists; create if not.
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, log_filename)

            # Use RotatingFileHandler for size-based rotation.
            # Consider TimedRotatingFileHandler for time-based rotation.
            file_handler = logging.handlers.RotatingFileHandler(
                filename=log_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8' # Explicitly set encoding
            )
            file_handler.setFormatter(file_formatter)
            # file_handler.setLevel(log_level) # Optional: filter at handler level
            handlers.append(file_handler)
            # print(f"File logging enabled: {log_path}")
        except OSError as e:
            # Use print because logging might fail if directory creation failed
            # print(f"Error setting up file logging in directory '{log_dir}': {e}")
            # Decide whether to raise, log a warning, or continue without file logging
            # For now, let's print the error and continue without file logging
            # raise # Uncomment to make directory creation failure fatal
            log_to_file = False # Disable if setup failed

    if not handlers:
        # Avoid setting up queue logging if no actual handlers are configured
        # This can happen if both log_to_console and log_to_file are False,
        # or if file logging setup failed.
        # print("Warning: No logging handlers configured (console or file). Logging setup skipped.")
        return

    # --- Configure Queue Handling ---
    # The QueueHandler takes log records and puts them onto the global queue.
    queue_handler = logging.handlers.QueueHandler(log_queue)

    # --- Configure Root Logger ---
    # Get the root logger. Configuring the root logger makes this setup
    # automatically apply to all loggers obtained via logging.getLogger()
    # unless they specifically disable propagation or override handlers.
    root_logger = logging.getLogger()

    # Remove existing handlers attached to the root logger.
    # This is crucial if setup_logging is called multiple times or if
    # other libraries have already configured logging.
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add our queue handler to the root logger.
    root_logger.addHandler(queue_handler)

    # Set the desired level on the root logger.
    # This determines which messages are even processed and put into the queue.
    root_logger.setLevel(log_level)

    # --- Start the Listener ---
    # Stop the existing listener if setup_logging is called again.
    stop_listener() # Ensure any previous listener is stopped

    # The QueueListener pulls records from log_queue and passes them to
    # the actual handlers (console, file) in its own thread.
    # respect_handler_level=True means the listener will check handler levels too.
    listener = logging.handlers.QueueListener(log_queue, *handlers, respect_handler_level=True)
    listener.start()
    # print("Logging listener thread started.")

    # --- Register Shutdown Hook ---
    # Ensure the listener is stopped gracefully on normal Python exit.
    # This allows the queue to be flushed.
    atexit.register(stop_listener)

    # Use the newly configured logger to indicate completion
    # Note: This message goes through the queue now.
    # logging.getLogger(__name__).info("Asynchronous logging setup complete.")

logging_is_setup = False

def get_logger(
        name: str, 
        log_level: str = global_settings.LOG_LEVEL, 
        log_filename: str = global_settings.LOG_FILE_NAME,
        log_dir: str = LOG_ROOT,
        log_to_console: bool = global_settings.APP_ENV == "DEV",
        log_to_file: bool = True,
    ) -> logging.Logger:
    """
    Retrieves a logger instance with the specified name.

    This is the standard way application modules should get their logger.
    Since the root logger is configured by setup_logging, loggers obtained
    via this function will automatically inherit the asynchronous setup
    (i.e., their records will go through the QueueHandler).

    Args:
        name (str): The name for the logger. Typically, use __name__ for
                    the calling module to leverage the logging hierarchy.

    Returns:
        logging.Logger: The logger instance.
    """
    global logging_is_setup
    if not logging_is_setup:
        setup_logging(
            log_level=log_level,
            log_to_console=log_to_console,
            log_to_file=log_to_file,
            log_dir=log_dir,
            log_filename=log_filename
        )
        # logging_is_setup = True
    # Simply return the logger. Configuration is handled at the root level.
    return logging.getLogger(name)


def stop_listener() -> None:
    """
    Stops the logging listener thread gracefully.

    This function is registered with atexit to be called on normal exit,
    but can also be called manually if needed (e.g., during specific
    application shutdown phases before atexit runs).
    """
    global listener
    if listener:
        try:
            current_thread_name = threading.current_thread().name
            # Use print here as logging might be shutting down or stopped
            # print(f"Attempting to stop logging listener from thread: {current_thread_name}...")
            listener.stop() # This signals the listener thread to stop and waits
            listener = None
            # print("Logging listener stopped successfully.")
        except Exception as e:
            # If stopping fails, print the error.
            # print(f"Error stopping logging listener: {e}")
            # Optionally, log this error if logging is still partially functional
            # logging.getLogger(__name__).error("Error stopping logging listener", exc_info=True)
            pass


# --- Example Usage (Illustrative) ---
# This block demonstrates how to use the setup.
# Typically, you would call setup_logging() once in your application's
# main entry point (e.g., main.py, app factory).
if __name__ == "__main__":
    print("Running logging example...")

    # Configure logging: DEBUG level, log to console and file
    setup_logging(
        log_level=logging.DEBUG,
        log_to_console=True,
        log_to_file=True,
        log_dir='./temp_logs', # Example: use a different directory
        log_filename='example_app.log'
    )

    # Get loggers for different parts of a hypothetical application
    main_logger = get_logger('main_app')
    module_logger = get_logger('main_app.module') # Child logger

    # Log messages from different levels and modules
    main_logger.info("Application starting up...")
    module_logger.debug("Debugging information from the module.")
    main_logger.warning("A potential issue was detected.")
    try:
        # Simulate an error
        result = 1 / 0
    except ZeroDivisionError:
        main_logger.error("An error occurred during calculation!", exc_info=True) # Log exception info

    module_logger.info("Module finished its task.")
    main_logger.info("Application shutting down...")

    # No need to explicitly call stop_listener() here because
    # atexit handles it on normal script completion.
    print("Example finished. Check console output and ./temp_logs/example_app.log")
