import multiprocessing

bind = "0.0.0.0:5000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "eventlet"
accesslog = "-"
errorlog = "-"
loglevel = "info"
timeout = 120
keepalive = 5
graceful_timeout = 90
forwarded_allow_ips = "*"
proxy_protocol = True
