"""One worker is required for temporary datasets, conversations, and request limits."""
import os
bind = '0.0.0.0:' + os.environ.get('PORT', '10000')
# More workers would create independent caches; threads share the same bounded in-memory datasets.
workers = 1
worker_class = 'gthread'
threads = 4
# The analyst loop has up to six bounded cloud calls. Threads leave health checks responsive.
timeout = 420
graceful_timeout = 30
keepalive = 5
accesslog = None
# Send operational errors to the platform log stream without enabling per-request access logs.
errorlog = '-'
limit_request_line = 4094
limit_request_fields = 40
limit_request_field_size = 4096
