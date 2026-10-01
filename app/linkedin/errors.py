"""Tool-layer errors shared across the LinkedIn local backend."""


class ToolError(RuntimeError):
    """Upstream/backend call failed or returned an unusable payload."""


class ToolNotFoundError(ToolError):
    """The requested entity does not exist."""
