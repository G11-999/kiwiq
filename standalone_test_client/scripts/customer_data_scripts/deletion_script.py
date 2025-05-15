#!/usr/bin/env python3
"""
Customer Data Deletion Script.

This script deletes all customer data documents within a specified namespace.
It provides options to filter by document types (versioned/unversioned), 
sharing status (shared/user-specific), and system entity status.
It offers two deletion modes:
- Object-by-object: Lists and deletes each document individually (default)
- Pattern-based: Uses wildcard patterns to delete documents in bulk

Example usage:
    python deletion_script.py --namespace test_data --include-shared --include-user-specific
    python deletion_script.py --namespace system_config --include-system --include-shared
    python deletion_script.py --namespace user_data --on-behalf-of-user-id 3fa85f64-5717-4562-b3fc-2c963f66afa6
    python deletion_script.py --namespace "test_*" --docname "*" --deletion-mode pattern --include-shared
"""

import argparse
import asyncio
import logging
import sys
import uuid
from typing import Dict, List, Any, Optional, Set, Tuple, Literal

# Import the customer data client
from kiwi_client.customer_data_client import CustomerDataTestClient, AuthenticatedClient
from kiwi_client.schemas.workflow_api_schemas import CustomerDocumentMetadata

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


async def delete_documents_individually(
    namespace: str,
    include_shared: bool = True,
    include_user_specific: bool = True,
    include_system_entities: bool = False,
    on_behalf_of_user_id: Optional[uuid.UUID] = None,
    dry_run: bool = False,
    confirm: bool = True,
) -> Tuple[int, int, List[Dict[str, Any]]]:
    """
    Delete all documents within the specified namespace by listing them first and deleting one by one.
    
    Args:
        namespace: The namespace to delete documents from
        include_shared: Whether to include shared documents
        include_user_specific: Whether to include user-specific documents
        include_system_entities: Whether to include system entities (superuser only)
        on_behalf_of_user_id: Optional user ID to act on behalf of (superuser only)
        dry_run: If True, only list documents but don't delete them
        confirm: If True, ask for confirmation before deletion
        
    Returns:
        Tuple containing (number of documents found, number of documents deleted, list of failed deletions)
    """
    # Track statistics
    docs_found = 0
    docs_deleted = 0
    failed_deletions = []
    
    try:
        # Create authenticated client and data client
        async with AuthenticatedClient() as auth_client:
            data_client = CustomerDataTestClient(auth_client)
            
            # List all documents in the namespace
            logger.info(f"Listing documents in namespace: {namespace}, include_shared: {include_shared}, include_user_specific: {include_user_specific}, include_system_entities: {include_system_entities}, on_behalf_of_user_id: {on_behalf_of_user_id}")
            documents = await data_client.list_documents(
                namespace=namespace,
                include_shared=include_shared,
                include_user_specific=include_user_specific,
                include_system_entities=include_system_entities,
                on_behalf_of_user_id=on_behalf_of_user_id,
                limit=1000  # Set a high limit to get all documents
            )
            
            if not documents:
                logger.info(f"No documents found in namespace '{namespace}' with the specified filters.")
                return 0, 0, []
            
            docs_found = len(documents)
            logger.info(f"Found {docs_found} documents in namespace '{namespace}'")
            
            # Group documents by type (versioned/unversioned) and sharing status
            # for prettier output and more efficient confirmation
            doc_groups: Dict[str, List[CustomerDocumentMetadata]] = {
                "Versioned Shared": [],
                "Versioned User-specific": [],
                "Unversioned Shared": [],
                "Unversioned User-specific": [],
            }
            
            for doc in documents:
                group_key = f"{'Versioned' if doc.is_versioned else 'Unversioned'} {'Shared' if doc.is_shared else 'User-specific'}"
                doc_groups[group_key].append(doc)
            
            # Print document groups for confirmation
            for group_name, docs in doc_groups.items():
                if docs:
                    logger.info(f"{group_name} documents ({len(docs)}):")
                    for doc in docs:
                        if include_system_entities:
                            system_status = f", System: {doc.is_system_entity}"
                        else:
                            system_status = ""
                        logger.info(f"  - {doc.namespace}/{doc.docname}{system_status}")
            
            # Ask for confirmation if not dry run and confirmation is required
            if not dry_run and confirm:
                confirmation = input(f"\nDelete {docs_found} documents from namespace '{namespace}'? (yes/no): ")
                if confirmation.lower() not in ["yes", "y"]:
                    logger.info("Deletion cancelled.")
                    return docs_found, 0, []
            
            if dry_run:
                logger.info("Dry run mode - no documents will be deleted.")
                return docs_found, 0, []
            
            # Delete documents
            logger.info(f"Deleting {docs_found} documents...")
            for doc in documents:
                try:
                    # Delete versioned or unversioned document based on type
                    if doc.is_versioned:
                        deleted = await data_client.delete_versioned_document(
                            namespace=doc.namespace,
                            docname=doc.docname,
                            is_shared=doc.is_shared,
                            is_system_entity=doc.is_system_entity,
                            on_behalf_of_user_id=on_behalf_of_user_id
                        )
                    else:
                        deleted = await data_client.delete_unversioned_document(
                            namespace=doc.namespace,
                            docname=doc.docname,
                            is_shared=doc.is_shared,
                            is_system_entity=doc.is_system_entity,
                            on_behalf_of_user_id=on_behalf_of_user_id
                        )
                    
                    if deleted:
                        docs_deleted += 1
                        logger.info(f"Deleted: {doc.namespace}/{doc.docname}")
                    else:
                        # Add to failed deletions if the result was False but no exception was thrown
                        failed_deletions.append({
                            "namespace": doc.namespace,
                            "docname": doc.docname,
                            "is_shared": doc.is_shared,
                            "is_versioned": doc.is_versioned,
                            "is_system_entity": doc.is_system_entity,
                            "error": "Deletion failed without error"
                        })
                        logger.error(f"Failed to delete: {doc.namespace}/{doc.docname}")
                        
                except Exception as e:
                    # Add to failed deletions with error information
                    failed_deletions.append({
                        "namespace": doc.namespace,
                        "docname": doc.docname,
                        "is_shared": doc.is_shared,
                        "is_versioned": doc.is_versioned,
                        "is_system_entity": doc.is_system_entity,
                        "error": str(e)
                    })
                    logger.error(f"Error deleting {doc.namespace}/{doc.docname}: {e}")
                    
    except Exception as e:
        logger.error(f"Error during document deletion process: {e}")
        
    return docs_found, docs_deleted, failed_deletions


async def delete_documents_by_pattern(
    namespace: str,
    docname: str = "*",
    include_shared: bool = True,
    include_user_specific: bool = True,
    include_system_entities: bool = False,
    on_behalf_of_user_id: Optional[uuid.UUID] = None,
    dry_run: bool = True,
    confirm: bool = True,
) -> Tuple[int, int, List[Dict[str, Any]]]:
    """
    Delete documents by pattern using the bulk deletion API.
    
    Args:
        namespace: The namespace pattern to match (supports wildcards)
        docname: The document name pattern to match (supports wildcards)
        include_shared: Whether to include shared documents
        include_user_specific: Whether to include user-specific documents
        include_system_entities: Whether to include system entities (superuser only)
        on_behalf_of_user_id: Optional user ID to act on behalf of (superuser only)
        dry_run: If True, only simulate the deletion
        confirm: If True, ask for confirmation before deletion
        
    Returns:
        Tuple containing (number of documents found, number of documents deleted, empty list for compatibility)
    """
    # Track statistics for compatibility with the individual deletion function
    docs_found = 0
    docs_deleted = 0
    failed_deletions = []
    
    try:
        # Create authenticated client and data client
        async with AuthenticatedClient() as auth_client:
            data_client = CustomerDataTestClient(auth_client)
            
            results = []
            
            # If both shared and user-specific are included, we need to make two separate calls
            operations_to_perform = []
            
            if include_shared:
                operations_to_perform.append({
                    "is_shared": True,
                    "description": "shared"
                })
            
            if include_user_specific:
                operations_to_perform.append({
                    "is_shared": False,
                    "description": "user-specific"
                })
            
            # First do a dry run to get counts for all operations
            logger.info(f"Counting documents that match pattern - namespace: {namespace}, docname: {docname}")
            
            for operation in operations_to_perform:
                is_shared = operation["is_shared"]
                description = operation["description"]
                
                # Always do a dry run first to get the count
                dry_run_result = await data_client.delete_objects_by_pattern(
                    namespace=namespace,
                    docname=docname,
                    is_shared=is_shared,
                    is_system_entity=include_system_entities,
                    on_behalf_of_user_id=on_behalf_of_user_id,
                    dry_run=True
                )
                
                if dry_run_result:
                    count = dry_run_result.deleted_count
                    docs_found += count
                    logger.info(f"Found {count} {description} documents matching namespace: {namespace}, docname: {docname}")
                    operation["count"] = count
                    results.append(dry_run_result)
                else:
                    logger.error(f"Error counting {description} documents")
                    operation["count"] = 0
            
            if docs_found == 0:
                logger.info(f"No documents found matching namespace: '{namespace}', docname: '{docname}' with the specified filters.")
                return 0, 0, []
            
            # Ask for confirmation if confirmation is required
            if confirm:
                confirmation = input(f"\nDelete {docs_found} documents matching namespace: '{namespace}', docname: '{docname}'? (yes/no): ")
                if confirmation.lower() not in ["yes", "y"]:
                    logger.info("Deletion cancelled.")
                    return docs_found, 0, []
            
            if dry_run:
                logger.info("Dry run mode - no documents will be deleted.")
                return docs_found, 0, []
            
            # Now perform the actual deletions
            logger.info(f"Deleting {docs_found} documents...")
            
            for operation in operations_to_perform:
                is_shared = operation["is_shared"]
                description = operation["description"]
                count = operation["count"]
                
                if count > 0:
                    deletion_result = await data_client.delete_objects_by_pattern(
                        namespace=namespace,
                        docname=docname,
                        is_shared=is_shared,
                        is_system_entity=include_system_entities,
                        on_behalf_of_user_id=on_behalf_of_user_id,
                        dry_run=False
                    )
                    
                    if deletion_result:
                        deleted = deletion_result.deleted_count
                        docs_deleted += deleted
                        logger.info(f"Deleted {deleted} {description} documents.")
                    else:
                        logger.error(f"Error deleting {description} documents")
                        failed_deletions.append({
                            "namespace": namespace,
                            "docname": docname,
                            "is_shared": is_shared,
                            "is_system_entity": include_system_entities,
                            "error": "Bulk deletion operation failed"
                        })
    
    except Exception as e:
        logger.error(f"Error during pattern-based document deletion: {e}")
        
    return docs_found, docs_deleted, failed_deletions


async def delete_documents(
    namespace: str,
    docname: str = "*",
    include_shared: bool = True,
    include_user_specific: bool = True,
    include_system_entities: bool = False,
    on_behalf_of_user_id: Optional[uuid.UUID] = None,
    dry_run: bool = False,
    confirm: bool = True,
    deletion_mode: Literal["individual", "pattern"] = "individual",
) -> Tuple[int, int, List[Dict[str, Any]]]:
    """
    Delete documents within the specified namespace using the selected deletion mode.
    
    Args:
        namespace: The namespace to delete documents from
        docname: The document name pattern (used only in pattern mode)
        include_shared: Whether to include shared documents
        include_user_specific: Whether to include user-specific documents
        include_system_entities: Whether to include system entities (superuser only)
        on_behalf_of_user_id: Optional user ID to act on behalf of (superuser only)
        dry_run: If True, only list documents but don't delete them
        confirm: If True, ask for confirmation before deletion
        deletion_mode: The deletion mode to use ("individual" or "pattern")
        
    Returns:
        Tuple containing (number of documents found, number of documents deleted, list of failed deletions)
    """
    if deletion_mode == "individual":
        return await delete_documents_individually(
            namespace=namespace,
            include_shared=include_shared,
            include_user_specific=include_user_specific,
            include_system_entities=include_system_entities,
            on_behalf_of_user_id=on_behalf_of_user_id,
            dry_run=dry_run,
            confirm=confirm
        )
    elif deletion_mode == "pattern":
        return await delete_documents_by_pattern(
            namespace=namespace,
            docname=docname,
            include_shared=include_shared,
            include_user_specific=include_user_specific,
            include_system_entities=include_system_entities,
            on_behalf_of_user_id=on_behalf_of_user_id,
            dry_run=dry_run,
            confirm=confirm
        )
    else:
        logger.error(f"Invalid deletion mode: {deletion_mode}")
        return 0, 0, []


async def main():
    """Main function to parse arguments and execute the deletion process."""
    # Default arguments to use if not provided via command line
    
    # HOW TO RUN SCRIPT:
    # poetry run python scripts/customer_data/deletion_script.py --namespace xyz --include-shared true
    # OR
    # CHANGE BELOW DEFAULT ARGS AND RUN WITHOUT ARGS
    default_args = {
        "namespace": "system_strategy_docs_namespace",  # No default namespace - must be provided
        "docname": "*",
        "include_shared": True,
        "include_user_specific": True,
        "include_system": True,
        "on_behalf_of_user_id": None,  # b853073c-200e-40ca-abaf-cbff9265d0d8   700ddb39-23b2-4426-be12-9db263a9c7a8
        "dry_run": False,
        "no_confirm": True,
        "deletion_mode": "pattern"
    }
    
    parser = argparse.ArgumentParser(description="Delete customer data documents within a namespace.")
    
    # Required namespace argument (can be overridden by explicitly setting a default)
    parser.add_argument(
        "--namespace", 
        required=default_args["namespace"] is None,  # Only required if no default
        default=default_args["namespace"],
        help="Namespace to delete documents from (supports wildcards in pattern mode)"
    )
    
    parser.add_argument(
        "--docname", 
        default=default_args["docname"],
        help="Document name pattern (used only in pattern mode, defaults to '*')"
    )
    
    # Document type filters with defaults
    parser.add_argument(
        "--include-shared", 
        action="store_true",
        default=default_args["include_shared"],
        help=f"Include shared documents (default: {default_args['include_shared']})"
    )
    parser.add_argument(
        "--include-user-specific", 
        action="store_true",
        default=default_args["include_user_specific"],
        help=f"Include user-specific documents (default: {default_args['include_user_specific']})"
    )
    parser.add_argument(
        "--include-system", 
        action="store_true",
        default=default_args["include_system"],
        help=f"Include system entities (superuser only) (default: {default_args['include_system']})"
    )
    
    # Optional parameters with defaults
    parser.add_argument(
        "--on-behalf-of-user-id", 
        type=str,
        default=default_args["on_behalf_of_user_id"],
        help="User ID to act on behalf of (superuser only, UUID format)"
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        default=default_args["dry_run"],
        help=f"List documents but don't delete them (default: {default_args['dry_run']})"
    )
    parser.add_argument(
        "--no-confirm", 
        action="store_true",
        default=default_args["no_confirm"],
        help=f"Skip confirmation prompt and proceed with deletion (default: {default_args['no_confirm']})"
    )
    
    # Deletion mode
    parser.add_argument(
        "--deletion-mode",
        choices=["individual", "pattern"],
        default=default_args["deletion_mode"],
        help=f"Deletion mode: 'individual' deletes documents one by one, 'pattern' uses wildcards for bulk deletion (default: {default_args['deletion_mode']})"
    )
    
    # Add argument to use all defaults
    parser.add_argument(
        "--use-defaults",
        action="store_true",
        help="Use default values for all arguments (except namespace if not specified)"
    )
    
    args = parser.parse_args()
    
    # If use-defaults flag is set and namespace is provided, use all defaults
    if args.use_defaults:
        if args.namespace or default_args["namespace"]:
            namespace = args.namespace or default_args["namespace"]
            docname = default_args["docname"]
            include_shared = default_args["include_shared"]
            include_user_specific = default_args["include_user_specific"]
            include_system = default_args["include_system"] 
            on_behalf_of_user_id_str = default_args["on_behalf_of_user_id"]
            dry_run = default_args["dry_run"]
            no_confirm = default_args["no_confirm"]
            deletion_mode = default_args["deletion_mode"]
            
            logger.info("Using default values for all arguments (except namespace)")
        else:
            parser.error("Namespace must be provided even when using --use-defaults")
    else:
        # Use parsed arguments
        namespace = args.namespace
        docname = args.docname
        include_shared = args.include_shared
        include_user_specific = args.include_user_specific
        include_system = args.include_system
        on_behalf_of_user_id_str = args.on_behalf_of_user_id
        dry_run = args.dry_run
        no_confirm = args.no_confirm
        deletion_mode = args.deletion_mode
    
    # Validate that at least one document type is included
    if not include_shared and not include_user_specific:
        parser.error("At least one of --include-shared or --include-user-specific must be specified.")
    
    # Convert on_behalf_of_user_id string to UUID if provided
    on_behalf_uuid = None
    if on_behalf_of_user_id_str:
        try:
            on_behalf_uuid = uuid.UUID(on_behalf_of_user_id_str)
        except ValueError:
            parser.error(f"Invalid UUID format for --on-behalf-of-user-id: {on_behalf_of_user_id_str}")
    
    # Execute deletion
    docs_found, docs_deleted, failed = await delete_documents(
        namespace=namespace,
        docname=docname,
        include_shared=include_shared,
        include_user_specific=include_user_specific,
        include_system_entities=include_system,
        on_behalf_of_user_id=on_behalf_uuid,
        dry_run=dry_run,
        confirm=not no_confirm,
        deletion_mode=deletion_mode
    )
    
    # Report results
    if dry_run:
        logger.info(f"Dry run summary: Found {docs_found} documents matching namespace '{namespace}'{', docname ' + docname if deletion_mode == 'pattern' else ''}")
    else:
        logger.info(f"Deletion summary: Deleted {docs_deleted} of {docs_found} documents from namespace '{namespace}'{', docname ' + docname if deletion_mode == 'pattern' else ''}")
        
        if failed:
            logger.error(f"Failed to delete {len(failed)} documents:")
            for doc in failed:
                logger.error(f"  - {doc['namespace']}/{doc['docname']}: {doc['error']}")
    
    return 0 if not failed or dry_run else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
