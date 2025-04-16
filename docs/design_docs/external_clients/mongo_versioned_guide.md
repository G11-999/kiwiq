# Guide: Using the AsyncMongoVersionedClient

This guide provides a quick overview of how to use the `AsyncMongoVersionedClient` to manage versioned documents in MongoDB.

**Core Concept:** It wraps the `AsyncMongoDBClient` to add features like multiple named versions, edit history tracking (using JSON patches), branching, and restore capabilities.

## Setup

1.  **Initialize Underlying Client:** First, create an instance of `AsyncMongoDBClient`. Crucially, its `segment_names` must include segments to accommodate the version and sequence numbers that the versioned client will add internally. 
    *   *Example:* If your versioned documents use base paths like `["org", "user", "doc"]`, the underlying client might need `segment_names = ["org", "user", "doc", "version", "sequence"]`.

2.  **Initialize Versioned Client:** Pass the underlying client instance and your *base* segment names.

```python
from mongo_client import AsyncMongoDBClient, AsyncMongoVersionedClient

# 1. Underlying Client Setup (adjust segment names as needed)
base_segment_names = ["org", "namespace", "docname"]
client = AsyncMongoDBClient(
    uri="mongodb://...",
    database="my_db",
    collection="my_collection",
    segment_names=base_segment_names + AsyncMongoVersionedClient.VERSION_SEGMENT_NAMES
)
await client.setup() # Ensure indexes are created

# 2. Versioned Client Setup (provide only the base segment names)

versioned_client = AsyncMongoVersionedClient(
    client=client,
    segment_names=base_segment_names
)
```

## Basic Usage

*   **Paths:** You primarily interact using the `base_path` (e.g., `["my_org", "my_ns", "my_doc"]`). The client handles the internal paths for metadata, versions, and history.
*   **Operations:** All methods are `async`.

### 1. Initializing a Document

This creates the metadata and the first version data structure.

```python
base_path = ["my_org", "my_ns", "config_doc"]
initial_version = "v1.0"
schema = {"type": "object", "properties": {"setting": {"type": "string"}}}

initialized = await versioned_client.initialize_document(
    base_path=base_path,
    initial_version=initial_version,
    schema=schema # Optional
)
# Returns True if successful, False if already exists
```

### 2. Updating a Document

Updates the document in the specified (or active) version and creates a history entry.

```python
# Update the active version (implicitly)
data_update = {"setting": "new_value", "enabled": True}
await versioned_client.update_document(base_path, data_update)

# Update a specific version
data_update_v2 = {"setting": "v2_value"}
await versioned_client.update_document(base_path, data_update_v2, version="v2.0")

# Update with a primitive type
await versioned_client.update_document(base_path, "This is a string value", version="v1.0")

# Mark an update as completing the document (for schema validation)
# NOTE: when document is not complete, json validation is relaxed and doesn't check for unset fields even if they are marked required
await versioned_client.update_document(base_path, final_data, is_complete=True)
```

### 3. Getting a Document

Retrieves the document state for a specific (or active) version.

```python
# Get active version
current_doc = await versioned_client.get_document(base_path)

# Get specific version
doc_v1 = await versioned_client.get_document(base_path, version="v1.0") 
```

## Version Management

### 1. Creating a New Version (Branching)

```python
# Create "v1.1" based on the current active version
await versioned_client.create_version(base_path, "v1.1")

# Create "dev" branch based on "v1.0"
await versioned_client.create_version(base_path, "dev", from_version="v1.0")
```

### 2. Listing Versions

```python
versions = await versioned_client.list_versions(base_path)
# Returns list like: 
# [{"version": "v1.0", "is_active": False, ..., "edit_count": 5}, ...]
```

### 3. Setting the Active Version

```python
await versioned_client.set_active_version(base_path, "v1.1")
```

### 4. Deleting a Version

*Caveat:* Cannot delete the active version.

```python
await versioned_client.delete_version(base_path, "dev") # Deletes "dev" data and history
```

## History and Restore

### 1. Getting History

```python
history = await versioned_client.get_version_history(base_path, version="v1.0", limit=10)
# Returns list of history items (newest first), each containing:
# {"timestamp": "...", "sequence": N, "patch": "[...json patch...]", "is_primitive": False/True}
```

### 2. Previewing a Restore

Reconstructs the document state at a specific sequence number without changing anything.

```python
past_state = await versioned_client.preview_restore(base_path, sequence=5, version="v1.0")
```

### 3. Restoring to a Previous State

Sets the current document state to the state at the specified sequence number and **deletes all history after that point** for the specific version.

```python
restored = await versioned_client.restore(base_path, sequence=5, version="v1.0") 
# Returns True if successful
```

## Schema Management

### 1. Getting the Schema

```python
schema = await versioned_client.get_schema(base_path)
```

### 2. Updating the Schema

```python
new_schema = {"type": "string"}
await versioned_client.update_schema(base_path, new_schema)
```

## Deleting the Document

Removes the metadata, all versions, and all history for the document.

```python
deleted = await versioned_client.delete_document(base_path)
```

## Caveats & Gotchas

*   **Underlying Client Setup:** The `AsyncMongoDBClient` *must* be configured with `segment_names` that anticipate the extra `version` and `sequence` segments added internally by the versioned client. Mismatched configurations will lead to errors or unexpected behavior.
*   **Active Version:** You cannot delete the currently active version. Change the active version first if needed.
*   **Restore is Destructive:** Restoring (`restore`) permanently deletes history items newer than the restored sequence number for that version.
*   **History Pruning:** History is automatically pruned (oldest entries deleted) based on `MAX_HISTORY_LENGTH`. You cannot restore to a sequence number that has been pruned.
*   **`update_document` Merge:** When updating a JSON object with another dictionary, the update dictionary is merged into the existing one (similar to `dict.update()`). It does not replace nested dictionaries entirely unless the new data explicitly provides the full nested structure.
*   **Permissions:** If using `allowed_prefixes`, ensure they grant access to the *internal* paths used by the versioned client (metadata path, version path, history paths).
*   **Primitive vs. JSON:** Transitions between primitive types and JSON objects are treated as full replacements, reflected by the `is_primitive` flag in the history.
