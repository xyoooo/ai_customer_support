from enum import StrEnum


class WorkspaceRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    AGENT = "agent"
    VIEWER = "viewer"


class DocumentVersionStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    ACTIVE = "active"
    FAILED = "failed"


class JobType(StrEnum):
    PROCESS_DOCUMENT = "process_document"
    DELETE_OBJECT = "delete_object"


class JobState(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"
    PROCESSING = "processing"
    RETRYING = "retrying"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"
    COMPLETED = "completed"
