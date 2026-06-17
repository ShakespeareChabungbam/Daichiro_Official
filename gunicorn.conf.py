# Gunicorn config for AWS EC2 (1GB RAM, 30GB storage)
# Usage: gunicorn -c gunicorn.conf.py run:app

import multiprocessing

# Bind
bind = "127.0.0.1:5001"

# Workers — on 1GB RAM, keep it low
# Rule of thumb: 2 × CPU + 1, but capped for memory
workers = 4

# Worker timeout (seconds) — AI analysis may take longer
timeout = 120

# Graceful restart timeout
graceful_timeout = 30

# Max requests per worker before restart (prevents memory leaks)
max_requests = 500
max_requests_jitter = 50

# Logging
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = "info"

# Security: limit request sizes
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# Preload app for faster worker startup
# Set to False so Zero-Downtime 'reload' fetches fresh Python code from disk
preload_app = False
