"""Extract plain text from LangChain / provider message content."""
from typing import Any, List


def extract_text_content(content: Any) -> str:
    """Normalize AIMessage.content (str, list of blocks, or dict) to a string."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                if block.strip():
                    parts.append(block.strip())
            elif isinstance(block, dict):
                text = block.get("text") or block.get("content")
                if text:
                    parts.append(str(text).strip())
        return "\n".join(parts).strip()
    if isinstance(content, dict):
        text = content.get("text") or content.get("content")
        return str(text).strip() if text else ""
    return str(content).strip()
