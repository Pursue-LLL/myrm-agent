"""End-to-end tests: a directory-level grep never returns the lines of a sensitive file, once per search tier.

Reading ``.env`` or a private key by name goes through an approval; a search that walks into its directory
would hand the same lines to the model without one.

Covers:
- Sensitive files are withheld from a directory search while ordinary hidden files are searched
- A ``file_pattern`` that names a sensitive file does not bypass the rule
- Withheld matches do not use up the result cap
- Naming the sensitive file as the search path still searches it
"""

from __future__ import annotations

from pathlib import Path

from tests.agent.meta_tools.file_search.search_probe import SearchRunner, hit_files, write_tree

SENSITIVE_TREE = {
    ".env": "API_KEY=needle\n",
    ".aws/credentials": "aws_secret_access_key = needle\n",
    ".ssh/id_ed25519": "needle\n",
    "certs/server.pem": "needle\n",
}
# Hidden, yet nothing to protect: still searched.
VISIBLE_TREE = {"src/app.py": "needle = 1\n", ".github/workflows/ci.yml": "run: needle\n"}


class TestDirectorySearch:
    async def test_sensitive_files_are_withheld_and_ordinary_hidden_files_are_searched(
        self, plain_dir: Path, run_grep: SearchRunner
    ) -> None:
        write_tree(plain_dir, SENSITIVE_TREE | VISIBLE_TREE)

        output = await run_grep(plain_dir, "needle")

        assert hit_files(output, set(SENSITIVE_TREE) | set(VISIBLE_TREE)) == set(VISIBLE_TREE)

    async def test_file_pattern_naming_a_sensitive_file_does_not_bypass_the_rule(
        self, plain_dir: Path, run_grep: SearchRunner
    ) -> None:
        write_tree(plain_dir, SENSITIVE_TREE | VISIBLE_TREE)

        output = await run_grep(plain_dir, "needle", file_pattern=".env")

        assert hit_files(output, set(SENSITIVE_TREE)) == set()

    async def test_withheld_matches_do_not_use_up_the_result_cap(self, plain_dir: Path, run_grep: SearchRunner) -> None:
        write_tree(plain_dir, {".env": "needle\n" * 5, "src/a.py": "needle\n", "src/b.py": "needle\n"})

        output = await run_grep(plain_dir, "needle", max_results=2)

        assert hit_files(output, {"src/a.py", "src/b.py", ".env"}) == {"src/a.py", "src/b.py"}


class TestNamedFile:
    async def test_naming_the_sensitive_file_as_the_path_still_searches_it(
        self, plain_dir: Path, run_grep: SearchRunner
    ) -> None:
        write_tree(plain_dir, SENSITIVE_TREE)

        output = await run_grep(plain_dir, "needle", path=".env")

        assert "Found 1 match(es)" in output
