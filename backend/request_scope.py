"""Request ownership. Local CLI callers share the explicitly local namespace."""
from contextvars import ContextVar
OWNER = ContextVar("dataset_owner", default="local")
