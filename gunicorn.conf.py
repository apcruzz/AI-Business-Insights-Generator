"""One worker is required: sessions and datasets live in process memory."""
import os
bind = '0.0.0.0:' + os.environ.get('PORT', '10000')
workers = 1
worker_class = 'gthread'
threads = 4
# The analyst loop has up to six bounded cloud calls. Threads leave health checks responsive.
timeout = 420
graceful_timeout = 30
keepalive = 5
accesslog = None
errorlog = '-'
limit_request_line = 4094
limit_request_fields = 40
limit_request_field_size = 4096
