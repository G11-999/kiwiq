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

from sqlmodel.ext.asyncio.session import AsyncSession
from db.session import get_async_db_as_manager, get_async_session # Assuming this provides psycopg pool
from global_config.settings import global_settings
from global_config.logger import get_prefect_or_regular_python_logger
from kiwi_app.settings import settings
from kiwi_app.billing.models import CreditType
from kiwi_app.billing import schemas as billing_schemas
from kiwi_app.data_jobs.models import DataJobType, DataJobStatus

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

# Data ingestion imports
from kiwi_app.data_jobs.ingestion.ingestion_pipeline import DocumentIngestionPipeline
from kiwi_app.data_jobs import schemas as data_job_schemas
from weaviate_client.weaviate_client import WeaviateChunkClient

# Export important functions for external use
__all__ = [
    'billing_expire_organization_credits_flow',
    'search_scheduled_briefs_and_send_reminders_flow', 
    'rag_data_ingestion_flow',
    'trigger_rag_ingestion_deployment',
    'DEFAULT_INGESTION_DOCUMENT_PATTERNS',
    'RAG_INGESTION_BATCH_SIZE',
    'RAG_INGESTION_MAX_BATCHES_PER_RUN'
]

# Constants for data ingestion
RAG_INGESTION_BATCH_SIZE = 1000
RAG_INGESTION_MAX_BATCHES_PER_RUN = 50

# Default document patterns for ingestion
# These patterns target the most important document types for RAG
DEFAULT_INGESTION_DOCUMENT_PATTERNS = [
    
    # # Uploaded files (empty docname template, so match all)
    # ("uploaded_files_*", "*"),
    
    # LinkedIn executive strategy and analysis documents
    ("linkedin_executive_strategy_*", "*"),
    ("linkedin_content_diagnostic_*", "*"),
    ("linkedin_knowledge_base_*", "*"),
    ("linkedin_uploaded_files_*", "*"),
    ("linkedin_executive_profile_namespace_*", "*"),
    ("linkedin_executive_analysis_*", "*"),
    
    # LinkedIn scraping results (updated patterns)
    ("linkedin_scraping_results_*", "*"),
    
    # LinkedIn content creation documents
    ("linkedin_content_briefs_*", "*"),
    ("linkedin_post_drafts_*", "*"),
    ("linkedin_content_ideas_*", "*"),
    
    # Blog company and strategy documents
    ("blog_company_profile_*", "*"),
    ("blog_company_strategy_*", "*"),
    ("blog_content_data_*", "*"),
    
    
    # Blog analysis documents
    ("blog_analysis_*", "*"),
    
    # Blog content diagnostic documents
    ("blog_content_diagnostic_*", "*"),
    # ("blog_content_diagnostic_report_*", "blog_content_diagnostic_report_doc"),
    
    # Blog AI query tracking documents
    ("blog_ai_query_tracking_*", "*"),
    
    # Blog content creation and delivery documents
    ("blog_spark_delivery_*", "*"),
    ("blog_ideas_namespace_*", "*"),
    ("blog_brief_namespace_*", "*"),
    ("blog_posts_draft_namespace_*", "blog_post_draft_*"),

    # External research and document summary reports
    ("external_research_reports_*", "*"),
    
    # System strategy documents (important for RAG context)
    ("blog_playbook_sys", "*"),
    ("blog_uploaded_files_*", "*"),
    
    # # LinkedIn executive strategy and analysis documents
    # ("linkedin_executive_strategy_*", "linkedin_content_playbook_doc"),
    # ("linkedin_content_diagnostic_*", "linkedin_content_diagnostic_report_doc"),
    # ("linkedin_knowledge_base_*", "linkedin_knowledge_base_analysis"),
    # ("linkedin_uploaded_files_*", "*"),
    # ("linkedin_executive_profile_namespace_*", "linkedin_executive_profile_doc"),
    # ("linkedin_executive_profile_namespace_*", "linkedin_executive_writing_style_doc"),
    # ("linkedin_executive_analysis_*", "linkedin_content_analysis_doc"),
    # ("linkedin_executive_analysis_*", "linkedin_executive_web_audit_doc"),
    # ("linkedin_executive_analysis_*", "linkedin_executive_ai_visibility_test_doc"),
    
    # # LinkedIn scraping results (updated patterns)
    # ("linkedin_scraping_results_*", "linkedin_scraped_profile_doc"),
    # ("linkedin_scraping_results_*", "linkedin_scraped_posts_doc"),
    
    # # LinkedIn content creation documents
    # ("linkedin_content_briefs_*", "linkedin_brief_*"),
    # ("linkedin_post_drafts_*", "linkedin_draft_*"),
    # ("linkedin_content_ideas_*", "linkedin_idea_*"),
    
    # # Blog company and strategy documents
    # ("blog_company_profile_*", "blog_company_doc"),
    # ("blog_company_strategy_*", "blog_content_playbook_doc"),
    # ("blog_content_data_*", "blog_post_catalog_doc"),
    
    # # Blog analysis documents
    # ("blog_analysis_*", "blog_seo_audit_doc"),
    # ("blog_analysis_*", "blog_ai_visibility_test_doc"),
    # ("blog_analysis_dashboard_*", "blog_analysis_dashboard_doc"),
    # ("blog_analysis_*", "blog_company_ai_baseline_doc"),
    # ("blog_analysis_*", "blog_competitor_content_analysis_*"),
    # ("blog_analysis_*", "blog_deep_research_report_doc"),
    # ("blog_analysis_*", "blog_content_analysis_doc"),
    # ("blog_analysis_*", "blog_competitor_ai_visibility_test_*"),
    
    # # Blog content diagnostic documents
    # ("blog_content_diagnostic_*", "blog_enhanced_ai_visibility_deepdive_doc"),
    # ("blog_content_diagnostic_*", "blog_context_package_doc"),
    # ("blog_content_diagnostic_*", "blog_keyword_validation_doc"),
    # ("blog_content_diagnostic_report_*", "blog_content_diagnostic_report_doc"),
    
    # # Blog AI query tracking documents
    # ("blog_ai_query_tracking_*", "blog_query_management_dashboard_doc"),
    # ("blog_ai_query_tracking_*", "blog_weekly_ai_visibility_report_doc"),
    # ("blog_ai_query_tracking_*", "blog_query_performance_summary_doc"),
    
    # # Blog content creation and delivery documents
    # ("blog_spark_delivery_*", "blog_user_schedule_config_doc"),
    # ("blog_spark_delivery_*", "blog_spark_content_card_*"),
    # ("blog_content_creation_*", "blog_topic_ideas_*"),
    # ("blog_content_creation_*", "blog_content_brief_*"),
    # ("blog_content_creation_*", "blog_improvement_suggestions_*"),
    # ("blog_posts_draft_*", "blog_post_draft_*"),
    
    # # System strategy documents (important for RAG context)
    # ("blog_playbook_sys", "Play 1: The Problem Authority Stack"),
    # ("blog_playbook_sys", "Play 2: The Category Pioneer Manifesto"),
    # ("blog_playbook_sys", "Play 3: The David vs Goliath Playbook"),
    # ("blog_playbook_sys", "Play 4: The Practitioner's Handbook"),
    # ("blog_playbook_sys", "Play 5: The Use Case Library"),
    # ("blog_playbook_sys", "Play 6: The Migration Magnet"),
    # ("blog_playbook_sys", "Play 7: The Integration Authority"),
    # ("blog_playbook_sys", "Play 8: The Vertical Dominator"),
    # ("blog_playbook_sys", "Play 9: The Customer Intelligence Network"),
    # ("blog_playbook_sys", "Play 10: The Research Engine"),
    # ("blog_playbook_sys", "Play 11: The Remote Revolution Handbook"),
    # ("blog_playbook_sys", "Play 12: The Maturity Model Master"),
    # ("blog_playbook_sys", "Play 13: The Community-Driven Roadmap"),
    # ("blog_playbook_sys", "Play 14: The Enterprise Translator"),
    # ("blog_playbook_sys", "Play 15: The Ecosystem Architect"),
    # ("blog_playbook_sys", "Play 16: The AI Specialist"),
    # ("blog_playbook_sys", "Play 17: The Efficiency Engine"),
    # ("blog_playbook_sys", "Play 18: The False Start Chronicles"),
    # ("blog_playbook_sys", "Play 19: The Compliance Simplifier"),
    # ("blog_playbook_sys", "Play 20: The Talent Magnet"),
    
    # # System strategy documents (important for RAG context)
    # ("system_strategy_docs_namespace", "methodology_implementation_ai_copilot"),
    # ("system_strategy_docs_namespace", "building_blocks_content_methodology"),
    # ("system_strategy_docs_namespace", "linkedin_post_evaluation_framework"),
    # ("system_strategy_docs_namespace", "linkedin_post_scoring_framework"),
    # ("system_strategy_docs_namespace", "linkedin_content_optimization_guide"),
]

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
    if not settings.ENABLE_EMAIL_DAILY_POST_NOTIFICATIONS:
        logger.info("Email daily post notifications are disabled, skipping flow")
        return {
            "status": "skipped",
            "executed_at": datetime.now(tz=timezone.utc).isoformat(),
            "target_date": target_date.strftime("%Y-%m-%dT%H:%M:%SZ") if target_date else None,
            "reason": "Email daily post notifications are disabled"
        }
    
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
            data = result.document_contents
            
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


@flow(
    name="rag-data-ingestion",
    description="Incrementally ingests updated customer documents into Weaviate for RAG applications",
    log_prints=global_settings.DEBUG,
    retries=2,
    retry_delay_seconds=120,
)
async def rag_data_ingestion_flow(
    start_timestamp: Optional[datetime] = None,
    end_timestamp: Optional[datetime] = None,
    document_patterns: Optional[List[Union[List[str], Tuple[str, str]]]] = None,  # List[str]  Tuple[str, str]
    batch_size: int = RAG_INGESTION_BATCH_SIZE,
    max_batches: int = RAG_INGESTION_MAX_BATCHES_PER_RUN,
    generate_vectors: bool = True
) -> Dict[str, Any]:
    """
    Prefect flow to incrementally ingest updated customer documents into Weaviate.
    
    This flow is designed to run as a scheduled cron job (half-hourly) to automatically process
    documents that have been updated since the last successful ingestion. It uses
    batch processing with pagination to handle large document volumes efficiently.
    
    Args:
        start_timestamp: Optional start timestamp. If None, uses last successful 
                        ingestion job's processed_timestamp_end.
        end_timestamp: Optional end timestamp. If None, uses current time.
        document_patterns: Optional list of (namespace_pattern, docname_pattern) tuples.
                          If None, uses DEFAULT_INGESTION_DOCUMENT_PATTERNS.
        batch_size: Number of documents to process per batch (default: 1000).
        max_batches: Maximum number of batches to process per run (default: 10).
        generate_vectors: Whether to generate embeddings during ingestion.
    
    Returns:
        Dict[str, Any]: Results of the ingestion process including counts,
                       timestamps, and any errors encountered.
    """
    logger = get_prefect_or_regular_python_logger(name="rag-data-ingestion-flow")
    
    # Use current time as end timestamp if not provided
    if end_timestamp is None:
        end_timestamp = datetime.now(tz=timezone.utc)
    
    # Use default document patterns if not provided
    if document_patterns is None:
        document_patterns = DEFAULT_INGESTION_DOCUMENT_PATTERNS
    
    logger.info(f"Starting RAG data ingestion process for end timestamp: {end_timestamp}")
    logger.info(f"Processing {len(document_patterns)} document pattern types with batch size: {batch_size}")
    
    # Initialize external context manager
    external_context = await get_external_context_manager_with_clients()
    logger.info("External context manager initialized for RAG ingestion")
    
    try:
        db_session = await get_async_session()
        # Task 1: Get or create data job and determine start timestamp
        data_job, resolved_start_timestamp = await get_or_create_ingestion_data_job(
            external_context=external_context,
            db_session=db_session,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp
        )
        
        logger.info(f"Data job {data_job.id} created/retrieved. Processing documents from {resolved_start_timestamp} to {end_timestamp}")
        
        # Task 2: Process documents in batches
        ingestion_results = await process_documents_in_batches(
            external_context=external_context,
            db_session=db_session,
            data_job_id=data_job.id,
            start_timestamp=resolved_start_timestamp,
            end_timestamp=end_timestamp,
            document_patterns=document_patterns,
            batch_size=batch_size,
            max_batches=max_batches,
            generate_vectors=generate_vectors
        )
        
        # Task 3: Update data job with final results
        final_job_status = await finalize_ingestion_data_job(
            external_context=external_context,
            db_session=db_session,
            data_job_id=data_job.id,
            ingestion_results=ingestion_results,
            end_timestamp=end_timestamp
        )
        
        # Create result summary
        result = {
            "status": "success",
            "executed_at": datetime.now(tz=timezone.utc).isoformat(),
            "data_job_id": str(data_job.id),
            "time_range": {
                "start_timestamp": resolved_start_timestamp.isoformat() if resolved_start_timestamp else None,
                "end_timestamp": end_timestamp.isoformat()
            },
            "processing_config": {
                "document_patterns_count": len(document_patterns),
                "batch_size": batch_size,
                "max_batches": max_batches,
                "generate_vectors": generate_vectors
            },
            "ingestion_results": ingestion_results,
            "final_job_status": final_job_status
        }
        
        logger.info(f"RAG data ingestion completed successfully. Results: {json.dumps(result, indent=2, default=str)}")
        
        return result
        
    except Exception as e:
        logger.error(f"RAG data ingestion flow failed: {e}", exc_info=True)
        
        # Try to mark data job as failed if we have a job ID
        try:
            if 'data_job' in locals() and data_job:
                # async with get_async_db_as_manager() as db:
                await external_context.data_job_service.data_job_dao.fail_job(
                    db=db_session,
                    job_id=data_job.id,
                    error_message=str(e),
                    commit=True
                )
                logger.info(f"Marked data job {data_job.id} as FAILED")
        except Exception as job_update_err:
            logger.error(f"Failed to update data job status to FAILED: {job_update_err}")
        
        # Return error information for monitoring
        error_result = {
            "status": "failed",
            "executed_at": datetime.now(tz=timezone.utc).isoformat(),
            "data_job_id": str(data_job.id) if 'data_job' in locals() and data_job else None,
            "error_message": str(e),
            "time_range": {
                "start_timestamp": resolved_start_timestamp.isoformat() if 'resolved_start_timestamp' in locals() and resolved_start_timestamp else None,
                "end_timestamp": end_timestamp.isoformat()
            },
            "ingestion_results": {
                "total_documents_processed": 0,
                "total_chunks_created": 0,
                "batches_processed": 0,
                "errors": [str(e)]
            }
        }
        
        # Re-raise the exception to ensure Prefect marks the flow as failed
        raise e
        
    finally:
        await db_session.close()
        # Clean up resources
        try:
            await external_context.close()
            logger.info("External context manager closed successfully")
        except Exception as close_err:
            logger.error(f"Error closing external context: {close_err}", exc_info=True)


@task(cache_policy=NO_CACHE)
async def get_or_create_ingestion_data_job(
    external_context: ExternalContextManager,
    db_session: AsyncSession,
    start_timestamp: Optional[datetime] = None,
    end_timestamp: Optional[datetime] = None,
) -> Tuple[Any, Optional[datetime]]:
    """
    Get or create a data job for RAG ingestion and determine the start timestamp.
    
    This function retrieves the last successful ingestion job to determine the
    start timestamp for incremental processing, or uses the provided start_timestamp.
    It creates a new data job to track the current ingestion run.
    
    Args:
        external_context: ExternalContextManager instance
        start_timestamp: Optional explicit start timestamp
        end_timestamp: End timestamp for the ingestion job
        
    Returns:
        Tuple[DataJob, Optional[datetime]]: The created data job and resolved start timestamp
    """
    logger = get_prefect_or_regular_python_logger(name="get-or-create-ingestion-data-job")
    
    resolved_start_timestamp = start_timestamp
    
    # async with get_async_db_as_manager() as db:
    # If start_timestamp is not provided, get it from the last successful ingestion job
    if resolved_start_timestamp is None:
        logger.info("No start timestamp provided, looking for last successful ingestion job")
        
        try:
            last_successful_job = await external_context.data_job_service.get_latest_successful_job(
                db=db_session,
                job_type=DataJobType.INGESTION.value
            )
            
            if last_successful_job and last_successful_job.processed_timestamp_end:
                resolved_start_timestamp = last_successful_job.processed_timestamp_end
                logger.info(f"Found last successful ingestion job {last_successful_job.id} with end timestamp: {resolved_start_timestamp}")
            else:
                logger.info("No previous successful ingestion job found, will process all documents up to end timestamp")
                resolved_start_timestamp = None
                
        except Exception as e:
            logger.warning(f"Error retrieving last successful ingestion job: {e}")
            resolved_start_timestamp = None
    
    # Create new data job for this ingestion run
    job_metadata = {
        "start_timestamp": resolved_start_timestamp.isoformat() if resolved_start_timestamp else None,
        "end_timestamp": end_timestamp.isoformat(),
        "ingestion_type": "incremental" if resolved_start_timestamp else "full",
        "document_patterns_count": len(DEFAULT_INGESTION_DOCUMENT_PATTERNS),
        "batch_size": RAG_INGESTION_BATCH_SIZE,
        "max_batches": RAG_INGESTION_MAX_BATCHES_PER_RUN
    }
    
    job_create_data = data_job_schemas.DataJobCreate(
        job_name=f"RAG Incremental Ingestion - {end_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        job_type=DataJobType.INGESTION.value,
        job_metadata=job_metadata,
        processed_timestamp_start=resolved_start_timestamp,
        processed_timestamp_end=end_timestamp,
    )
    
    data_job = await external_context.data_job_service.create_job(
        db=db_session,
        job_data=job_create_data
    )
    
    logger.info(f"Created data job {data_job.id} for RAG ingestion")
        
    return data_job, resolved_start_timestamp


@task(cache_policy=NO_CACHE)
async def process_documents_in_batches(
    external_context: ExternalContextManager,
    db_session: AsyncSession,
    data_job_id: uuid.UUID,
    start_timestamp: Optional[datetime],
    end_timestamp: datetime,
    document_patterns: List[Tuple[str, str]],
    batch_size: int,
    max_batches: int,
    generate_vectors: bool
) -> Dict[str, Any]:
    """
    Process documents in batches with pagination and ingestion into Weaviate.
    
    This function uses the BatchDocumentBuilder to efficiently search for updated 
    documents across multiple patterns, processes them in batches, and ingests them 
    into Weaviate using the DocumentIngestionPipeline.
    
    Args:
        external_context: ExternalContextManager instance
        data_job_id: ID of the data job tracking this ingestion
        start_timestamp: Start timestamp for document filtering (None for all documents)
        end_timestamp: End timestamp for document filtering
        document_patterns: List of (namespace_pattern, docname_pattern) tuples
        batch_size: Number of documents to process per batch
        max_batches: Maximum number of batches to process
        generate_vectors: Whether to generate embeddings during ingestion
        
    Returns:
        Dict[str, Any]: Results of the batch processing including counts and errors
    """
    logger = get_prefect_or_regular_python_logger(name="process-documents-in-batches")
    
    # Build value filter for updated_at field
    value_filter = {
        "updated_at": {
            "$lte": end_timestamp
        }
    }
    
    if start_timestamp:
        value_filter["updated_at"]["$gt"] = start_timestamp
        logger.info(f"Processing documents updated between {start_timestamp} and {end_timestamp}")
    else:
        logger.info(f"Processing all documents updated before {end_timestamp}")
    
    # Initialize batch builder
    batch_builder = BatchDocumentBuilder(
        external_context=external_context,
        document_patterns=document_patterns,
        value_filter=value_filter,
        batch_size=batch_size,
        max_total_batches=max_batches,
        logger=logger
    )
    
    # Initialize Weaviate client and ingestion pipeline
    try:
        async with WeaviateChunkClient() as weaviate_client:
            await weaviate_client.setup_schema()  # Ensure schema exists
            logger.info(f"Weaviate client initialized: HOST:: {weaviate_client.host}")
            
            ingestion_pipeline = DocumentIngestionPipeline(
                weaviate_client=weaviate_client,
                max_json_chunk_size=700,
                max_text_char_limit=700,
                preserve_temporal_fields=True
            )

            # Update data job with progress
            # async with get_async_db_as_manager() as db:
            status_update = data_job_schemas.DataJobStatusUpdate(
                status=DataJobStatus.STARTED
            )
            await external_context.data_job_service.data_job_dao.update_job_status(
                db=db_session,
                job_id=data_job_id,
                status_update=status_update,
                commit=True
            )
            
            # Process batches using the builder
            while True:
                # Get next batch of documents
                batch_documents = await batch_builder.build_next_batch()
                
                if not batch_documents:
                    logger.info("No more document batches available")
                    break
                
                logger.info(f"Processing batch {batch_builder.total_batches_built} with {len(batch_documents)} documents")
                
                try:
                    # Ingest documents using the pipeline
                    logger.info(f"Starting ingestion of {len(batch_documents)} documents...")
                    ingestion_results = await ingestion_pipeline.ingest_documents(
                        documents=batch_documents,
                        generate_vectors=generate_vectors
                    )
                    logger.info(f"Ingestion completed. Results: {len(ingestion_results)} document results")
                    
                    # Debug: Log ingestion results summary
                    total_chunks_in_batch = sum(chunk_count for chunk_count, _ in ingestion_results.values())
                    successful_docs_in_batch = sum(1 for chunk_count, _ in ingestion_results.values() if chunk_count > 0)
                    logger.info(f"Ingestion summary: {successful_docs_in_batch}/{len(batch_documents)} docs successful, {total_chunks_in_batch} total chunks")
                    
                    if total_chunks_in_batch == 0:
                        logger.warning("NO CHUNKS CREATED! Investigating ingestion results...")
                        for i, (result_doc_id, (chunks, errors)) in enumerate(list(ingestion_results.items())[:3]):
                            logger.warning(f"  Sample result {i+1}: doc_id='{result_doc_id}', chunks={chunks}, errors={errors}")
                    
                    # Update pattern results in batch builder using document metadata
                    for doc in batch_documents:
                        doc_id = batch_builder._generate_doc_id(doc.metadata)
                        
                        # Debug: Log doc IDs for troubleshooting
                        if len(batch_documents) <= 5:  # Only log for small batches to avoid spam
                            logger.info(f"Processing doc: batch_doc_id='{doc_id}', namespace='{doc.metadata.namespace}', docname='{doc.metadata.docname}'")
                        
                        # Get chunk count from ingestion results
                        chunk_count = 0
                        ingestion_result = ingestion_results.get(doc_id)
                        if ingestion_result:
                            chunk_count = ingestion_result[0] if isinstance(ingestion_result, tuple) else 0
                            if len(batch_documents) <= 5:
                                logger.info(f"  Found exact match in ingestion results: {chunk_count} chunks")
                        else:
                            # Try to find by partial matching if exact match fails
                            for result_doc_id, (chunks, _) in ingestion_results.items():
                                if (doc.metadata.namespace in result_doc_id and 
                                    doc.metadata.docname in result_doc_id):
                                    chunk_count = chunks
                                    if len(batch_documents) <= 5:
                                        logger.info(f"  Found partial match: batch_doc_id='{doc_id}' -> ingestion_doc_id='{result_doc_id}' ({chunks} chunks)")
                                    break
                            
                            if chunk_count == 0 and len(batch_documents) <= 5:
                                logger.warning(f"  No match found for doc_id: {doc_id}")
                                logger.warning(f"  Available ingestion result keys: {list(ingestion_results.keys())[:3]}...")
                        
                        # Always update pattern results (even if 0 chunks) to track processed docs
                        batch_builder.update_pattern_results(doc.metadata, chunk_count)
                        
                        if chunk_count > 0:
                            logger.debug(f"Pattern updated: {batch_builder.document_pattern_mapping.get(doc_id)} - doc processed with {chunk_count} chunks")
                    
                    batch_chunks_created = sum(chunk_count for chunk_count, _ in ingestion_results.values())
                    batch_successful = sum(1 for chunk_count, _ in ingestion_results.values() if chunk_count > 0)
                    
                    logger.info(f"Batch {batch_builder.total_batches_built}: processed {batch_successful}/{len(batch_documents)} documents, created {batch_chunks_created} chunks")
                    
                except Exception as batch_error:
                    error_msg = f"Error processing batch {batch_builder.total_batches_built}: {batch_error}"
                    logger.error(error_msg, exc_info=True)
                    batch_builder.errors.append(error_msg)
                    
                    # Continue to next batch on error to avoid stopping entire process
                    continue
    
    except Exception as pipeline_error:
        error_msg = f"Critical error in document processing pipeline: {pipeline_error}"
        logger.error(error_msg, exc_info=True)
        batch_builder.errors.append(error_msg)
        raise pipeline_error
    
    # Get final summary from batch builder
    summary = batch_builder.get_summary()
    
    # Compile final results
    results = {
        "total_documents_processed": summary["total_documents_processed"],
        "total_chunks_created": sum(p.get("chunks_created", 0) for p in summary["pattern_results"].values()),
        "batches_processed": summary["total_batches_built"],
        "patterns_processed": summary["patterns_completed"],
        "errors_count": summary["errors_count"],
        "errors": summary["errors"],
        "pattern_results": summary["pattern_results"],
        "processing_stopped_at_max_batches": summary["stopped_at_max_batches"],
        "builder_summary": summary  # Include full builder summary for debugging
    }
    
    logger.info(f"Batch processing completed: {results['total_documents_processed']} documents, {results['total_chunks_created']} chunks, {results['batches_processed']} batches")
    
    return results


@task(cache_policy=NO_CACHE)
async def finalize_ingestion_data_job(
    external_context: ExternalContextManager,
    db_session: AsyncSession,
    data_job_id: uuid.UUID,
    ingestion_results: Dict[str, Any],
    end_timestamp: datetime
) -> Dict[str, Any]:
    """
    Finalize the data job with processing results and update status.
    
    Args:
        external_context: ExternalContextManager instance
        data_job_id: ID of the data job to finalize
        ingestion_results: Results from the batch processing
        end_timestamp: End timestamp for the job
        
    Returns:
        Dict[str, Any]: Final job status information
    """
    logger = get_prefect_or_regular_python_logger(name="finalize-ingestion-data-job")
    
    try:
        # async with get_async_db_as_manager() as db:
        # Determine final status based on results
        has_errors = ingestion_results.get("errors_count", 0) > 0
        processed_any = ingestion_results.get("total_documents_processed", 0) > 0
        
        if has_errors and not processed_any:
            final_status = DataJobStatus.FAILED
        elif has_errors and processed_any:
            final_status = DataJobStatus.COMPLETED  # Partial success
        else:
            final_status = DataJobStatus.COMPLETED
        
        # Calculate processing duration (approximate based on current time)
        processing_duration = None
        try:
            # We can't easily get the job start time, so we'll estimate from current flow
            # This could be improved by tracking start time in the job metadata
            current_time = datetime.now(timezone.utc)
            estimated_start = end_timestamp - timedelta(hours=1)  # Rough estimate
            processing_duration = (current_time - estimated_start).total_seconds()
        except Exception as duration_err:
            logger.warning(f"Could not calculate processing duration: {duration_err}")
        
        # Call DAO methods directly to avoid service layer bugs
        job_dao = external_context.data_job_service.data_job_dao
        
        if final_status == DataJobStatus.COMPLETED:
            # Use complete_job DAO method directly
            job_result = await job_dao.complete_job(
                db=db_session,
                job_id=data_job_id,
                records_processed=ingestion_results.get("total_documents_processed", 0),
                records_failed=ingestion_results.get("errors_count", 0),
                commit=True
            )
            
            # Update metadata separately using BaseDAO update (without commit parameter)
            if ingestion_results:
                update_data = data_job_schemas.DataJobUpdate(
                    job_metadata={
                        **(job_result.job_metadata or {}),
                        "ingestion_summary": {
                            "total_chunks_created": ingestion_results.get("total_chunks_created", 0),
                            "batches_processed": ingestion_results.get("batches_processed", 0),
                            "patterns_processed": ingestion_results.get("patterns_processed", 0),
                            "stopped_at_max_batches": ingestion_results.get("processing_stopped_at_max_batches", False),
                            "processing_duration_seconds": processing_duration,
                            "end_timestamp": end_timestamp.isoformat()
                        }
                    }
                )
                
                # Use BaseDAO update without commit parameter
                job_result = await job_dao.update(
                    db=db_session,
                    db_obj=job_result,
                    obj_in=update_data
                )
                await db_session.commit()
                await db_session.refresh(job_result)
        else:
            # Use fail_job DAO method directly
            error_message = "; ".join(ingestion_results.get("errors", [])[:3]) if has_errors else "Unknown failure"
            
            job_result = await job_dao.fail_job(
                db=db_session,
                job_id=data_job_id,
                error_message=error_message,
                records_processed=ingestion_results.get("total_documents_processed", 0),
                records_failed=ingestion_results.get("errors_count", 0),
                commit=True
            )
            
            # Update metadata separately for failure details
            if ingestion_results:
                update_data = data_job_schemas.DataJobUpdate(
                    job_metadata={
                        **(job_result.job_metadata or {}),
                        "failure_details": {
                            "total_chunks_created": ingestion_results.get("total_chunks_created", 0),
                            "batches_processed": ingestion_results.get("batches_processed", 0),
                            "patterns_processed": ingestion_results.get("patterns_processed", 0),
                            "processing_duration_seconds": processing_duration,
                            "end_timestamp": end_timestamp.isoformat(),
                            "error_details": ingestion_results.get("errors", [])
                        }
                    }
                )
                
                # Use BaseDAO update without commit parameter
                job_result = await job_dao.update(
                    db=db_session,
                    db_obj=job_result,
                    obj_in=update_data
                )
                await db_session.commit()
                await db_session.refresh(job_result)
        
        job_status_info = {
            "job_id": str(data_job_id),
            "final_status": final_status.value,
            "processing_duration_seconds": processing_duration,
            "has_errors": has_errors,
            "partial_success": has_errors and processed_any,
            "job_result": data_job_schemas.DataJobRead.model_validate(job_result).model_dump() if job_result else None
        }
        
        logger.info(f"Finalized data job {data_job_id} with status {final_status.value}")
        
        return job_status_info
            
    except Exception as e:
        logger.error(f"Error finalizing data job {data_job_id}: {e}", exc_info=True)
        
        # Try to mark job as failed using the DAO method directly
        try:
            # async with get_async_db_as_manager() as db:
            job_dao = external_context.data_job_service.data_job_dao
            
            await job_dao.fail_job(
                db=db_session,
                job_id=data_job_id,
                error_message=f"Finalization failed: {str(e)}",
                records_processed=ingestion_results.get("total_documents_processed", 0),
                records_failed=ingestion_results.get("errors_count", 0) + 1,  # Add finalization error
                commit=True
            )
        except Exception as fallback_err:
            logger.error(f"Failed to update job status as fallback: {fallback_err}")
        
        raise e

async def trigger_rag_ingestion_deployment(
    start_timestamp: Optional[datetime] = None,
    end_timestamp: Optional[datetime] = None,
    document_patterns: Optional[List[Union[List[str], Tuple[str, str]]]] = None,
    batch_size: Optional[int] = None,
    max_batches: Optional[int] = None,
    generate_vectors: bool = True,
    tags: Optional[List[str]] = None
) -> FlowRun:
    """
    Helper function to manually trigger the RAG data ingestion deployment.
    
    This function can be called from API routes or other services to trigger
    on-demand document ingestion into Weaviate for RAG applications.
    
    Args:
        start_timestamp: Optional start timestamp for document filtering
        end_timestamp: Optional end timestamp for document filtering (defaults to now)
        document_patterns: Optional list of (namespace_pattern, docname_pattern) tuples
        batch_size: Number of documents to process per batch
        max_batches: Maximum number of batches to process
        generate_vectors: Whether to generate embeddings during ingestion
        tags: Optional list of tags to add to the flow run
        
    Returns:
        FlowRun: The Prefect flow run object for the triggered deployment
        
    Example:
        ```python
        # Trigger full ingestion
        flow_run = await trigger_rag_ingestion_deployment()
        
        # Trigger incremental ingestion for last 24 hours
        yesterday = datetime.now(tz=timezone.utc) - timedelta(days=1)
        flow_run = await trigger_rag_ingestion_deployment(
            start_timestamp=yesterday,
            batch_size=500
        )
        
        # Trigger ingestion for specific document types
        custom_patterns = [
            ("user_strategy_*", "content_strategy_doc_*"),
            ("content_briefs_*", "brief_*")
        ]
        flow_run = await trigger_rag_ingestion_deployment(
            document_patterns=custom_patterns
        )
        ```
    """
    logger = get_prefect_or_regular_python_logger(name="trigger_rag_data_ingestion_job")
    # Set default end timestamp to now if not provided
    # if end_timestamp is None:
    #     end_timestamp = datetime.now(tz=timezone.utc)
    
    # # Use default patterns if not provided
    # if document_patterns is None:
    #     document_patterns = DEFAULT_INGESTION_DOCUMENT_PATTERNS
    
    # Create parameters for the deployment
    parameters = {
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "document_patterns": document_patterns,
        "batch_size": batch_size or RAG_INGESTION_BATCH_SIZE,
        "max_batches": max_batches or RAG_INGESTION_MAX_BATCHES_PER_RUN,
        "generate_vectors": generate_vectors
    }

    # Add default tags if not provided
    if tags is None:
        tags = []
    tags.extend([
        "rag-ingestion",
        "manual-trigger",
    ])
    
    # Trigger the deployment
    flow_run = await run_deployment(
        name="rag-data-ingestion/half-hourly",  # References the deployment name
        parameters=parameters,
        timeout=0,  # Don't wait for completion
        tags=tags,
    )
    
    logger.info(
        f"Triggered RAG ingestion deployment 'rag-data-ingestion/half-hourly' "
        f"(Prefect Flow Run ID: {flow_run.id}) for time range: "
        f"{start_timestamp or 'last_job_end'} to {end_timestamp}"
    )
    
    return flow_run


class BatchDocumentBuilder:
    """
    Handles building batches of documents across multiple namespace/docname patterns.
    
    This class maintains state across pattern searches to efficiently build batches
    that may span multiple patterns. It handles cases where:
    - A batch fills up in the middle of a pattern search
    - Multiple patterns are needed to fill a single batch
    - Some patterns have no results
    - Pagination state needs to be maintained across patterns
    
    Key Features:
    - Cross-pattern batch building with configurable batch size
    - Automatic pagination management per pattern
    - State preservation for resuming interrupted patterns
    - Comprehensive error handling and logging
    - Memory-efficient processing with generator pattern
    - Pattern-to-document mapping for accurate statistics
    """
    
    def __init__(
        self,
        external_context: ExternalContextManager,
        document_patterns: List[Tuple[str, str]],
        value_filter: Dict[str, Any],
        batch_size: int,
        max_total_batches: int,
        logger: Any = None,
    ):
        """
        Initialize the batch builder.
        
        Args:
            external_context: ExternalContextManager for accessing services
            document_patterns: List of (namespace_pattern, docname_pattern) tuples
            value_filter: MongoDB-style filter for document selection
            batch_size: Target size for each batch
            max_total_batches: Maximum total batches to process across all patterns
        """
        self.external_context = external_context
        self.document_patterns = document_patterns
        self.value_filter = value_filter
        self.batch_size = batch_size
        self.max_total_batches = max_total_batches
        
        # State tracking
        self.current_pattern_index = 0
        self.current_pattern_skip = 0
        self.total_batches_built = 0
        self.pattern_states = {}  # Track completion status per pattern
        
        # Results tracking
        self.total_documents_seen = 0
        self.total_documents_processed = 0
        self.pattern_results = {}
        self.errors = []
        
        # Document-to-pattern mapping for accurate statistics
        self.document_pattern_mapping = {}  # doc_id -> pattern_key
        
        self.logger = logger or get_prefect_or_regular_python_logger(name="batch-document-builder")
        
    def _get_pattern_key(self, pattern_index: int) -> str:
        """Get pattern key for a given pattern index."""
        if pattern_index < len(self.document_patterns):
            namespace_pattern, docname_pattern = self.document_patterns[pattern_index]
            return f"{namespace_pattern}|{docname_pattern}"
        return "unknown_pattern"
        
    def _generate_doc_id(self, doc_metadata) -> str:
        """Generate a consistent document ID for tracking."""
        return doc_metadata.id

    async def build_next_batch(self) -> Optional[List[Any]]:
        """
        Build the next batch of documents across patterns.
        
        Returns:
            List of CustomerDocumentSearchResult objects, or None if no more documents
            
        This method intelligently builds batches that may span multiple patterns,
        handling pagination and state management automatically.
        """
        if self.total_batches_built >= self.max_total_batches:
            self.logger.info(f"Reached maximum batch limit ({self.max_total_batches})")
            return None
            
        if self.current_pattern_index >= len(self.document_patterns):
            self.logger.info("Exhausted all document patterns")
            return None
        
        batch = []
        
        # Keep filling the batch until we reach batch_size or run out of documents
        while len(batch) < self.batch_size and self.current_pattern_index < len(self.document_patterns):
            remaining_capacity = self.batch_size - len(batch)
            
            # Get current pattern
            namespace_pattern, docname_pattern = self.document_patterns[self.current_pattern_index]
            pattern_key = self._get_pattern_key(self.current_pattern_index)
            
            # Initialize pattern state if not exists
            if pattern_key not in self.pattern_states:
                self.pattern_states[pattern_key] = {
                    "completed": False,
                    "total_processed": 0,
                    "last_batch_size": 0,
                    "errors": []
                }
                self.pattern_results[pattern_key] = {
                    "documents_processed": 0,
                    "chunks_created": 0,
                    "errors_count": 0,
                    "errors": []
                }
            
            # Skip completed patterns
            if self.pattern_states[pattern_key]["completed"]:
                self.current_pattern_index += 1
                self.current_pattern_skip = 0
                continue
                
            try:
                self.logger.debug(
                    f"Searching pattern {self.current_pattern_index + 1}/{len(self.document_patterns)}: "
                    f"'{namespace_pattern}' / '{docname_pattern}' "
                    f"(skip={self.current_pattern_skip}, limit={remaining_capacity})"
                )
                
                # Search for documents from current pattern
                search_results = await self.external_context.customer_data_service.system_search_documents(
                    namespace_pattern=namespace_pattern,
                    docname_pattern=docname_pattern,
                    value_filter=self.value_filter,
                    limit=remaining_capacity,  # Only request what we need
                    skip=self.current_pattern_skip,
                    sort_by="updated_at",
                    sort_order="asc"
                )
                
                if not search_results:
                    # No more results for this pattern, mark as completed
                    self.logger.info(f"Pattern '{pattern_key}' completed - no more documents")
                    self.pattern_states[pattern_key]["completed"] = True
                    self.current_pattern_index += 1
                    self.current_pattern_skip = 0
                    continue
                
                # Filter out versioning metadata documents and raw content documents

                filtered_results = [
                    result for result in search_results 
                    if (not result.metadata.is_versioning_metadata)
                    # "File uploaded as raw content. Use `/download` endpoint to download it."
                    and (not (isinstance(result.document_contents, dict) and "raw_content" in result.document_contents and "source_filename" in result.document_contents))
                ]
                
                self.total_documents_seen += len(search_results)
                
                if not filtered_results:
                    # No non-versioning documents, but there might be more in next batch
                    self.current_pattern_skip += len(search_results)
                    continue
                
                # Add to batch and track pattern mapping
                for doc in filtered_results:
                    doc_id = self._generate_doc_id(doc.metadata)
                    self.document_pattern_mapping[doc_id] = pattern_key
                
                batch.extend(filtered_results)
                
                # Update pattern state
                self.pattern_states[pattern_key]["total_processed"] += len(filtered_results)
                self.pattern_states[pattern_key]["last_batch_size"] = len(filtered_results)
                
                # Update skip for next search
                self.current_pattern_skip += len(search_results)
                
                self.logger.info(
                    f"Added {len(filtered_results)} documents from pattern '{pattern_key}' "
                    f"(batch size now: {len(batch)}/{self.batch_size})"
                )
                
                # Check if we got fewer results than requested (end of pattern data)
                if len(search_results) < remaining_capacity:
                    self.logger.info(f"Pattern '{pattern_key}' completed - got {len(search_results)} < {remaining_capacity}")
                    self.pattern_states[pattern_key]["completed"] = True
                    self.current_pattern_index += 1
                    self.current_pattern_skip = 0
                
            except Exception as e:
                error_msg = f"Error searching pattern '{pattern_key}' at skip={self.current_pattern_skip}: {e}"
                self.logger.error(error_msg, exc_info=True)
                
                self.pattern_states[pattern_key]["errors"].append(error_msg)
                self.pattern_results[pattern_key]["errors"].append(error_msg)
                self.pattern_results[pattern_key]["errors_count"] += 1
                self.errors.append(error_msg)
                
                # Move to next pattern on error to avoid infinite loop
                self.pattern_states[pattern_key]["completed"] = True
                self.current_pattern_index += 1
                self.current_pattern_skip = 0
        
        if not batch:
            self.logger.info("No more documents available across all patterns")
            return None
        
        self.total_batches_built += 1
        self.total_documents_processed += len(batch)
        
        self.logger.info(
            f"Built batch {self.total_batches_built}: {len(batch)} documents "
            f"(total processed: {self.total_documents_processed})"
        )
        
        return batch
    
    def update_pattern_results(self, doc_metadata, chunk_count: int):
        """
        Update results for a specific pattern based on processed document.
        
        Args:
            doc_metadata: Document metadata object to identify the pattern
            chunk_count: Number of chunks created for this document (can be 0)
        """
        doc_id = self._generate_doc_id(doc_metadata)
        pattern_key = self.document_pattern_mapping.get(doc_id)
        
        if not pattern_key:
            self.logger.warning(f"No pattern mapping found for doc_id: {doc_id}")
            return
                
        if pattern_key not in self.pattern_results:
            self.pattern_results[pattern_key] = {
                "documents_processed": 0,
                "chunks_created": 0,
                "errors_count": 0,
                "errors": []
            }
        
        # Always count the document as processed
        self.pattern_results[pattern_key]["documents_processed"] += 1
        
        # Add chunks if any were created
        if chunk_count > 0:
            self.pattern_results[pattern_key]["chunks_created"] += chunk_count
            self.logger.debug(f"Updated pattern '{pattern_key}': +1 doc, +{chunk_count} chunks (total: {self.pattern_results[pattern_key]['documents_processed']} docs, {self.pattern_results[pattern_key]['chunks_created']} chunks)")
        else:
            self.logger.debug(f"Updated pattern '{pattern_key}': +1 doc, +0 chunks (total: {self.pattern_results[pattern_key]['documents_processed']} docs, {self.pattern_results[pattern_key]['chunks_created']} chunks)")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the batch building process."""
        return {
            "total_batches_built": self.total_batches_built,
            "total_documents_seen": self.total_documents_seen,
            "total_documents_processed": self.total_documents_processed,
            "current_pattern_index": self.current_pattern_index,
            "patterns_completed": sum(1 for state in self.pattern_states.values() if state.get("completed", False)),
            "total_patterns": len(self.document_patterns),
            "errors_count": len(self.errors),
            "errors": self.errors,
            "pattern_results": self.pattern_results,
            "stopped_at_max_batches": self.total_batches_built >= self.max_total_batches,
            "document_pattern_mappings_count": len(self.document_pattern_mapping)
        }


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
