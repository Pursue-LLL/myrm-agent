"""In-sandbox execution-mode detection source for the unified execution wrapper script.

[INPUT]
- (none)

[OUTPUT]
- ASYNC_MODE_DETECTION_SOURCE: Source text of the helpers the wrapper script runs to decide how a user script is driven: it calls ``asyncio.run`` itself, or it defines ``async def main()`` and calls ``main()`` without driving it.

[POS]
Spliced verbatim into the wrapper script by ``generate_wrapper_script``. The helpers read the user's script as a syntax tree, so a mention of ``asyncio.run`` in a comment or a string never selects a mode. They rely on the template's top-level ``import ast``. A script that matches neither helper is compiled by the wrapper with top-level await allowed, so awaiting at module level needs no detection of its own.
"""

ASYNC_MODE_DETECTION_SOURCE = r'''# ============================================================
# Execution mode detection
# ============================================================

def _collect_async_runners(tree: object) -> set[str]:
    """Collect all callable names that act as asyncio.run (including aliases and imports)."""

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
    return False'''
