from global_config.settings import global_settings

# gunicorn.conf.py - Minimal production config
bind = "0.0.0.0:8000"
workers = 1
worker_class = "uvicorn.workers.UvicornWorker"

# Timeouts
timeout = 120
graceful_timeout = 30
keepalive = 5

# Prevent memory leaks with worker recycling
max_requests = 10000
max_requests_jitter = 1000

# Logging
accesslog = "-"
errorlog = "-"
loglevel = global_settings.LOG_LEVEL.lower()

# Use RAM for worker heartbeat (faster hang detection)
worker_tmp_dir = "/dev/shm"

# Preload app for faster restarts
preload_app = True
