"""
Email Template Renderer

This module provides email template rendering system using Jinja2 templates with email-specific Pydantic models.
Each email type has its own dedicated data model that matches exactly what appears in that specific template.

Key features:
- Email-specific Pydantic models for type-safe data structures
- Template-specific data models that match email content order
- Generic text embedded directly in templates
- Only variable/personalized data in models
- Component-based template system for consistent styling

Design decisions:
- Email-specific models instead of generic models for better maintainability
- Variable data separated from static template text
- Jinja2 for template rendering with template inheritance
- Inline CSS styles for maximum email client compatibility

Caveats:
- Email clients have varying CSS support, so inline styles are preferred
- Template loading assumes templates are in the same directory structure
- Some email clients may not support all HTML features
"""

from typing import Optional, List, Dict, Any, Union
from pathlib import Path
from dataclasses import dataclass, field
from pydantic import BaseModel, Field, ConfigDict
from jinja2 import Environment, FileSystemLoader, select_autoescape
import os
import re
from html import unescape
from kiwi_app.settings import settings


# ==============================================================================
# BASE AND COMMON DATA MODELS
# ==============================================================================

class FooterData(BaseModel):
    """Footer configuration with default KiwiQ branding."""
    company_name: str = Field(default="KiwiQ AI", description="Company name")
    company_address: str = Field(default="San Francisco, CA", description="Company address")
    unsubscribe_link: Optional[str] = Field(default=None, description="Unsubscribe URL")
    powered_by_name: str = Field(default="KiwiQ Platform", description="Powered by text")
    powered_by_url: str = Field(default="https://kiwiq.ai", description="Powered by URL")
    support_email: str = Field(default="support@kiwiq.ai", description="Support email address")
    help_center_url: str = Field(default="https://help.kiwiq.ai", description="Help center URL")


class BaseEmailData(BaseModel):
    """
    Base email data model containing common components across all emails.
    
    This model provides default values for common email elements like footer,
    support links, and company branding. All email-specific models should
    inherit from this base model to ensure consistency.
    """
    user_name: str = Field(description="Recipient's name")
    footer: FooterData = Field(default_factory=FooterData, description="Footer configuration")
    
    class Config:
        """Pydantic configuration."""
        # Allow arbitrary types for flexibility
        arbitrary_types_allowed = True


# ==============================================================================
# EMAIL-SPECIFIC DATA MODELS
# ==============================================================================

class WelcomeEmailData(BaseEmailData):
    """Data model for welcome emails with congratulations and feature highlights."""
    congratulations_message: str = Field(
        default="🎉 Congratulations! Your account has been successfully set up and you're ready to get started.",
        description="Welcome message with emoji"
    )
    action_button_url: str = Field(
        default="https://app.kiwiq.com/dashboard",
        description="Main CTA button URL"
    )
    features_page_url: str = Field(
        default="https://kiwiq.com/features",
        description="Link to features page"
    )


class AccountConfirmationEmailData(BaseEmailData):
    """Data model for account confirmation emails."""
    opening_message: Optional[str] = Field(default=None, description="Opening message to include in the email")
    confirmation_url: str = Field(description="Account confirmation link")
    expiry_hours: Optional[int] = Field(default=None, description="Link expiry time in hours")
    expiry_minutes: Optional[int] = Field(default=None, description="Link expiry time in minutes")
    additional_message: Optional[str] = Field(default=None, description="Additional message to include in the email")
    is_email_confirmation: bool = Field(default=False, description="Whether the email is a confirmation of email address")


class FirstStepsGuideEmailData(BaseEmailData):
    """Data model for first steps guide emails."""
    start_writing_url: str = Field(description="Link to start writing first post")
    explore_ideas_url: str = Field(description="Link to explore content ideas")
    calendar_url: str = Field(description="Link to content calendar")


class DraftProgressReminderEmailData(BaseEmailData):
    """Data model for draft progress reminder emails."""
    brief_title: str = Field(description="Title/topic of the draft post")
    publication_time: str = Field(description="Scheduled publication time")
    complete_post_url: str = Field(description="Link to complete the draft post")
    calendar_url: str = Field(description="Link to content calendar for rescheduling")


class AchievementMilestoneEmailData(BaseEmailData):
    """Data model for achievement milestone emails."""
    posts_published: int = Field(description="Number of posts published")
    consistency_streak_weeks: int = Field(description="Consistency streak in weeks")
    next_milestone_target: str = Field(description="Description of next achievement target")
    content_journey_url: str = Field(description="Link to review content journey/stats")


class GentleReminderEmailData(BaseEmailData):
    """Data model for gentle reminder emails for inactive users."""
    draft_posts_count: int = Field(description="Number of draft posts waiting")
    new_ideas_count: int = Field(description="Number of new content ideas generated")
    scheduled_posts_count: int = Field(description="Number of scheduled posts this week")
    calendar_url: str = Field(description="Link to review calendar")


class PasswordResetEmailData(BaseEmailData):
    """Data model for password reset emails."""
    reset_url: str = Field(description="Password reset URL with token")
    expiry_hours: int = Field(default=24, description="Link expiry time in hours")


class NotificationEmailData(BaseEmailData):
    """Data model for general notification emails."""
    message: str = Field(description="Main notification message")
    action_button_text: Optional[str] = Field(default=None, description="CTA button text")
    action_button_url: Optional[str] = Field(default=None, description="CTA button URL")


class MagicLoginLinkEmailData(BaseEmailData):
    """Data model for magic login link emails."""
    magic_login_url: str = Field(description="Magic login URL with embedded token")
    expiry_minutes: int = Field(default=10, description="Link expiry time in minutes")


# ==============================================================================
# EMAIL RENDERER CLASS
# ==============================================================================

@dataclass
class EmailRenderer:
    """
    Email template renderer using Jinja2 templates with email-specific data models.
    
    This class handles loading and rendering of email templates where each email type
    has its own dedicated data model that matches the template content structure.
    
    Attributes:
        template_dir: Path to the template directory
        env: Jinja2 environment for template rendering
    """
    
    template_dir: Path = field(default_factory=lambda: Path(__file__).parent)
    env: Environment = field(init=False)
    
    def __post_init__(self):
        """Initialize the Jinja2 environment after dataclass initialization."""
        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )
        
        # Register custom filters if needed
        self.env.filters['default_if_none'] = lambda value, default: default if value is None else value
    
    def html_to_text(self, html_content: str) -> str:
        """
        Convert HTML email content to clean, well-formatted plain text.
        
        This method extracts text content from HTML, converts links to a readable format,
        and ensures proper spacing and line breaks for text-only email clients.
        
        Args:
            html_content: HTML email content to convert
            
        Returns:
            Clean, formatted plain text version of the email
            
        Key conversions:
        - <a href="url">text</a> -> text (url)
        - <p>, <div>, <h1-h6> -> text with double line breaks
        - <br> -> single line break
        - <li> -> bullet points with proper indentation
        - HTML entities -> decoded text
        - Multiple whitespace -> single space
        """
        # Remove HTML comments and scripts
        text = re.sub(r'<!--.*?-->', '', html_content, flags=re.DOTALL)
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove CSS style blocks completely
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove inline style attributes
        text = re.sub(r'\s*style\s*=\s*["\'][^"\']*["\']', '', text, flags=re.IGNORECASE)
        
        # Convert headers to uppercase with spacing
        text = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', lambda m: f"\n\n{m.group(1).strip().upper()}\n{'-' * min(len(m.group(1).strip()), 50)}\n", text, flags=re.IGNORECASE | re.DOTALL)
        
        # Convert links to text format: "Link Text (http://example.com)"
        def link_replacer(match):
            href = match.group(1).strip()
            link_text = re.sub(r'<[^>]+>', '', match.group(2)).strip()  # Remove any nested tags
            
            # Skip if href is empty, is just a hash, or matches the link text
            if not href or href == '#' or href == link_text:
                return link_text
            # Skip mailto links (just show the text)
            if href.startswith('mailto:'):
                return link_text
            # Skip if link text is empty
            if not link_text:
                return href
            
            return f"{link_text} ({href})"
        
        text = re.sub(r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', link_replacer, text, flags=re.IGNORECASE | re.DOTALL)
        
        # Handle table structures - convert to readable format
        text = re.sub(r'<table[^>]*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</table>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<tr[^>]*>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'</tr>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<td[^>]*>', ' ', text, flags=re.IGNORECASE)
        text = re.sub(r'</td>', ' ', text, flags=re.IGNORECASE)
        text = re.sub(r'<th[^>]*>', ' ', text, flags=re.IGNORECASE)
        text = re.sub(r'</th>', ' ', text, flags=re.IGNORECASE)
        
        # Convert list items to bullet points
        text = re.sub(r'<li[^>]*>(.*?)</li>', lambda m: f"\n• {re.sub(r'<[^>]+>', '', m.group(1)).strip()}", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'</?[uo]l[^>]*>', '\n', text, flags=re.IGNORECASE)
        
        # Convert block elements to line breaks
        for tag in ['p', 'div', 'section', 'article', 'header', 'footer', 'main']:
            text = re.sub(f'<{tag}[^>]*>', '\n\n', text, flags=re.IGNORECASE)
            text = re.sub(f'</{tag}>', '', text, flags=re.IGNORECASE)
        
        # Convert line breaks
        text = re.sub(r'<br[^>]*/?>', '\n', text, flags=re.IGNORECASE)
        
        # Convert buttons to call-to-action format
        text = re.sub(r'<button[^>]*>(.*?)</button>', lambda m: f"\n\n>>> {re.sub(r'<[^>]+>', '', m.group(1)).strip()} <<<\n\n", text, flags=re.IGNORECASE | re.DOTALL)
        
        # Remove all remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Decode HTML entities
        text = unescape(text)
        
        # Clean up whitespace and formatting
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Clean up each line
            line = re.sub(r'[ \t]+', ' ', line)  # Multiple spaces to single space
            line = line.strip()
            
            # Skip empty lines but preserve intentional spacing
            if line or (cleaned_lines and cleaned_lines[-1]):
                cleaned_lines.append(line)
        
        # Join lines and clean up excessive newlines
        text = '\n'.join(cleaned_lines)
        text = re.sub(r'\n{3,}', '\n\n', text)  # Multiple newlines to double newlines
        text = text.strip()
        
        # Add email formatting structure
        if text:
            # Add text email headers
            text = f"{text}\n\n{'=' * 40}\nThis email was sent by KiwiQ AI Platform"
        
        return text
    
    def _render_template(self, template_name: str, data: BaseModel, **kwargs) -> str:
        """
        Internal method to render any email template with the provided data.
        
        Args:
            template_name: Name of the template file to render
            data: Email-specific data model instance
            **kwargs: Additional template variables
            
        Returns:
            Rendered HTML email as a string
            
        Raises:
            TemplateNotFound: If the specified template doesn't exist
            TemplateError: If there's an error during template rendering
        """
        # Convert data model to dict and merge with kwargs
        context = data.model_dump()
        context.update(kwargs)
        
        template = self.env.get_template(template_name)
        return template.render(**context)
    
    # ==========================================================================
    # EMAIL-SPECIFIC RENDERING METHODS
    # ==========================================================================
    
    def render_welcome_email(self, data: WelcomeEmailData, **kwargs) -> str:
        """
        Render a welcome email for new users.
        
        Args:
            data: WelcomeEmailData instance with user-specific information
            **kwargs: Additional template variables
            
        Returns:
            Rendered welcome email HTML
        """
        return self._render_template('welcome.html', data, **kwargs)
    
    def render_account_confirmation_email(self, data: AccountConfirmationEmailData, **kwargs) -> str:
        """
        Render an account confirmation email.
        
        Args:
            data: AccountConfirmationEmailData instance with confirmation details
            **kwargs: Additional template variables
            
        Returns:
            Rendered account confirmation email HTML
        """
        return self._render_template('account_confirmation.html', data, **kwargs)
    
    def render_first_steps_guide_email(self, data: FirstStepsGuideEmailData, **kwargs) -> str:
        """
        Render a first steps guide email.
        
        Args:
            data: FirstStepsGuideEmailData instance with onboarding links
            **kwargs: Additional template variables
            
        Returns:
            Rendered first steps guide email HTML
        """
        return self._render_template('first_steps_guide.html', data, **kwargs)
    
    def render_draft_progress_reminder_email(self, data: DraftProgressReminderEmailData, **kwargs) -> str:
        """
        Render a draft progress reminder email.
        
        Args:
            data: DraftProgressReminderEmailData instance with draft details
            **kwargs: Additional template variables
            
        Returns:
            Rendered draft progress reminder email HTML
        """
        return self._render_template('draft_progress_reminder.html', data, **kwargs)
    
    def render_achievement_milestone_email(self, data: AchievementMilestoneEmailData, **kwargs) -> str:
        """
        Render an achievement milestone email.
        
        Args:
            data: AchievementMilestoneEmailData instance with milestone details
            **kwargs: Additional template variables
            
        Returns:
            Rendered achievement milestone email HTML
        """
        return self._render_template('achievement_milestone.html', data, **kwargs)
    
    def render_gentle_reminder_email(self, data: GentleReminderEmailData, **kwargs) -> str:
        """
        Render a gentle reminder email for inactive users.
        
        Args:
            data: GentleReminderEmailData instance with activity details
            **kwargs: Additional template variables
            
        Returns:
            Rendered gentle reminder email HTML
        """
        return self._render_template('gentle_reminder.html', data, **kwargs)
    
    def render_password_reset_email(self, data: PasswordResetEmailData, **kwargs) -> str:
        """
        Render a password reset email.
        
        Args:
            data: PasswordResetEmailData instance with reset details
            **kwargs: Additional template variables
            
        Returns:
            Rendered password reset email HTML
        """
        return self._render_template('password_reset.html', data, **kwargs)
    
    def render_notification_email(self, data: NotificationEmailData, **kwargs) -> str:
        """
        Render a general notification email.
        
        Args:
            data: NotificationEmailData instance with notification details
            **kwargs: Additional template variables
            
        Returns:
            Rendered notification email HTML
        """
        return self._render_template('notification.html', data, **kwargs)
    
    def render_magic_login_link_email(self, data: MagicLoginLinkEmailData, **kwargs) -> str:
        """
        Render a magic login link email.
        
        Args:
            data: MagicLoginLinkEmailData instance with magic login details
            **kwargs: Additional template variables
            
        Returns:
            Rendered magic login link email HTML
        """
        return self._render_template('magic_login_link.html', data, **kwargs)
    



# ==============================================================================
# EXAMPLE USAGE AND TESTING
# ==============================================================================

if __name__ == "__main__":
    # Create an email renderer
    renderer = EmailRenderer()
    
    # Create rendered_samples directory
    samples_dir = Path(__file__).parent / Path("rendered_samples")
    samples_dir.mkdir(exist_ok=True)
    
    print("🚀 Email Template Rendering Examples with New Model System\n")
    print("=" * 60)
    
    # Example: Welcome email
    print("\n📧 Example 1: Welcome Email")
    print("-" * 30)
    
    welcome_data = WelcomeEmailData(
        user_name="John Doe",
        congratulations_message="🎉 Welcome to KiwiQ! Your journey starts here.",
        action_button_url="https://app.kiwiq.com/dashboard",
        features_page_url="https://kiwiq.com/features"
    )
    
    welcome_html = renderer.render_welcome_email(welcome_data)
    welcome_text = renderer.html_to_text(welcome_html)
    
    welcome_html_file = samples_dir / "welcome_email.html"
    welcome_text_file = samples_dir / "welcome_email.txt"
    welcome_html_file.write_text(welcome_html)
    welcome_text_file.write_text(welcome_text)
    
    print(f"✅ Welcome email rendered successfully!")
    print(f"   HTML length: {len(welcome_html):,} characters")
    print(f"   Text length: {len(welcome_text):,} characters")
    print(f"   Footer company: {welcome_data.footer.company_name}")
    print(f"   Saved to: {welcome_html_file} & {welcome_text_file}")
    
    # Example: Account confirmation email with custom footer
    print("\n📧 Example 2: Account Confirmation Email")
    print("-" * 30)
    
    # Create custom footer for this specific email
    custom_footer = FooterData(
        unsubscribe_link="https://app.kiwiq.com/unsubscribe?token=abc123"
    )
    
    confirmation_data = AccountConfirmationEmailData(
        user_name="Alice Johnson",
        confirmation_url="https://app.kiwiq.com/confirm?token=abc123xyz",
        footer=custom_footer
    )
    
    confirmation_html = renderer.render_account_confirmation_email(confirmation_data)
    confirmation_text = renderer.html_to_text(confirmation_html)
    
    confirmation_html_file = samples_dir / "account_confirmation_email.html"
    confirmation_text_file = samples_dir / "account_confirmation_email.txt"
    confirmation_html_file.write_text(confirmation_html)
    confirmation_text_file.write_text(confirmation_text)
    
    print(f"✅ Account confirmation email rendered successfully!")
    print(f"   HTML length: {len(confirmation_html):,} characters")
    print(f"   Text length: {len(confirmation_text):,} characters")
    print(f"   Support email: {confirmation_data.footer.support_email}")
    print(f"   Saved to: {confirmation_html_file} & {confirmation_text_file}")
    
    # Example: First steps guide
    print("\n📧 Example 3: First Steps Guide Email")
    print("-" * 30)
    
    first_steps_data = FirstStepsGuideEmailData(
        user_name="Carol Williams",
        start_writing_url="https://app.kiwiq.com/create",
        explore_ideas_url="https://app.kiwiq.com/ideas",
        calendar_url="https://app.kiwiq.com/calendar"
    )
    
    first_steps_html = renderer.render_first_steps_guide_email(first_steps_data)
    first_steps_text = renderer.html_to_text(first_steps_html)
    
    first_steps_html_file = samples_dir / "first_steps_guide_email.html"
    first_steps_text_file = samples_dir / "first_steps_guide_email.txt"
    first_steps_html_file.write_text(first_steps_html)
    first_steps_text_file.write_text(first_steps_text)
    
    print(f"✅ First steps guide email rendered successfully!")
    print(f"   HTML length: {len(first_steps_html):,} characters")
    print(f"   Text length: {len(first_steps_text):,} characters")
    print(f"   Saved to: {first_steps_html_file} & {first_steps_text_file}")
    
    # Example: Draft progress reminder
    print("\n📧 Example 4: Draft Progress Reminder")
    print("-" * 30)
    
    reminder_data = DraftProgressReminderEmailData(
        user_name="Bob Smith",
        brief_title="LinkedIn Content Strategy Tips",
        publication_time="Today at 3:00 PM",
        complete_post_url="https://app.kiwiq.com/drafts/123",
        calendar_url="https://app.kiwiq.com/calendar"
    )
    
    reminder_html = renderer.render_draft_progress_reminder_email(reminder_data)
    reminder_text = renderer.html_to_text(reminder_html)
    
    reminder_html_file = samples_dir / "draft_progress_reminder_email.html"
    reminder_text_file = samples_dir / "draft_progress_reminder_email.txt"
    reminder_html_file.write_text(reminder_html)
    reminder_text_file.write_text(reminder_text)
    
    print(f"✅ Draft progress reminder email rendered successfully!")
    print(f"   HTML length: {len(reminder_html):,} characters")
    print(f"   Text length: {len(reminder_text):,} characters")
    print(f"   Using default footer: {reminder_data.footer.company_name}")
    print(f"   Saved to: {reminder_html_file} & {reminder_text_file}")
    
    # Example: Achievement milestone
    print("\n📧 Example 5: Achievement Milestone Email")
    print("-" * 30)
    
    milestone_data = AchievementMilestoneEmailData(
        user_name="David Chen",
        posts_published=25,
        consistency_streak_weeks=8,
        next_milestone_target="50 posts published",
        content_journey_url="https://app.kiwiq.com/analytics"
    )
    
    milestone_html = renderer.render_achievement_milestone_email(milestone_data)
    milestone_text = renderer.html_to_text(milestone_html)
    
    milestone_html_file = samples_dir / "achievement_milestone_email.html"
    milestone_text_file = samples_dir / "achievement_milestone_email.txt"
    milestone_html_file.write_text(milestone_html)
    milestone_text_file.write_text(milestone_text)
    
    print(f"✅ Achievement milestone email rendered successfully!")
    print(f"   HTML length: {len(milestone_html):,} characters")
    print(f"   Text length: {len(milestone_text):,} characters")
    print(f"   Saved to: {milestone_html_file} & {milestone_text_file}")
    
    # Example: Gentle reminder
    print("\n📧 Example 6: Gentle Reminder Email")
    print("-" * 30)
    
    gentle_reminder_data = GentleReminderEmailData(
        user_name="Emma Wilson",
        draft_posts_count=3,
        new_ideas_count=7,
        scheduled_posts_count=2,
        calendar_url="https://app.kiwiq.com/calendar"
    )
    
    gentle_reminder_html = renderer.render_gentle_reminder_email(gentle_reminder_data)
    gentle_reminder_text = renderer.html_to_text(gentle_reminder_html)
    
    gentle_reminder_html_file = samples_dir / "gentle_reminder_email.html"
    gentle_reminder_text_file = samples_dir / "gentle_reminder_email.txt"
    gentle_reminder_html_file.write_text(gentle_reminder_html)
    gentle_reminder_text_file.write_text(gentle_reminder_text)
    
    print(f"✅ Gentle reminder email rendered successfully!")
    print(f"   HTML length: {len(gentle_reminder_html):,} characters")
    print(f"   Text length: {len(gentle_reminder_text):,} characters")
    print(f"   Saved to: {gentle_reminder_html_file} & {gentle_reminder_text_file}")
    
    # Example: Password reset email
    print("\n📧 Example 7: Password Reset Email")
    print("-" * 30)
    
    password_reset_data = PasswordResetEmailData(
        user_name="Grace Thompson",
        reset_url="https://app.kiwiq.com/reset-password?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        expiry_hours=1
    )
    
    password_reset_html = renderer.render_password_reset_email(password_reset_data)
    password_reset_text = renderer.html_to_text(password_reset_html)
    
    password_reset_html_file = samples_dir / "password_reset_email.html"
    password_reset_text_file = samples_dir / "password_reset_email.txt"
    password_reset_html_file.write_text(password_reset_html)
    password_reset_text_file.write_text(password_reset_text)
    
    print(f"✅ Password reset email rendered successfully!")
    print(f"   HTML length: {len(password_reset_html):,} characters")
    print(f"   Text length: {len(password_reset_text):,} characters")
    print(f"   Uses new notice component for important messages")
    print(f"   Saved to: {password_reset_html_file} & {password_reset_text_file}")
    
    # Example: General notification
    print("\n📧 Example 8: General Notification Email")
    print("-" * 30)
    
    notification_data = NotificationEmailData(
        user_name="Frank Garcia",
        message="Your monthly analytics report has been generated and is ready for download. The report includes detailed insights from the past 30 days, including engagement metrics, best performing posts, and content recommendations.",
        action_button_text="Download Report",
        action_button_url="https://app.kiwiq.com/reports/monthly"
    )
    
    notification_html = renderer.render_notification_email(notification_data)
    notification_text = renderer.html_to_text(notification_html)
    
    notification_html_file = samples_dir / "general_notification_email.html"
    notification_text_file = samples_dir / "general_notification_email.txt"
    notification_html_file.write_text(notification_html)
    notification_text_file.write_text(notification_text)
    
    print(f"✅ General notification email rendered successfully!")
    print(f"   HTML length: {len(notification_html):,} characters")
    print(f"   Text length: {len(notification_text):,} characters")
    print(f"   Saved to: {notification_html_file} & {notification_text_file}")
    
    # Example: Magic login link
    print("\n📧 Example 9: Magic Login Link Email")
    print("-" * 30)
    
    magic_login_data = MagicLoginLinkEmailData(
        user_name="Sarah Johnson",
        magic_login_url="https://app.kiwiq.com/magic-login?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9&csrf=abc123",
        expiry_minutes=10
    )
    
    magic_login_html = renderer.render_magic_login_link_email(magic_login_data)
    magic_login_text = renderer.html_to_text(magic_login_html)
    
    magic_login_html_file = samples_dir / "magic_login_link_email.html"
    magic_login_text_file = samples_dir / "magic_login_link_email.txt"
    magic_login_html_file.write_text(magic_login_html)
    magic_login_text_file.write_text(magic_login_text)
    
    print(f"✅ Magic login link email rendered successfully!")
    print(f"   HTML length: {len(magic_login_html):,} characters")
    print(f"   Text length: {len(magic_login_text):,} characters")
    print(f"   Includes browser security warning and CSRF protection")
    print(f"   Saved to: {magic_login_html_file} & {magic_login_text_file}")
    
    print("\n" + "=" * 60)
    print("🎯 All email examples rendered with email-specific models!")
    print("📝 Each email type now has its own dedicated data structure.")
    print(f"📁 All rendered files (HTML & TXT) saved to: {samples_dir.absolute()}")
    print("\n💡 Pro tips:")
    print("   📧 Open the HTML files in a web browser to see visual emails")
    print("   📄 Open the TXT files to see clean text-only versions")
    print("   🔗 Text versions include extracted links in readable format")
    print("   🔐 Magic login links include security warnings and CSRF protection")
    
    # Create an index file for easy viewing
    index_html = """<!DOCTYPE html>
<html>
<head>
    <title>KiwiQ Email Templates - Rendered Samples</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { color: #0867ec; }
        .email-list { list-style: none; padding: 0; }
        .email-list li { margin: 15px 0; padding: 15px; background: #f8f9fa; border-radius: 8px; }
        .email-title { font-size: 18px; font-weight: bold; color: #333; margin-bottom: 8px; }
        .description { color: #666; font-size: 14px; margin-bottom: 10px; }
        .format-links { display: flex; gap: 15px; margin-top: 10px; }
        .format-links a { 
            padding: 8px 16px; 
            background: #0867ec; 
            color: white; 
            text-decoration: none; 
            border-radius: 4px;
            font-size: 14px;
            transition: background 0.3s;
        }
        .format-links a:hover { background: #065bb5; }
        .format-links a.text { background: #28a745; }
        .format-links a.text:hover { background: #218838; }
        .note { background: #e3f2fd; padding: 15px; border-radius: 8px; margin: 20px 0; color: #1565c0; }
    </style>
</head>
<body>
    <h1>🎉 KiwiQ Email Templates - Rendered Samples</h1>
    <div class="note">
        <strong>📧 Dual Format Support:</strong> Each email is available in both HTML (rich format) and TXT (plain text) versions.
        Text versions include extracted links and are perfect for email clients that don't support HTML.
    </div>
    
    <ul class="email-list">
        <li>
            <div class="email-title">Welcome Email</div>
            <div class="description">New user welcome with congratulations and feature highlights</div>
            <div class="format-links">
                <a href="welcome_email.html">📧 View HTML</a>
                <a href="welcome_email.txt" class="text">📄 View Text</a>
            </div>
        </li>
        <li>
            <div class="email-title">Account Confirmation Email</div>
            <div class="description">Email verification with action required notice</div>
            <div class="format-links">
                <a href="account_confirmation_email.html">📧 View HTML</a>
                <a href="account_confirmation_email.txt" class="text">📄 View Text</a>
            </div>
        </li>
        <li>
            <div class="email-title">First Steps Guide Email</div>
            <div class="description">Onboarding guide with three simple action steps</div>
            <div class="format-links">
                <a href="first_steps_guide_email.html">📧 View HTML</a>
                <a href="first_steps_guide_email.txt" class="text">📄 View Text</a>
            </div>
        </li>
        <li>
            <div class="email-title">Draft Progress Reminder Email</div>
            <div class="description">Urgent reminder for scheduled post completion</div>
            <div class="format-links">
                <a href="draft_progress_reminder_email.html">📧 View HTML</a>
                <a href="draft_progress_reminder_email.txt" class="text">📄 View Text</a>
            </div>
        </li>
        <li>
            <div class="email-title">Achievement Milestone Email</div>
            <div class="description">Celebration of user content creation milestones</div>
            <div class="format-links">
                <a href="achievement_milestone_email.html">📧 View HTML</a>
                <a href="achievement_milestone_email.txt" class="text">📄 View Text</a>
            </div>
        </li>
        <li>
            <div class="email-title">Gentle Reminder Email</div>
            <div class="description">Re-engagement for inactive users with pending items</div>
            <div class="format-links">
                <a href="gentle_reminder_email.html">📧 View HTML</a>
                <a href="gentle_reminder_email.txt" class="text">📄 View Text</a>
            </div>
        </li>
        <li>
            <div class="email-title">Password Reset Email</div>
            <div class="description">Secure password reset with expiry notice and security tips</div>
            <div class="format-links">
                <a href="password_reset_email.html">📧 View HTML</a>
                <a href="password_reset_email.txt" class="text">📄 View Text</a>
            </div>
        </li>
        <li>
            <div class="email-title">General Notification Email</div>
            <div class="description">General purpose notification with optional action button</div>
            <div class="format-links">
                <a href="general_notification_email.html">📧 View HTML</a>
                <a href="general_notification_email.txt" class="text">📄 View Text</a>
            </div>
        </li>
        <li>
            <div class="email-title">Magic Login Link Email</div>
            <div class="description">Secure passwordless login with CSRF protection and browser security warnings</div>
            <div class="format-links">
                <a href="magic_login_link_email.html">📧 View HTML</a>
                <a href="magic_login_link_email.txt" class="text">📄 View Text</a>
            </div>
        </li>
    </ul>
    
    <hr>
    <p><em>Generated by KiwiQ Email Template System - Supporting both HTML and Plain Text formats</em></p>
</body>
</html>"""
    
    index_file = samples_dir / "index.html"
    index_file.write_text(index_html)
    print(f"📋 Index file created: {index_file}")
    print("   Open index.html to browse all email templates!") 