"""Special block detection module.

Identifies and extracts special structures in text (code blocks, tables, lists).

[INPUT]
- (none - standard library regex)

[OUTPUT]
- SpecialBlockDetector: Detects code, table, and list blocks for boundary protection

[POS]
Provides SpecialBlockDetector for markdown structure extraction.
"""

import re


class SpecialBlockDetector:
    """Finds the Markdown structures a text splitter must not cut through.

    - **Code blocks**: a fenced block, both fences included; a cut inside it breaks the code.
    - **Tables**: a header row, a separator row (``|---|---|``) and the data rows after it; they only make
      sense together.
    - **Lists**: items starting with ``-``, ``*``, ``+`` or ``1.``; nesting is recognised by indentation, and
      an item stays together with its sub-items.

    ``start`` and ``end`` of every structure are character offsets into the scanned text.

    Example::

        detector = SpecialBlockDetector()
        blocks = detector.extract_special_structures(text)
        # [{"type": "code", "start": 20, "end": 50, "language": "python", "content": "<fenced code>"},
        #  {"type": "table", "start": 52, "end": 80, "content": "<table text>"}]
    """

    def __init__(self):
        # Pre-compiled regex patterns
        self._list_item_pattern = re.compile(r"^(\s*)([-*+]|\d+\.)\s+")
        self._code_fence_pattern = re.compile(r"```(\w*)\n([\s\S]*?)```", re.MULTILINE)
        self._table_separator_pattern = re.compile(r"^[\s|:-]+\|[\s|:-]+$")

    def extract_special_structures(self, text: str) -> list[dict]:
        """Extract every code block, table and list from the text.

        Args:
            text: Text to scan.

        Returns:
            Structure descriptors (``type``, ``start``, ``end``, ``content``, plus ``language`` for code),
            sorted by start offset.
        """
        special_structures = []

        # Code blocks
        for m in self._code_fence_pattern.finditer(text):
            special_structures.append(
                {
                    "type": "code",
                    "start": m.start(),
                    "end": m.end(),
                    "language": m.group(1) or "",
                    "content": m.group(2),
                }
            )

        # Tables
        table_structures = self._extract_tables(text)
        special_structures.extend(table_structures)

        # Lists
        list_structures = self._extract_lists(text)
        special_structures.extend(list_structures)

        special_structures.sort(key=lambda x: x["start"])
        return special_structures

    def _extract_tables(self, text: str) -> list[dict]:
        """Extract tables.

        A table is a header row, a separator row (``|:-:|``) and the data rows after it.

        Args:
            text: Text to scan.

        Returns:
            Table descriptors.
        """
        table_structures = []
        lines = text.split("\n")
        i = 0

        while i < len(lines):
            if i + 1 < len(lines):
                current_line = lines[i]
                next_line = lines[i + 1]

                if "|" in current_line and self._table_separator_pattern.match(next_line):
                    table_start_line_idx = i
                    table_lines = [current_line, next_line]
                    j = i + 2

                    # Collect the data rows that follow
                    while j < len(lines) and "|" in lines[j] and lines[j].strip():
                        table_lines.append(lines[j])
                        j += 1

                    # Character offset of the table start
                    chars_before = sum(len(lines[k]) + 1 for k in range(table_start_line_idx))
                    table_content = "\n".join(table_lines)

                    table_structures.append(
                        {
                            "type": "table",
                            "start": chars_before,
                            "end": chars_before + len(table_content),
                            "content": table_content,
                        }
                    )

                    i = j
                    continue
            i += 1

        return table_structures

    def _extract_lists(self, text: str) -> list[dict]:
        """Extract lists, including nested ones.

        A list starts at an item line (``1. ``, ``- ``, ``* `` or ``+ ``). It continues over items indented at
        least as far as the first one (nested items), over a blank line followed by another item, and over
        lines indented at least two spaces deeper than the first item (item continuations). A less-indented
        item or any other line ends it.

        Args:
            text: Text to scan.

        Returns:
            List descriptors.
        """
        list_structures = []
        lines = text.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i]
            match = self._list_item_pattern.match(line)

            if match:
                # Start of the list
                list_start_idx = i
                list_lines = []
                base_indent = len(match.group(1))  # indent of the first item

                # Collect the whole list, nested items and continuation lines included
                j = i
                while j < len(lines):
                    current_line = lines[j]
                    current_match = self._list_item_pattern.match(current_line)

                    if not current_line.strip():
                        # Blank line: the list may end here or continue after it
                        if j + 1 < len(lines):
                            next_line = lines[j + 1]
                            next_match = self._list_item_pattern.match(next_line)
                            if next_match:
                                # The next line is still a list item, so keep the blank line
                                list_lines.append(current_line)
                                j += 1
                                continue
                        # Otherwise the list ends
                        break

                    if current_match:
                        # List item
                        current_indent = len(current_match.group(1))
                        if current_indent < base_indent:
                            # Indent decreased: back to the parent list, or the list ends
                            break
                        # Sibling or nested item
                        list_lines.append(current_line)
                    else:
                        # Not a list item
                        # Continuation of the previous item (indented)
                        if current_line.startswith(" " * (base_indent + 2)):
                            # Indented continuation belongs to the item
                            list_lines.append(current_line)
                        else:
                            # End of the list
                            break

                    j += 1

                if list_lines:
                    # Character offset of the list start
                    chars_before = sum(len(lines[k]) + 1 for k in range(list_start_idx))
                    list_content = "\n".join(list_lines)

                    list_structures.append(
                        {
                            "type": "list",
                            "start": chars_before,
                            "end": chars_before + len(list_content),
                            "content": list_content,
                        }
                    )

                    i = j
                    continue

            i += 1

        return list_structures

    def is_table_separator_line(self, line: str) -> bool:
        """Whether the line is a table separator row."""
        return bool(self._table_separator_pattern.match(line.strip()))

    def is_list_item_line(self, line: str) -> bool:
        """Whether the line is a list item."""
        return bool(self._list_item_pattern.match(line))

    def get_list_item_indent(self, line: str) -> int:
        """Indent width of a list item line, or -1 when the line is not a list item."""
        match = self._list_item_pattern.match(line)
        return len(match.group(1)) if match else -1
