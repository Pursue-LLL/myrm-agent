"""In-sandbox execution-mode detection source for the unified execution wrapper script.

[INPUT]
- (none)

[OUTPUT]
- ASYNC_MODE_DETECTION_SOURCE: Source text of the helpers the wrapper script runs to decide how a user script is driven: it calls ``asyncio.run`` itself, it defines ``async def main()`` and calls ``main()`` without driving it, or it uses top-level await.

[POS]
Spliced verbatim into the wrapper script by ``generate_wrapper_script``. The helpers read the user's script as a syntax tree, so a mention of ``asyncio.run`` in a comment or a string never selects a mode.
"""

ASYNC_MODE_DETECTION_SOURCE = r'''# ============================================================
# Execution mode detection
# ============================================================

def _collect_async_runners(tree: object) -> set[str]:
    """Collect all callable names that act as asyncio.run (including aliases and imports)."""
    import ast

    runners = {"asyncio.run"}
    if not isinstance(tree, ast.AST):
        return runners

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "asyncio":
            for alias in node.names:
                if alias.name == "run":
                    runners.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "asyncio" and alias.asname:
                    runners.add(f"{alias.asname}.run")
    return runners


def _has_asyncio_run(code: str) -> bool:
    """Check if code contains a real asyncio.run() Call node (or alias) via AST."""
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False

    runners = _collect_async_runners(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "run":
                if isinstance(func.value, ast.Name):
                    call_name = f"{func.value.id}.run"
                    if call_name in runners:
                        return True
            elif isinstance(func, ast.Name):
                if func.id in runners:
                    return True
    return False


def _has_async_main_call(code: str) -> bool:
    """Check if code defines an async main() and invokes main() as a top-level statement or inside if __name__ == '__main__': block without await/asyncio.run."""
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False

    has_async_main_def = False
    for stmt in tree.body:
        if isinstance(stmt, ast.AsyncFunctionDef) and stmt.name == "main":
            has_async_main_def = True
            break

    if not has_async_main_def:
        return False

    runners = _collect_async_runners(tree)

    class _MainCallDetector(ast.NodeVisitor):
        def __init__(self):
            self.calls_main_unawaited = False

        def visit_FunctionDef(self, node):
            pass

        def visit_AsyncFunctionDef(self, node):
            pass

        def visit_ClassDef(self, node):
            pass

        def visit_Await(self, node):
            # Awaited calls (e.g. await main() or res = await main()) are properly scheduled
            pass

        def visit_Call(self, node):
            # Skip runners that take care of scheduling coroutines
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in (
                "run",
                "create_task",
                "run_until_complete",
            ):
                return
            if isinstance(func, ast.Name) and func.id in runners:
                return
            if isinstance(func, ast.Name) and func.id == "main":
                self.calls_main_unawaited = True
            self.generic_visit(node)

    detector = _MainCallDetector()
    for stmt in tree.body:
        detector.visit(stmt)
        if detector.calls_main_unawaited:
            return True
    return False


def _has_top_level_await(code: str) -> bool:
    """Check if code contains top-level await (await/async for/async with outside any function)."""
    import ast

    class _TopLevelAsyncVisitor(ast.NodeVisitor):
        def __init__(self):
            self.has_top_level = False

        def visit_FunctionDef(self, node):
            pass

        def visit_AsyncFunctionDef(self, node):
            pass

        def visit_ClassDef(self, node):
            pass

        def visit_Await(self, node):
            self.has_top_level = True

        def visit_AsyncFor(self, node):
            self.has_top_level = True

        def visit_AsyncWith(self, node):
            self.has_top_level = True

    try:
        tree = ast.parse(code)
    except SyntaxError:
        has_await = bool(re.search(r"\\bawait\\b", code))
        return has_await and not _has_asyncio_run(code)

    visitor = _TopLevelAsyncVisitor()
    for stmt in tree.body:
        visitor.visit(stmt)
        if visitor.has_top_level:
            return True
    return False


def _wrap_top_level_async_user_code(user_code: str) -> str:
    """Wrap code with an async function while keeping future imports and headers at file top."""
    import textwrap

    header_lines = []
    body_lines = []
    in_header = True
    for line in user_code.splitlines():
        stripped = line.strip()
        if in_header:
            if not stripped or stripped.startswith("#") or stripped.startswith("from __future__ import"):
                header_lines.append(line)
                continue
            in_header = False
        body_lines.append(line)

    header_part = chr(10).join(header_lines)
    body_part = textwrap.indent(chr(10).join(body_lines), "    ")
    return f"{header_part}\nasync def __user_code__():\n{body_part}\n"'''
