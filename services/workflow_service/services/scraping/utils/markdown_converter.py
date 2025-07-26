import os
import tempfile
import uuid
from typing import Union, Optional

from markitdown import MarkItDown
# from kiwi_app.workflow_app.customer_data_routes import upload_router

md = MarkItDown()


def convert_to_markdown_from_raw_file_content(file_content: Union[bytes, str], file_name: Optional[str] = None) -> str:
    """
    Convert raw file content to Markdown text.
    """
    if file_name is None:
        file_name = f"temp_{uuid.uuid4()}.html"
    filename, ext = os.path.splitext(file_name.lower())
    # assert file_extension in VALID_FILE_EXTENSIONS, f"Unsupported file extension: {file_extension}"
    if isinstance(file_content, str):
        file_content = file_content.encode("utf-8")
    with tempfile.NamedTemporaryFile(delete=True, prefix = filename, suffix=ext) as tmp:  # f"temp_file_{str(uuid.uuid4())}"
        tmp.write(file_content)
        tmp.flush()
        tmp_path = tmp.name
        return convert_to_markdown(tmp_path)

def convert_to_markdown(input_path: str) -> str:
    """
    Convert .pdf/.docx/.pptx/.xlsx/.html/.jpg/.mp3/.zip/... to Markdown,
    or return raw text for .txt/.md files.
    """
    _, ext = os.path.splitext(input_path.lower())

    # Passthrough for plain text or Markdown files
    if ext in (".txt", ".md"):
        with open(input_path, "r", encoding="utf-8") as f:
            return f.read()

    # Universal converter for all other supported formats
    md = MarkItDown(enable_plugins=False)  # disable plugins by default
    result = md.convert(input_path)
    return result.text_content

if __name__ == "__main__":
    test_html = """"""

    resp = convert_to_markdown_from_raw_file_content(test_html, f"temp_{uuid.uuid4()}.html")
