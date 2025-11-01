# gunicorn.conf.py
import multiprocessing

# Use sync workers instead of async for better compatibility
worker_class = 'sync'

# Worker configuration
workers = 1

# Bind address
bind = '0.0.0.0:10000'

# Timeouts
timeout = 120
graceful_timeout = 60
keepalive = 5

# Logging
loglevel = 'info'
accesslog = '-'
errorlog = '-'

# Process naming
proc_name = 'tubealgo'

# Server hooks
def on_exit(server):
    server.log.info("TubeAlgo server shutting down...")

def worker_abort(worker):
    worker.log.info("Worker aborting...")