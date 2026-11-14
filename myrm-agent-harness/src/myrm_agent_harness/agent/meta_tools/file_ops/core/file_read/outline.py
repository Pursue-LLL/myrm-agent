"""Adaptive structural outline extractor for files.

Extracts top-level class, function, interface, struct signatures, and Markdown headings
from source code or document files. Supports truncated file reads and structure-only reading mode.

[INPUT]
- output: Raw file text, or the text a read shows the model: the numbered (gutter) lines, usually inside a notice
  and tool-output tags that are not part of the file
- path_str: Target file path
- next_offset: 1-indexed line number where extraction starts (1 for full document)

[OUTPUT]
- extract_file_outline: Formatted document structure outline string, or empty string
- extract_truncated_outline: Formatted outline string block for truncated reads, or empty string

[POS]
In-memory zero-dependency outline extraction supporting Python (AST + regex fallback),
TypeScript/JavaScript, Go, Rust, Java, C/C++, C#, and Markdown. The regex scan reads one line at a time, so it lists a
definition whose signature starts on that line: type parameters (`<T>`, `[T]`) and an arrow function's return type
are covered, an arrow function whose parameters continue on the next line is not.
"""

from __future__ import annotations

import ast
import os
import re
import warnings
from dataclasses import dataclass

# Matches line gutter emitted by ResultFormatter (e.g. "     12|def foo():")
_GUTTER_LINE_RE = re.compile(r"^\s*(\d+)\|")

# The AST of a source costs ~150 bytes of memory per character: 0.5 MB takes ~0.1 s and ~75 MB, 7 MB takes seconds and
# over 1 GB. A read of a large generated module must not spike the server like that, so past this size the regex scan
# lists the symbols (in milliseconds) without their ranges.
_AST_MAX_SOURCE_CHARS = 300_000

# Between a definition's name and its parameter list (or initializer) TypeScript writes `<T>`, Go and Python write
# `[T]`. A pattern that expects `name(` or `name =` straight after the name silently drops every generic definition,
# and the model is told the file has no such symbol. The lazy match ends at the first closing bracket that is followed
# by what the pattern needs next, so nested brackets (`<T extends Array<U>>`, `[M ~map[K]V]`) are covered. The bound
# keeps a hostile one-line file (`const a = <>(<>(<>(...`) linear: unbounded, every `>(` is retried against the rest
# of the line and a 120 KB line takes 1.6 s.
_ANGLE_TYPE_PARAMS = r"(?:<.{0,200}?>\s*)?"
_SQUARE_BRACKETS = r"\[.{0,200}?\]"
_SQUARE_TYPE_PARAMS = rf"(?:{_SQUARE_BRACKETS}\s*)?"

# Pre-compiled symbol matching regexes for non-Python or fallback extraction
# Each pattern captures (kind, name) or (name)
_GENERIC_SYMBOL_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "ts_js": [
        re.compile(
            rf"^(?:export\s+(?:default\s+)?)?((?:async\s+)?function)\s+([a-zA-Z0-9_$]+)\s*{_ANGLE_TYPE_PARAMS}\("
        ),
        re.compile(r"^(?:export\s+(?:default\s+)?)?(class)\s+([a-zA-Z0-9_$]+)"),
        re.compile(r"^(?:export\s+)?(interface)\s+([a-zA-Z0-9_$]+)"),
        re.compile(rf"^(?:export\s+)?(type)\s+([a-zA-Z0-9_$]+)\s*{_ANGLE_TYPE_PARAMS}="),
        re.compile(r"^(?:export\s+)?(enum)\s+([a-zA-Z0-9_$]+)"),
        # An arrow function: the variable may carry a type (`: FC<Props>`), the arrow a return type (`): void =>`).
        re.compile(
            rf"^(?:export\s+)?(const)\s+([a-zA-Z0-9_$]+)\s*(?::[^=]*)?=\s*(?:async\s*)?{_ANGLE_TYPE_PARAMS}\([^)]*\)\s*(?::[^=]*)?=>"
        ),
    ],
    "go": [
        re.compile(rf"^(func)\s+(?:\([^)]+\)\s+)?([a-zA-Z0-9_]+)\s*{_SQUARE_TYPE_PARAMS}\("),
        re.compile(rf"^(type)\s+([a-zA-Z0-9_]+)(?:\s+|{_SQUARE_BRACKETS}\s*)(?:struct|interface)"),
    ],
    "rust": [
        re.compile(r"^(?:pub(?:\([^)]+\))?\s+)?((?:async\s+)?fn)\s+([a-zA-Z0-9_]+)"),
        re.compile(r"^(?:pub(?:\([^)]+\))?\s+)?(struct|enum|trait|type)\s+([a-zA-Z0-9_]+)"),
        re.compile(r"^(impl)(?:\s*<[^>]+>)?\s+([a-zA-Z0-9_]+)"),
    ],
    "java_csharp": [
        re.compile(r"^(?:public|protected|private|static|final|abstract|sealed|\s)*(class)\s+([a-zA-Z0-9_]+)"),
        re.compile(r"^(?:public|protected|private|static|final|abstract|\s)*(interface)\s+([a-zA-Z0-9_]+)"),
        re.compile(r"^(?:public|protected|private|static|final|abstract|\s)*(enum)\s+([a-zA-Z0-9_]+)"),
        re.compile(r"^(?:public|protected|private|static|async|\s)+[\w<>\[\],\s]+\s+([a-zA-Z0-9_]+)\s*\([^;]*$"),
    ],
    "c_cpp": [
        re.compile(r"^(class|struct|enum)\s+([a-zA-Z0-9_]+)"),
        re.compile(r"^(?:[\w:*&<>\s]+)\s+([a-zA-Z0-9_]+)\s*\([^;]*\)\s*(?:const)?\s*\{?"),
    ],
    "python_fallback": [
        re.compile(rf"^((?:async\s+)?def)\s+([a-zA-Z0-9_]+)\s*{_SQUARE_TYPE_PARAMS}\("),
        re.compile(r"^(class)\s+([a-zA-Z0-9_]+)"),
    ],
    "markdown": [
        re.compile(r"^(#{1,6})\s+(.+)$"),
    ],
}

_EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "ts_js",
    ".tsx": "ts_js",
    ".js": "ts_js",
    ".jsx": "ts_js",
    ".mjs": "ts_js",
    ".cjs": "ts_js",
    ".go": "go",
    ".rs": "rust",
    ".java": "java_csharp",
    ".cs": "java_csharp",
    ".cpp": "c_cpp",
    ".cc": "c_cpp",
    ".cxx": "c_cpp",
    ".hpp": "c_cpp",
    ".h": "c_cpp",
    ".c": "c_cpp",
    ".md": "markdown",
    ".mdx": "markdown",
}


@dataclass(frozen=True, slots=True)
class OutlineSymbol:
    """Represents an extracted code symbol with line boundaries."""

    name: str
    kind: str
    start_line: int
    end_line: int | None = None

    def format_entry(self) -> str:
        """Format symbol entry with single line or line range."""
        if self.end_line and self.end_line > self.start_line:
            return f"- Line {self.start_line}-{self.end_line}: {self.kind} {self.name}"
        return f"- Line {self.start_line}: {self.kind} {self.name}"


def _strip_gutter_line(line: str) -> tuple[int | None, str]:
    """Strip line number gutter if present and return (line_number, raw_text)."""
    match = _GUTTER_LINE_RE.match(line)
    if match:
        line_num = int(match.group(1))
        raw_text = line[match.end() :]
        return line_num, raw_text
    return None, line


def _clean_path_extension(path_str: str) -> str:
    """Extract clean file extension from path string which may include line ranges or URI schemes."""
    clean_path = path_str.split(":")[0] if ":" in path_str else path_str
    clean_path = clean_path.split("?")[0]
    return os.path.splitext(clean_path)[1].lower()


def _numbered_lines(lines: list[str]) -> list[tuple[int, str]]:
    """The lines of the file with their file line numbers.

    A read shows the model the numbered lines inside a notice and tool-output tags. Those lines are not the file:
    parsed they break the Python AST, listed they pass for headings, and they shift every position counted from the
    top of the text. So once any line carries a gutter, only the numbered lines count. Text without a gutter is raw
    and numbered by position.
    """
    stripped = [_strip_gutter_line(line) for line in lines]
    if any(number is not None for number, _ in stripped):
        return [(number, text) for number, text in stripped if number is not None]
    return [(position, text) for position, (_, text) in enumerate(stripped, start=1)]


def _extract_python_ast_symbols(numbered: list[tuple[int, str]], start_line_threshold: int) -> list[OutlineSymbol]:
    """Extract top-level and class-level Python symbols, with their line ranges, using AST."""
    numbers = [number for number, _ in numbered]
    # A lone CR is a line break to the parser and would shift every number after it.
    source = "\n".join(text for _, text in numbered).replace("\r", " ")
    if len(source) > _AST_MAX_SOURCE_CHARS:
        return []
    # Source the parser cannot take is not a failed read: a lone surrogate (ValueError) or a source too complex for its
    # stack (MemoryError, RecursionError) leaves the regex scan. What the file's author wrote, such as an escape
    # Python warns about, is not for the server's log, and the parser repeats the warning on every read.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(source)
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return []

    symbols: list[OutlineSymbol] = []

    def add(node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> None:
        start_line = numbers[node.lineno - 1]
        if start_line < start_line_threshold:
            return
        if isinstance(node, ast.ClassDef):
            kind = "class"
        else:
            kind = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        end_line = numbers[node.end_lineno - 1] if node.end_lineno else None
        symbols.append(OutlineSymbol(name=name, kind=kind, start_line=start_line, end_line=end_line))

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            add(node, node.name)
            for subnode in node.body:
                if isinstance(subnode, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add(subnode, f"{node.name}.{subnode.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add(node, node.name)

    return symbols


def _extract_regex_symbols(
    numbered: list[tuple[int, str]],
    language_key: str,
    start_line_threshold: int,
) -> list[OutlineSymbol]:
    """Extract code symbols using pre-compiled regex patterns."""
    patterns = _GENERIC_SYMBOL_PATTERNS.get(language_key, [])
    if not patterns:
        return []

    symbols: list[OutlineSymbol] = []
    in_code_block = False
    in_frontmatter = False

    for line_num, raw_text in numbered:
        if line_num < start_line_threshold:
            continue

        stripped_code = raw_text.strip()
        if not stripped_code:
            continue
        if language_key == "markdown":
            # Handle YAML frontmatter at document start
            if line_num == 1 and stripped_code == "---":
                in_frontmatter = True
                continue
            if in_frontmatter:
                if stripped_code == "---":
                    in_frontmatter = False
                continue

            if stripped_code.startswith(("```", "~~~")):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue
            # CommonMark indented code blocks (4+ leading spaces/tabs) are not headings.
            if len(raw_text) - len(raw_text.lstrip(" \t")) >= 4:
                continue
        elif stripped_code.startswith(("//", "/*", "*", "#", "'''", '"""')):
            continue
        for pattern in patterns:
            match = pattern.match(stripped_code)
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    kind_name, symbol_name = groups[0], groups[1]
                else:
                    kind_name, symbol_name = "def", groups[0]
                symbols.append(
                    OutlineSymbol(
                        name=symbol_name,
                        kind=kind_name,
                        start_line=line_num,
                    )
                )
                break

    return symbols


def _extract_symbols(output: str, language: str, start_line_threshold: int) -> list[OutlineSymbol]:
    """The symbols of ``output`` from line ``start_line_threshold`` on: Python by AST, else (or when it fails) by regex."""
    numbered = _numbered_lines(output.split("\n"))
    if language == "python":
        return _extract_python_ast_symbols(numbered, start_line_threshold) or _extract_regex_symbols(
            numbered, "python_fallback", start_line_threshold
        )
    return _extract_regex_symbols(numbered, language, start_line_threshold)


def extract_truncated_outline(
    output: str,
    path_str: str,
    next_offset: int,
    max_symbols: int = 20,
) -> str:
    """Extract structural outline for omitted lines in a truncated source code file.

    Args:
        output: Full raw or gutter-formatted text before truncation.
        path_str: Path to determine language syntax.
        next_offset: 1-indexed line number of first truncated line.
        max_symbols: Maximum outline items before applying truncation fuse.

    Returns:
        Formatted outline text block or empty string if no relevant symbols found.
    """
    ext = _clean_path_extension(path_str)
    language = _EXT_TO_LANGUAGE.get(ext)
    if not language:
        return ""

    symbols = _extract_symbols(output, language, next_offset)
    if not symbols:
        return ""

    total_symbols = len(symbols)
    displayed_symbols = symbols[:max_symbols]

    outline_lines: list[str] = [f"[OUTLINE OF REMAINING SYMBOLS (from line {next_offset})]:"]
    for sym in displayed_symbols:
        outline_lines.append(f"  {sym.format_entry()}")

    if total_symbols > max_symbols:
        omitted = total_symbols - max_symbols
        outline_lines.append(f"  ... and {omitted:,} more symbols.")

    return "\n".join(outline_lines)


def extract_file_outline(
    output: str,
    path_str: str,
    max_symbols: int = 100,
) -> str:
    """Extract structural outline with line numbers for a complete source or markdown file.

    Args:
        output: Full raw or gutter-formatted file text.
        path_str: Path to determine language syntax.
        max_symbols: Maximum outline items before applying truncation fuse.

    Returns:
        Formatted outline text block or empty string.
    """
    ext = _clean_path_extension(path_str)
    language = _EXT_TO_LANGUAGE.get(ext)
    if not language:
        return ""

    symbols = _extract_symbols(output, language, 1)
    if not symbols:
        return ""

    total_symbols = len(symbols)
    displayed_symbols = symbols[:max_symbols]

    outline_lines: list[str] = [f"[DOCUMENT STRUCTURE OUTLINE: {os.path.basename(path_str)}]:"]
    for sym in displayed_symbols:
        outline_lines.append(f"  {sym.format_entry()}")

    if total_symbols > max_symbols:
        omitted = total_symbols - max_symbols
        outline_lines.append(f"  ... and {omitted:,} more symbols.")

    return "\n".join(outline_lines)
