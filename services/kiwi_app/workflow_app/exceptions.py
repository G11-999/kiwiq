
"""Custom exceptions for the Workflow Service."""

from fastapi import HTTPException, status

class WorkflowNotFoundException(HTTPException):
    """Raised when a requested workflow is not found or not accessible."""
    def __init__(self, detail: str = "Workflow not found or not accessible."):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class WorkflowRunNotFoundException(HTTPException):
    """Raised when a requested workflow run is not found or not accessible."""
    def __init__(self, detail: str = "Workflow run not found or not accessible."):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class TemplateNotFoundException(HTTPException):
    """Raised when a requested template (Node, Prompt, Schema) is not found."""
    def __init__(self, detail: str = "Template not found."):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class WorkflowExecutionError(HTTPException):
    """Raised when there's an error triggering or during workflow execution."""
    def __init__(self, detail: str = "Workflow execution failed."):
        # Use 500 for internal errors during execution triggering/processing
        super().__init__(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)

class InvalidWorkflowConfigException(HTTPException):
    """Raised when a workflow's graph configuration is invalid."""
    def __init__(self, detail: str = "Invalid workflow configuration."):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

# Add more specific exceptions as needed
