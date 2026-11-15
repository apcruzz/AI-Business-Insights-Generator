"""Request ownership. Local CLI callers share the explicitly local namespace."""
from contextvars import ContextVar
# HTTP middleware replaces this per request; caches read it without sharing owners across threads.
# The default namespace is reserved for the local workflow, which has no hosted user session.
OWNER = ContextVar("dataset_owner", default="local")
