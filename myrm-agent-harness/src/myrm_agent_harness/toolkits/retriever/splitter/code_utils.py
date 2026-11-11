"""Code-related text splitting utilities.

Provides programming language detection, code block protection, and language-aware splitting.

[INPUT]
- langchain_text_splitters (optional `[retrieval]` extra)::Language, RecursiveCharacterTextSplitter

[OUTPUT]
- detect_code_language: Detect programming language from code block or text
- split_large_code_block: Split large code block with a language-aware splitter
- protect_code_blocks: Protect code blocks with placeholders during splitting
- restore_code_blocks: Restore code blocks from placeholders

[POS]
Code-aware splitting utilities for language-aware chunking and code block protection.
"""

import logging
import re

logger = logging.getLogger(__name__)

_RETRIEVAL_INSTALL_HINT = (
    "langchain-text-splitters is required for code-aware splitting. "
    "Install with: pip install 'myrm-agent-harness[retrieval]'"
)


def _get_langchain_splitters():
    try:
        from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
    except ImportError as exc:
        raise ImportError(_RETRIEVAL_INSTALL_HINT) from exc
    return Language, RecursiveCharacterTextSplitter


# Language aliases mapped to langchain Language enum names
LANGUAGE_MAP = {
    "cpp": "cpp",
    "c++": "cpp",
    "c": "c",
    "csharp": "csharp",
    "c#": "csharp",
    "cobol": "cobol",
    "elixir": "elixir",
    "go": "go",
    "golang": "go",
    "haskell": "haskell",
    "html": "html",
    "java": "java",
    "js": "js",
    "javascript": "js",
    "jsx": "js",
    "kotlin": "kotlin",
    "latex": "latex",
    "lua": "lua",
    "markdown": "markdown",
    "md": "markdown",
    "perl": "perl",
    "php": "php",
    "powershell": "powershell",
    "proto": "proto",
    "python": "python",
    "py": "python",
    "rst": "rst",
    "ruby": "ruby",
    "rb": "ruby",
    "rust": "rust",
    "rs": "rust",
    "scala": "scala",
    "sol": "sol",
    "solidity": "sol",
    "swift": "swift",
    "ts": "ts",
    "typescript": "ts",
    "tsx": "ts",
    "visualbasic6": "visualbasic6",
    "vb6": "visualbasic6",
}


def detect_code_language(code: str) -> str | None:
    """Auto-detect the programming language of code (only languages supported by langchain's from_language)

    Args:
        code: Code content

    Returns:
        Detected language name, or None if it cannot be detected

    Note:
        Only languages supported by langchain's RecursiveCharacterTextSplitter.from_language are detected:
        cpp, go, java, kotlin, js, ts, php, proto, python, rst, ruby, rust,
        scala, swift, markdown, latex, html, sol, csharp, cobol, c, lua,
        perl, haskell, elixir, powershell, visualbasic6
    """
    if not code or len(code.strip()) < 10:
        return None

    # Language signature patterns (only languages langchain supports)
    language_patterns = {
        "python": [
            r"\bdef\s+\w+\s*\(",
            r"\bclass\s+\w+\s*:",
            r"\bimport\s+\w+",
            r"\bfrom\s+\w+\s+import",
        ],
        "js": [
            r"\bfunction\s+\w+\s*\(",
            r"\bconst\s+\w+\s*=",
            r"\blet\s+\w+\s*=",
            r"=>\s*{",
            r"<\w+\s+[^>]*>",  # JSX
        ],
        "ts": [
            r"\binterface\s+\w+\s*{",
            r"\btype\s+\w+\s*=",
            r":\s*(string|number|boolean)",
        ],
        "html": [
            r"<!DOCTYPE\s+html>",
            r"<html[^>]*>",
            r"<head>",
            r"<body[^>]*>",
        ],
        "java": [
            r"\bpublic\s+class\s+\w+",
            r"\bprivate\s+\w+\s+\w+",
            r"\bpublic\s+static\s+void\s+main",
        ],
        "go": [
            r"\bfunc\s+\w+\s*\(",
            r"\bpackage\s+\w+",
            r"\btype\s+\w+\s+struct",
        ],
        "rust": [
            r"\bfn\s+\w+\s*\(",
            r"\blet\s+mut\s+",
            r"\bimpl\s+\w+",
        ],
        "ruby": [
            r"\bdef\s+\w+",
            r"\bclass\s+\w+\s*<",
            r"\bend\b",
        ],
        "cpp": [
            r"#include\s+<",
            r"\bclass\s+\w+\s*{",
            r"std::",
        ],
        "csharp": [
            r"\bnamespace\s+\w+",
            r"\bpublic\s+class\s+\w+",
            r"using\s+System",
        ],
        "php": [
            r"<\?php",
            r"\$\w+\s*=",
            r"function\s+\w+\s*\(",
        ],
    }

    # Count the matching patterns of each language
    scores = {}
    for lang, patterns in language_patterns.items():
        score = 0
        for pattern in patterns:
            if re.search(pattern, code, re.MULTILINE):
                score += 1
        if score > 0:
            scores[lang] = score

    if not scores:
        return None

    # Special case: prefer HTML (avoids confusion with JSX)
    if "html" in scores and scores["html"] >= 3:
        detected_lang = "html"
    else:
        # Pick the language with the highest score
        detected_lang = max(scores.items(), key=lambda x: x[1])[0]

    logger.warning(f"Auto-detected code language: {detected_lang} (match score: {scores[detected_lang]})")
    return detected_lang


def split_large_code_block(code_content: str, language: str, max_tokens: int = 2000) -> list[str]:
    """Split a large code block with the language-aware splitter

    Args:
        code_content: Code content (without the ``` fence markers)
        language: Code language
        max_tokens: Maximum token count per fragment

    Returns:
        List of split code fragments
    """
    from myrm_agent_harness.utils.text_utils import get_token_count

    code_tokens = get_token_count(code_content)
    if code_tokens <= max_tokens:
        return [code_content]

    lang_key = LANGUAGE_MAP.get(language.lower())
    if not lang_key:
        logger.warning(f"Unsupported code language: {language}, falling back to line-based splitting")
        return _split_by_lines(code_content, max_tokens)

    try:
        Language, RecursiveCharacterTextSplitter = _get_langchain_splitters()  # noqa: N806  # third-party class names
        splitter = RecursiveCharacterTextSplitter.from_language(
            language=Language[lang_key.upper()],
            chunk_size=max_tokens,
            chunk_overlap=int(max_tokens * 0.1),
        )

        chunks = splitter.split_text(code_content)
        logger.warning(f"Split large {language} code block: {code_tokens} tokens -> {len(chunks)} fragments")
        return chunks

    except Exception as e:
        logger.warning(f"Language-aware split failed: {e!s}; keeping the code block intact")
        return [code_content]


def _split_by_lines(code_content: str, max_tokens: int) -> list[str]:
    """Split code by lines, packing lines into fragments of at most max_tokens."""
    from myrm_agent_harness.utils.text_utils import get_token_count

    lines = code_content.split("\n")
    chunks = []
    current_chunk = []
    current_tokens = 0

    for line in lines:
        line_tokens = get_token_count(line)
        if current_tokens + line_tokens > max_tokens and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_tokens = line_tokens
        else:
            current_chunk.append(line)
            current_tokens += line_tokens

    if current_chunk:
        chunks.append("\n".join(current_chunk))
    return chunks


def protect_code_blocks(text: str, max_chunk_tokens: int = 675) -> tuple[str, dict[str, str]]:
    """Replace markdown fenced code blocks with placeholders so that later splitting cannot cut them

    Args:
        text: Original text
        max_chunk_tokens: Not used; code blocks are always kept whole

    Returns:
        (Processed text, placeholder-to-code-block mapping)
    """
    code_block_pattern = r"```(\w*)\n([\s\S]*?)```"
    code_blocks = {}
    counter = 0

    def replace_code_block(match):
        nonlocal counter
        language = match.group(1) or ""
        code_content = match.group(2)

        # Without a language tag, try auto-detection
        if not language or language in ("text", "txt", ""):
            detected = detect_code_language(code_content)
            if detected:
                language = detected
                logger.warning(f"Code block has no language tag; auto-detected: {language}")
            else:
                language = "text"

        # Code blocks are not pre-split, so they stay whole;
        # oversized ones are handled at the whole-chunk stage
        code_chunks = [code_content]

        if len(code_chunks) == 1:
            # Keep the code block whole (using the corrected language)
            placeholder = f"__CODE_BLOCK_{counter}__"
            code_blocks[placeholder] = f"```{language}\n{code_content}\n```"
            counter += 1
            return placeholder
        else:
            # The code block was split into multiple fragments
            placeholders = []
            for chunk in code_chunks:
                placeholder = f"__CODE_BLOCK_{counter}__"
                code_blocks[placeholder] = f"```{language}\n{chunk}\n```"
                placeholders.append(placeholder)
                counter += 1
            logger.warning(f"Code block split into {len(code_chunks)} fragments")
            return "\n\n".join(placeholders)

    protected_text = re.sub(code_block_pattern, replace_code_block, text)
    return protected_text, code_blocks


def restore_code_blocks(text: str, code_blocks: dict[str, str]) -> str:
    """Restore code blocks from their placeholders

    Args:
        text: Text containing placeholders
        code_blocks: Placeholder-to-code-block mapping

    Returns:
        Text with the code blocks restored
    """
    for placeholder, code_block in code_blocks.items():
        text = text.replace(placeholder, code_block)
    return text
