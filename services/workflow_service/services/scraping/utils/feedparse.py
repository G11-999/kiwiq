import feedparser
from urllib.parse import urlparse
import re

def extract_urls_from_feed(feed_url, extract_media=False, extract_embedded_urls=True, flatten_results=True):
    """
    Extract content URLs from a feed, with optional media extraction.
    
    Args:
        feed_url (str): URL of the feed to parse
        extract_media (bool): Whether to extract media/image URLs (default: False)
        extract_embedded_urls (bool): Whether to extract embedded URLs (default: True)

    Returns:
        dict: Dictionary containing categorized URLs found in the feed
    """
    # Parse the feed
    feed = feedparser.parse(feed_url)
    
    # Initialize URL containers
    urls = {
        'article_urls': set(),      # Primary article/blog post URLs
        'source_urls': set(),       # Original source URLs (if different from article)
        'comment_urls': set(),      # Comment/discussion URLs
        'feed_home': set(),         # Feed's home page
        'alternate_urls': set(),    # Alternative versions (AMP, mobile, etc.)
        'embedded_urls': set(),     # URLs found within content
        'all_content_urls': set()   # All non-media URLs
    }
    
    if extract_media:
        urls.update({
            'media_urls': set(),    # Images, videos, audio
            'enclosure_urls': set() # Podcast episodes, attachments
        })
    
    # Helper function to add URL to sets
    def add_url(url, category='all_content_urls'):
        if url and isinstance(url, str) and url.startswith(('http://', 'https://')):
            if not extract_media and category in ['media_urls', 'enclosure_urls']:
                return  # Skip media URLs if not requested
            
            urls['all_content_urls'].add(url)
            if category in urls:
                urls[category].add(url)
    
    # Extract feed-level URLs (blog/site home)
    if hasattr(feed, 'feed'):
        # Main feed link (usually the blog's homepage)
        if hasattr(feed.feed, 'link'):
            add_url(feed.feed.link, 'feed_home')
        
        # Alternate feed links
        if hasattr(feed.feed, 'links'):
            for link in feed.feed.links:
                if hasattr(link, 'href') and hasattr(link, 'type'):
                    # Skip feed URLs (xml, rss, atom)
                    if 'xml' not in link.type and 'rss' not in link.type:
                        add_url(link.href, 'feed_home')
    
    # Extract entry-level URLs (the main content)
    for entry in feed.entries:
        # Primary article URL - this is what you want most of the time
        if hasattr(entry, 'link'):
            add_url(entry.link, 'article_urls')
        
        # Handle multiple links (some feeds provide multiple URLs per entry)
        if hasattr(entry, 'links'):
            for link in entry.links:
                if hasattr(link, 'href'):
                    # Categorize by relationship type
                    rel = getattr(link, 'rel', 'alternate')
                    
                    if rel == 'alternate':
                        # Usually the main article URL or alternative format
                        if not hasattr(entry, 'link') or entry.link != link.href:
                            add_url(link.href, 'alternate_urls')
                        else:
                            add_url(link.href, 'article_urls')
                    
                    elif rel == 'replies' or 'comment' in rel:
                        # Comments/discussion URL
                        add_url(link.href, 'comment_urls')
                    
                    elif rel == 'enclosure' and extract_media:
                        # Media attachments (podcasts, videos)
                        add_url(link.href, 'enclosure_urls')
                    
                    elif rel == 'via' or rel == 'source':
                        # Original source (for aggregators)
                        add_url(link.href, 'source_urls')
        
        # Entry ID (sometimes contains the permalink)
        if hasattr(entry, 'id') and entry.id.startswith(('http://', 'https://')):
            # Only add if different from main link
            if not hasattr(entry, 'link') or entry.id != entry.link:
                add_url(entry.id, 'alternate_urls')
        
        # Source URL (for content aggregators)
        if hasattr(entry, 'source'):
            if hasattr(entry.source, 'href'):
                add_url(entry.source.href, 'source_urls')
            if hasattr(entry.source, 'link'):
                add_url(entry.source.link, 'source_urls')
        
        # Comments URL
        if hasattr(entry, 'comments'):
            add_url(entry.comments, 'comment_urls')
        
        # Extract media if requested
        if extract_media:
            _extract_media_urls(entry, urls, add_url)
        
        # Extract URLs from content (optional)
        if extract_embedded_urls:
            _extract_embedded_urls(entry, urls, add_url, extract_media)
    
    # Convert sets to sorted lists
    result = set() if flatten_results else {}
    for key, url_set in urls.items():
        if flatten_results:
            result.update(url_set)
        else:
            result[key] = url_set
    
    return result

def _extract_media_urls(entry, urls, add_url):
    """Extract media-related URLs from an entry"""
    # Enclosures
    if hasattr(entry, 'enclosures'):
        for enclosure in entry.enclosures:
            if hasattr(enclosure, 'href'):
                add_url(enclosure.href, 'enclosure_urls')
            if hasattr(enclosure, 'url'):
                add_url(enclosure.url, 'enclosure_urls')
    
    # Media RSS extensions
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if hasattr(media, 'url'):
                add_url(media.url, 'media_urls')
    
    if hasattr(entry, 'media_thumbnail'):
        for thumb in entry.media_thumbnail:
            if hasattr(thumb, 'url'):
                add_url(thumb.url, 'media_urls')
    
    # iTunes extensions (podcasts)
    if hasattr(entry, 'itunes_image'):
        add_url(entry.itunes_image, 'media_urls')

def _extract_embedded_urls(entry, urls, add_url, include_media=False):
    """Extract URLs embedded in content text"""
    # URL regex pattern
    url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+/?(?:[-\w.,@?^=%&:/~+#])*(?:[-\w@?^=%&/~+#])?'
    
    # Common media extensions to filter out
    media_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', 
                       '.mp3', '.mp4', '.avi', '.mov', '.webm', '.ogg'}
    
    def extract_from_text(text):
        if not text:
            return
        urls_found = re.findall(url_pattern, str(text))
        for url in urls_found:
            # Check if it's a media URL
            is_media = any(url.lower().endswith(ext) for ext in media_extensions)
            
            if is_media and include_media:
                add_url(url, 'media_urls')
            elif not is_media:
                add_url(url, 'embedded_urls')
    
    # Check content
    if hasattr(entry, 'content'):
        for content in entry.content:
            if hasattr(content, 'value'):
                extract_from_text(content.value)
    
    # Check summary/description
    if hasattr(entry, 'summary'):
        extract_from_text(entry.summary)
    if hasattr(entry, 'description'):
        extract_from_text(entry.description)
