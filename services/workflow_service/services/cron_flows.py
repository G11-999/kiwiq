# PYTHONPATH=.:./services poetry run python /path/to/project/services/workflow_service/services/worker.py
import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Tuple, AsyncGenerator, Optional, List, Union, cast
from pydantic import BaseModel

# Prefect imports
from prefect import flow, get_run_logger, serve, task
from prefect.deployments import run_deployment
from prefect import resume_flow_run, pause_flow_run, suspend_flow_run
from prefect.client.schemas import FlowRun
from prefect.server.schemas.schedules import CronSchedule
# from prefect.filesystems import S3, GitHub, LocalFileSystem
from prefect.cache_policies import NO_CACHE
from prefect.context import get_run_context

from db.session import get_async_pool, get_async_db_as_manager # Assuming this provides psycopg pool
from global_config.settings import global_settings
from global_config.logger import get_prefect_or_regular_python_logger
from kiwi_app.settings import settings
from kiwi_app.billing.models import CreditType
from kiwi_app.billing import schemas as billing_schemas

# Email system imports
from kiwi_app.email.email_dispatch import email_dispatch, EmailContent, EmailRecipient
from kiwi_app.email.email_templates.renderer import (
    EmailRenderer, 
    DraftProgressReminderEmailData
)

# Local workflow service imports
from workflow_service.services.external_context_manager import (
    ExternalContextManager,
    get_external_context_manager_with_clients
)



@flow(
    name="billing-expire-organization-credits",
    description="Expires organization credits that have reached their expiration date",
    log_prints=global_settings.DEBUG,
    retries=2,
    retry_delay_seconds=60,
    # validate_parameters=False,
)
async def billing_expire_organization_credits_flow(
    org_id: Optional[uuid.UUID] = None,
    cutoff_datetime: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Prefect flow to expire organization credits that have reached their expiration date.
    
    This flow is designed to run as a scheduled cron job to automatically clean up
    expired credits across all organizations or for a specific organization.
    
    Args:
        org_id: Optional organization ID to expire credits for. If None, expires 
               credits for all organizations.
        cutoff_datetime: Optional cutoff datetime. If None, uses current time.
               Credits with expiration dates before this time will be expired.
    
    Returns:
        Dict[str, Any]: Results of the credit expiration process including counts
                       of expired credits and any errors encountered.
    """
    logger = get_prefect_or_regular_python_logger(name="expire-organization-credits-flow")
    
    # Use current time as cutoff if not provided
    if cutoff_datetime is None:
        cutoff_datetime = datetime.now(tz=timezone.utc)
    
    logger.info(f"Starting credit expiration process for org_id: {org_id}, cutoff: {cutoff_datetime}")
    
    # Initialize external context manager to access billing service
    external_context = await get_external_context_manager_with_clients()
    logger.info("External context manager initialized for credit expiration")
    
    try:
        # Execute credit expiration using billing service
        async with get_async_db_as_manager() as db:
            expiration_result = await external_context.billing_service.expire_organization_credits(
                db=db,
                org_id=org_id,
                cutoff_datetime=cutoff_datetime
            )
        
        # Add some metrics to the result for monitoring
        result = {
            "status": "success",
            "executed_at": datetime.now(tz=timezone.utc).isoformat(),
            "cutoff_datetime": cutoff_datetime.isoformat(),
            "target_org_id": str(org_id) if org_id else "all_organizations",
            **expiration_result
        }

        logger.info(f"Credit expiration completed successfully. Results: {json.dumps(result, indent=2, default=str)}")
        
        return result
        
    except Exception as e:
        logger.error(f"Credit expiration flow failed: {e}", exc_info=True)
        
        # Return error information for monitoring
        error_result = {
            "status": "failed",
            "executed_at": datetime.now(tz=timezone.utc).isoformat(),
            "cutoff_datetime": cutoff_datetime.isoformat() if cutoff_datetime else None,
            "target_org_id": str(org_id) if org_id else "all_organizations",
            "error_message": str(e),
            "expired_credits_count": 0,
            "affected_organizations": 0
        }
        
        # Re-raise the exception to ensure Prefect marks the flow as failed
        raise e
        
    finally:
        # Clean up resources
        try:
            await external_context.close()
            logger.info("External context manager closed successfully")
        except Exception as close_err:
            logger.error(f"Error closing external context: {close_err}", exc_info=True)



@flow(
    name="search-scheduled-briefs-and-send-reminders",
    description="Searches for all post briefs scheduled for today and sends draft progress reminder emails",
    log_prints=global_settings.DEBUG,
    retries=2,
    retry_delay_seconds=60,
)
async def search_scheduled_briefs_and_send_reminders_flow(
    target_date: Optional[datetime] = None,
    send_reminder_emails: bool = True,
    trigger_workflows: bool = False
) -> Dict[str, Any]:
    """
    Prefect flow to search for post briefs scheduled for a specific date and send
    draft progress reminder emails to users.
    
    This flow is designed to run as a scheduled cron job to find all briefs
    that are scheduled for content creation on the target date and notify users
    about pending drafts that need their attention.
    
    Args:
        target_date: Optional target date to search for. If None, uses today's date.
        send_reminder_emails: If True, sends draft progress reminder emails for found briefs.
        trigger_workflows: If True, triggers content creation workflows for found briefs.
                          (Not implemented in this version)
    
    Returns:
        Dict[str, Any]: Results of the brief search and email sending including counts and details.
    """
    logger = get_prefect_or_regular_python_logger(name="search-scheduled-briefs-and-send-reminders-flow")
    
    # Use current time if not provided
    if target_date is None:
        utc_now = datetime.now(tz=timezone.utc)
        target_date = utc_now.replace(hour=12, minute=0, second=0, microsecond=0) # 12 PM UTC
    
    date_format = "%Y-%m-%dT%H:%M:%SZ"
    target_date_str = target_date.strftime(date_format)
    
    logger.info(f"Starting scheduled brief search and reminder process for date: {target_date_str}")
    
    try:
        # Task 1: Search for scheduled briefs
        briefs = await search_scheduled_briefs_for_today(start_date=target_date)
        
        # Prepare summary statistics
        total_briefs = len(briefs)
        org_ids = set(b["org_id"] for b in briefs if b["org_id"])
        user_ids = set(b["user_id"] for b in briefs)
        
        # Group by status if available
        status_counts = {}
        for brief in briefs:
            status = brief.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        logger.info(
            f"Brief search completed successfully. "
            f"Found {total_briefs} briefs across {len(org_ids)} organizations"
        )
        
        # Task 2: Send reminder emails if enabled and briefs found
        email_results = None
        if send_reminder_emails and briefs:
            logger.info(f"Sending draft progress reminder emails for {total_briefs} briefs")
            email_results = await send_draft_progress_reminder_emails(briefs)
        elif send_reminder_emails and not briefs:
            logger.info("No briefs found, skipping reminder email sending")
            email_results = {
                "total_briefs": 0,
                "emails_sent": 0,
                "emails_failed": 0,
                "errors": []
            }
        else:
            logger.info("Reminder email sending disabled")
            email_results = {
                "total_briefs": total_briefs,
                "emails_sent": 0,
                "emails_failed": 0,
                "errors": [],
                "disabled": True
            }
        
        # Create result summary
        result = {
            "status": "success",
            "executed_at": datetime.now(tz=timezone.utc).isoformat(),
            "target_date": target_date_str,
            "total_briefs_found": total_briefs,
            "unique_organizations": len(org_ids),
            "unique_users": len(user_ids),
            "briefs_by_status": status_counts,
            "email_results": email_results,
            "briefs": briefs  # Full brief data
        }
        
        # TODO: If trigger_workflows is True, trigger content creation workflows
        # for each found brief. This would involve calling trigger_workflow_run
        # for each brief with appropriate parameters.
        if trigger_workflows:
            logger.info("Workflow triggering not yet implemented")
            result["workflows_triggered"] = 0
        
        return result
        
    except Exception as e:
        logger.error(f"Scheduled brief search and reminder flow failed: {e}", exc_info=True)
        
        # Return error information for monitoring
        error_result = {
            "status": "failed",
            "executed_at": datetime.now(tz=timezone.utc).isoformat(),
            "target_date": target_date_str if target_date else None,
            "error_message": str(e),
            "total_briefs_found": 0,
            "unique_organizations": 0,
            "unique_users": 0,
            "email_results": {
                "total_briefs": 0,
                "emails_sent": 0,
                "emails_failed": 0,
                "errors": [str(e)]
            }
        }
        
        # Re-raise the exception to ensure Prefect marks the flow as failed
        raise e


@task
async def search_scheduled_briefs_for_today(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Search for all post briefs scheduled for a specific date.
    
    This function uses the system search capability to find all briefs 
    across all organizations and users that have a scheduled_date matching
    the target date.
    
    Args:
        start_date: The start date to search for. If None, uses today's date.
                    Should be timezone-aware datetime object.
        end_date: The end date to search for. If None, uses start_date + 1 day.
    
    Returns:
        List of dictionaries containing brief data and metadata
    
    NOTE: Search API query for debugging:
    {
        "namespace_filter": "content_briefs_*",
        "value_filter": {
            "scheduled_date": {
                    "$gt":"2025-06-14",
                    "$lte": "2025-06-17"
                }
        },
        "skip": 0,
        "limit": 100,
        "sort_by": "created_at",
        "sort_order": "desc"
    }
    """
    logger = get_prefect_or_regular_python_logger(name="search-scheduled-briefs")
    
    # Use today's date if not provided
    if start_date is None:
        start_date = datetime.now(tz=timezone.utc)
    if end_date is None:
        end_date = start_date + timedelta(days=1)
    
    # Format date as YYYY-MM-DD for the value filter
    date_format = "%Y-%m-%dT%H:%M:%SZ"
    start_date_str = start_date.strftime(date_format)
    end_date_str = end_date.strftime(date_format)
    logger.info(f"Searching for briefs scheduled for date: {start_date_str} to {end_date_str}")

    # Create value filter for scheduled_date
    value_filter = {
        "scheduled_date": {
            "$gt": start_date_str,
            "$lte": end_date_str
        }
    }
    
    # Import the document configs from app_artifacts
    from kiwi_app.workflow_app.app_artifacts import DEFAULT_USER_DOCUMENTS_CONFIG
    
    # Get the brief document configuration
    brief_config = DEFAULT_USER_DOCUMENTS_CONFIG.get_document_config("brief")
    if not brief_config:
        logger.error("Brief document configuration not found in app_artifacts")
        raise ValueError("Brief document configuration not found")
    
    # Extract the namespace template pattern
    # The namespace template is "content_briefs_{entity_username}"
    # For system search, we use wildcards to match all users
    namespace_pattern = "content_briefs_*"
    
    # The docname template is "brief_{_uuid_}"
    # Use wildcard to match all brief documents
    docname_pattern = "brief_*"
    
    logger.info(f"Using namespace pattern: {namespace_pattern}, docname pattern: {docname_pattern}")
    
    # Initialize external context manager to access customer data service
    external_context = await get_external_context_manager_with_clients()
    logger.info("External context manager initialized for brief search")
    
    try:
        
        # Use system search to find all briefs with the target scheduled date
        search_results = await external_context.customer_data_service.system_search_documents(
            namespace_pattern=namespace_pattern,
            docname_pattern=docname_pattern,
            value_filter=value_filter,
            limit=9000,  # Adjust based on expected volume
            sort_by=None,  # Can add sorting if needed
            sort_order=None
        )
        
        logger.info(f"Found {len(search_results)} briefs scheduled for {start_date_str} to {end_date_str}")
        
        # Process results to extract relevant information
        unique_brief_paths = set()
        processed_results = []
        for result in search_results:
            metadata = result.metadata
            data = result.data
            
            # Skip versioning metadata entries
            if metadata.is_versioning_metadata:
                continue
            
            brief_id = metadata.versionless_path
            if (brief_id and brief_id in unique_brief_paths) or (metadata.is_active_version == False):
                continue
            unique_brief_paths.add(brief_id)
            
            # Extract organization and user information
            org_id = metadata.org_id
            user_id = metadata.user_id_or_shared_placeholder
            
            # # Skip shared documents (briefs should be user-specific)
            # if user_id == external_context.customer_data_service.SHARED_DOC_PLACEHOLDER:
            #     logger.warning(f"Skipping shared brief: {metadata.docname}")
            #     continue
            
            # Extract brief details
            brief_info = {
                "org_id": str(org_id) if org_id else None,
                "user_id": user_id,
                "namespace": metadata.namespace,
                "docname": metadata.docname,
                "version": metadata.version,
                "is_versioned": metadata.is_versioned,
                "scheduled_date": data.get("scheduled_date"),
                "brief_data": data,
                # Extract key fields from brief data if available
                "title": data.get("title", ""),
                "status": data.get("status", ""),
                "post_type": data.get("post_type", ""),
                "content_focus": data.get("content_focus", ""),
            }
            
            processed_results.append(brief_info)
        
        # Log summary of results
        if processed_results:
            org_count = len(set(b["org_id"] for b in processed_results if b["org_id"]))
            user_count = len(set(b["user_id"] for b in processed_results))
            logger.info(
                f"Found {len(processed_results)} briefs across "
                f"{org_count} organizations and {user_count} users"
            )
        else:
            logger.info("No briefs found for the specified date")
        
        return processed_results
        
    except Exception as e:
        logger.error(f"Error searching for scheduled briefs: {e}", exc_info=True)
        raise
        
    finally:
        # Clean up resources
        try:
            await external_context.close()
            logger.info("External context manager closed successfully")
        except Exception as close_err:
            logger.error(f"Error closing external context: {close_err}", exc_info=True)


@task
async def send_draft_progress_reminder_emails(
    briefs: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Send draft progress reminder emails for scheduled briefs.
    
    This task processes a list of scheduled briefs and sends draft progress reminder
    emails to users for briefs that need attention. Similar to the email sending
    pattern used in email_verify.py.
    
    Args:
        briefs: List of brief dictionaries containing brief data and metadata
        
    Returns:
        Dict[str, Any]: Results of the email sending process including counts
                       of emails sent and any errors encountered.
    """
    logger = get_prefect_or_regular_python_logger(name="send-draft-progress-reminders")
    
    if not briefs:
        logger.info("No briefs provided for reminder emails")
        return {
            "total_briefs": 0,
            "emails_sent": 0,
            "emails_failed": 0,
            "errors": []
        }
    
    logger.info(f"Processing {len(briefs)} briefs for draft progress reminders")
    
    # Initialize email renderer and external context
    email_renderer = EmailRenderer()
    external_context = await get_external_context_manager_with_clients()
    
    emails_sent = 0
    emails_failed = 0
    errors = []
    
    try:
        # First, prepare all email data and validate users
        email_tasks = []
        email_briefs_data = []  # Keep track of brief data for each email task
        
        # Process each brief and prepare email data
        for brief in briefs:
            try:
                # Extract brief and user information
                org_id_str = brief.get("org_id")
                user_id = brief.get("user_id")
                brief_data = brief.get("brief_data", {})
                
                if not org_id_str or not user_id:
                    logger.warning(f"Skipping brief with missing org_id or user_id: {brief.get('docname')}")
                    emails_failed += 1
                    errors.append(f"Missing org_id or user_id for brief {brief.get('docname', 'unknown')}")
                    continue
                
                org_id = uuid.UUID(org_id_str)
                
                # Get user information from database
                async with get_async_db_as_manager() as db:
                    user = await external_context.daos.user.get(db, id=user_id)
                    if not user:
                        logger.warning(f"User not found for ID: {user_id}")
                        emails_failed += 1
                        errors.append(f"User not found for ID: {user_id}")
                        continue
                    
                    if not user.email:
                        logger.warning(f"User {user_id} has no email address")
                        emails_failed += 1
                        errors.append(f"User {user_id} has no email address")
                        continue
                
                # Extract brief details for email
                brief_title = brief_data.get("title", brief_data.get("core_perspective", "Untitled Brief"))
                scheduled_date = brief_data.get("scheduled_date", "")
                
                # Format publication time for better readability
                publication_time = "Today"
                if scheduled_date:
                    try:
                        # Parse the scheduled date and format it nicely
                        if isinstance(scheduled_date, str):
                            parsed_date = datetime.fromisoformat(scheduled_date.replace('Z', '+00:00'))
                        else:
                            parsed_date = scheduled_date
                        publication_time = parsed_date.strftime("%A at %I:%M %p")
                    except Exception as date_err:
                        logger.warning(f"Could not parse scheduled_date {scheduled_date}: {date_err}")
                        publication_time = f"Scheduled for {scheduled_date}"
                    publication_time += " UTC"
                
                # Construct URLs (these should match your app's URL structure)
                # complete_post_url = f"https://app.kiwiq.com/briefs/{brief.get('docname', '')}/edit"
                # calendar_url = "https://app.kiwiq.com/calendar"
                
                # Create email data using the template system
                email_data = DraftProgressReminderEmailData(
                    user_name=user.full_name or user.email.split('@')[0],  # Fallback to email prefix if no name
                    brief_title=brief_title,
                    publication_time=publication_time,
                    complete_post_url=settings.URL_CONTENT_CALENDAR,
                    calendar_url=settings.URL_CONTENT_CALENDAR,
                )
                
                # Render both HTML and text versions
                html_content = email_renderer.render_draft_progress_reminder_email(email_data)
                text_content = email_renderer.html_to_text(html_content)
                
                # Create email content object
                email_content = EmailContent(
                    subject=f"[REMINDER] Your LinkedIn post is scheduled for {publication_time}: \"{brief_title}\"",
                    html_body=html_content,
                    text_body=text_content,
                    from_name="KiwiQ Team"
                )
                
                # Create recipient object
                recipient = EmailRecipient(
                    email=user.email,
                    name=user.full_name
                )
                
                # Create email sending coroutine for concurrent execution
                email_task = email_dispatch.send_email(
                    recipient=recipient,
                    content=email_content
                )
                
                email_tasks.append(email_task)
                email_briefs_data.append({
                    "brief": brief,
                    "brief_title": brief_title,
                    "user_email": user.email,
                    "user_name": user.full_name or user.email.split('@')[0]
                })
                
            except Exception as brief_err:
                emails_failed += 1
                error_msg = f"Error preparing email for brief {brief.get('docname', 'unknown')}: {brief_err}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)
        
        # Send all emails concurrently using asyncio.gather
        if email_tasks:
            logger.info(f"Sending {len(email_tasks)} draft reminder emails concurrently...")
            
            # Use gather with return_exceptions=True to handle individual failures gracefully
            email_results = await asyncio.gather(*email_tasks, return_exceptions=True)
            
            # Process results from concurrent email sending
            for i, result in enumerate(email_results):
                brief_data = email_briefs_data[i]
                
                if isinstance(result, Exception):
                    # Email sending failed with an exception
                    emails_failed += 1
                    error_msg = f"Exception sending email to {brief_data['user_email']}: {result}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)
                elif result is True:
                    # Email sent successfully
                    emails_sent += 1
                    logger.info(f"Draft reminder email sent to {brief_data['user_email']} for brief: {brief_data['brief_title']}")
                else:
                    # Email sending returned False (failed but no exception)
                    emails_failed += 1
                    error_msg = f"Failed to send draft reminder email to {brief_data['user_email']} (returned False)"
                    logger.warning(error_msg)
                    errors.append(error_msg)
        else:
            logger.info("No valid email tasks prepared for sending")
        
        result = {
            "total_briefs": len(briefs),
            "emails_sent": emails_sent,
            "emails_failed": emails_failed,
            "errors": errors
        }
        
        logger.info(
            f"Draft progress reminder email task completed. "
            f"Sent: {emails_sent}, Failed: {emails_failed}, Total briefs: {len(briefs)}"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Critical error in send_draft_progress_reminder_emails task: {e}", exc_info=True)
        raise
        
    finally:
        # Clean up resources
        try:
            await external_context.close()
            logger.info("External context manager closed successfully")
        except Exception as close_err:
            logger.error(f"Error closing external context: {close_err}", exc_info=True)


if __name__ == "__main__":
    async def run_search_for_day(day: int) -> tuple[int, list]:
        """
        Search for scheduled briefs for a specific day offset from today.
        
        Args:
            day: Number of days from today to search for briefs
            
        Returns:
            Tuple of (day_offset, search_results)
        """
        target_date = datetime(2025, 6, 25, tzinfo=timezone.utc) + timedelta(days=day)
        results = await search_scheduled_briefs_for_today(start_date=target_date)
        return day, results
    
    async def main():
    
        # Use asyncio.gather to run all searches concurrently
        # This improves performance by running database queries in parallel
        tasks = [run_search_for_day(day) for day in range(1, 10)]
        all_results = await asyncio.gather(*tasks)
    
        # Process and display results
        for day_offset, results in all_results:
            print(f"\n--- Day +{day_offset} Results ---")
            print(json.dumps(results, indent=2, default=str))
            if results:
                import ipdb; ipdb.set_trace()
    
    asyncio.run(main())

