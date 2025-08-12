import re
import uuid
from bs4 import BeautifulSoup
import trafilatura
from workflow_service.services.scraping.utils.markdown_converter import convert_to_markdown_from_raw_file_content


def clean_html_text_and_convert_to_markdown(html: str, remove_links: bool = True) -> str:
    """
    Clean HTML text and convert to markdown.
    """

    # Pre-process to protect headings
    soup = BeautifulSoup(html, 'html.parser')
    
    # Store original headings
    heading_map = {}
    for i, heading in enumerate(soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])):
        placeholder = f"HEADING_PLACEHOLDER_{i}"
        heading_map[placeholder] = {
            'tag': heading.name,
            'text': heading.get_text(strip=True),
            'html': str(heading)
        }
        # Replace heading with a paragraph containing placeholder
        new_tag = soup.new_tag('p')
        new_tag.string = f"{placeholder}: {heading.get_text(strip=True)}"
        heading.replace_with(new_tag)
    
    # Extract with trafilatura
    output = trafilatura.extract(
        str(soup),
        output_format="html",
        include_formatting=True,
        include_links=True,
        favor_recall=True,
        include_comments=True
    )

    # Restore headings
    if output:
        for placeholder, heading_info in heading_map.items():
            # Replace placeholder with original heading HTML
            output = output.replace(
                f"<p>{placeholder}: {heading_info['text']}</p>",
                heading_info['html']
            )
            # Also handle case where <p> tags were stripped
            output = output.replace(
                f"{placeholder}: {heading_info['text']}",
                heading_info['html']
            )

    # output = trafilatura.extract(html, output_format="html", include_formatting=True, include_links=True, favor_recall=True, include_comments=True, )
    # output = trafilatura.bare_extraction(html, as_dict=True, include_formatting=True, include_links=True, favor_recall=True, include_comments=True, )
    # print(output)
    # import ipdb; ipdb.set_trace()
    
    cleaned_markdown_content = convert_to_markdown_from_raw_file_content(output, f"temp_{uuid.uuid4()}.html")

    if remove_links:
        cleaned_markdown_content = remove_markdown_links(cleaned_markdown_content, max_chars=None)

    return cleaned_markdown_content


def remove_markdown_links(text: str, max_chars: int | None = None) -> str:
    """
    Remove markdown links from text while retaining the bracketed link text.

    This strips the URL portion of markdown links while preserving the link
    label wrapped in brackets. For example, "[Example](https://x.com)"
    becomes "[Example]".

    Args:
        text: The markdown text containing links.
        max_chars: Optional maximum characters to retain from the link text.
            When provided and the link text exceeds this length, the text is
            truncated and an ellipsis is appended within the brackets.

    Returns:
        Text with markdown links removed and link text preserved in brackets.
    """

    def replace_link(match: re.Match[str]) -> str:
        link_text: str = match.group(1)
        if max_chars is not None and len(link_text) > max_chars:
            # Truncate and add ellipsis if text is longer than max_chars, keep brackets
            return f"[{link_text[:max_chars]}...]"
        return f"[{link_text}]"
    
    # Pattern to match markdown links: [text](url)
    # Using non-greedy matching (*?) to avoid matching multiple links
    pattern = r'\[([^\]]*?)\]\([^\)]*?\)'
    
    # Replace all markdown links with just the text part
    result = re.sub(pattern, replace_link, text)
    
    return result


def remove_markdown_links_advanced(
    text: str,
    max_chars: int | None = None,
    placeholder: str = "",
) -> str:
    """
    Advanced version with more options for handling markdown links, keeping
    the link text wrapped in brackets after cleanup.

    Args:
        text: The markdown text containing links.
        max_chars: Optional maximum characters to retain from link text. If
            provided and exceeded, the text is truncated (accounting for
            ellipsis) and preserved inside brackets.
        placeholder: Text to use inside the brackets if link text is empty.

    Returns:
        Text with markdown links processed and link text preserved in brackets.
    """

    def replace_link(match: re.Match[str]) -> str:
        link_text: str = match.group(1).strip()

        # Handle empty link text
        if not link_text:
            return f"[{placeholder}]"

        if max_chars is not None and len(link_text) > max_chars:
            if max_chars <= 3:
                # If max_chars is very small, just truncate (no ellipsis), keep brackets
                return f"[{link_text[:max_chars]}]"
            else:
                # Add ellipsis for longer truncations, keep brackets
                return f"[{link_text[: max_chars - 3]}...]"
        return f"[{link_text}]"
    
    # Pattern for inline links [text](url) - using non-greedy matching
    pattern_inline = r'\[([^\]]*?)\]\([^\)]*?\)'
    result = re.sub(pattern_inline, replace_link, text)
    
    # # Remove reference definitions [ref]: url
    # pattern_ref_def = r'^\[[^\]]+?\]:\s+.+?$'
    # result = re.sub(pattern_ref_def, '', result, flags=re.MULTILINE)
    
    # Convert reference-style links [text][ref] to just text
    pattern_ref_link = r'\[([^\]]+?)\]\[[^\]]*?\]'
    result = re.sub(pattern_ref_link, r'[\1]', result)
    
    # Clean up any extra blank lines
    result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)
    
    return result.strip()


# Example usage
if __name__ == "__main__":
    # Test text with various markdown links
    markdown_text = """
    This is a [sample link](https://example.com) in markdown.
    Here's another [very long link text that might need truncation](https://google.com).
    And [another one](https://github.com) with more text.
    
    Some text with [](https://empty-text.com) empty link text.
    
    Reference style: [Reference link][1] and [Another ref][2].
    
    Multiple links close together: [first](url1)[second](url2)[third](url3)
    
    [1]: https://reference1.com
    [2]: https://reference2.com
    """
    
    # print("Original text:")
    # print(markdown_text)
    # print("\n" + "="*50 + "\n")
    
    # # Remove links, keep all text
    # print("Links removed (keep all text):")
    # print(remove_markdown_links(markdown_text))
    # print("\n" + "="*50 + "\n")
    
    # # Remove links, limit text to 10 characters
    # print("Links removed (max 10 chars):")
    # print(remove_markdown_links(markdown_text, max_chars=10))
    # print("\n" + "="*50 + "\n")
    
    # # Advanced version with reference links handling
    # print("Advanced version (max 15 chars):")
    # print(remove_markdown_links_advanced(markdown_text, max_chars=15, placeholder="link"))
    
    print(markdown_content)
    import ipdb; ipdb.set_trace()


