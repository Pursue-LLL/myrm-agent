"""Which commands the bash tool runs in Python and which in a shell, on a hand-labelled set of commands.

The route is decided from the syntax tree, never from line counts or keywords in the text: a shell command that
mentions ``await`` or ``import`` in a string stays shell, and a one-line ``print(1)`` is Python. The set covers the
shell words that also parse as Python, everyday shell, PowerShell, Python of every statement kind, Python that does
not parse, and three commands whose route is wrong by construction (``DOCUMENTED_LIMITS``). It is the specification
of the router: a change that moves any row has to say why.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.code_execution.code_detector import runs_as_python


def _route(command: str) -> str:
    """The route the executor takes: it strips the text and unwraps one Markdown fence first."""
    return "python" if runs_as_python(command) else "shell"


# Valid Python expressions, yet nothing in them is something a shell line cannot be.
SHELL_WORDS_THAT_PARSE_AS_PYTHON: list[tuple[str, str]] = [
    ("ls", "bare word"),
    ("pwd", "bare word"),
    ("ls -la", "BinOp"),
    ("ls -l | head", "BinOp |"),
    ("ls | wc -l", "BinOp"),
    ("df -h", "BinOp"),
    ("true", "bare word"),
    ("FOO=bar", "assign name"),
    ('X="a b"', "assign const"),
    ("OUT=result.txt", "assign attribute"),
    ("FLAGS=-la", "assign unary minus"),
    ("RATIO=3/4", "assign BinOp"),
    ("LIST=[1,2]", "assign list"),
    ("# list files\nls -la", "comment + BinOp"),
    ("uname -a", "BinOp"),
    ("echo", "bare word"),
    ("whoami", "bare word"),
    ("pwd\nls -la", "two bare statements"),
]

ORDINARY_SHELL: list[tuple[str, str]] = [
    ("echo hello", ""),
    ("cat app.log | grep ERROR | wc -l", ""),
    ('grep -rn "await" src/', "word await in a string"),
    ('grep -n "async for" app.py', "async for in a string"),
    ('grep -rn "import os" .', "import in a string"),
    ("for i in 1 2 3; do echo $i; done", ""),
    ("for f in *.py\ndo\n  wc -l $f\ndone", ""),
    ("if [ -f app.py ]; then echo yes; fi", ""),
    ("while read l; do echo $l; done < app.log", ""),
    ("cat > config.ini <<'EOF'\n[server]\nport=8080\nEOF", "heredoc to cat"),
    ("python3 script.py", ""),
    ("python -m pytest -q", ""),
    ("pip install requests", ""),
    ("cd proj && make test", ""),
    ("git status && git diff --stat", ""),
    ("curl -s http://localhost:8080/hello.txt", ""),
    ("awk '{print $1}' app.log | sort | uniq -c", ""),
    ("sed -n '7p' notes.txt", ""),
    ("f() { echo hi; }\nf", "function def"),
    ("export MODE=fast && echo $MODE", ""),
    ("echo \"print('hello')\"", "python text in a shell string"),
    ("printf 'import os\\nprint(1)\\n' > t.py", ""),
    ("which python3", ""),
    ("time ls", ""),
    ("test -f app.py && echo ok", ""),
    ("[ -d proj ] && ls proj", ""),
    ("tar -czf out.tgz proj/", ""),
    ("find . -name '*.py' -print0 | xargs -0 wc -l", ""),
    ("docker build -t app .", ""),
    ("npm test", ""),
    ("make", ""),
    ("sleep 5", ""),
    ("echo $((1+2))", ""),
    ("(cd proj && ls)", ""),
    ("head -n 5 file", ""),
    ("date +%s", ""),
    ("ps aux | grep python", ""),
    ("echo a | tr a-z A-Z", ""),
    ("import -window root shot.png", "ImageMagick with flags"),
]

POWERSHELL: list[tuple[str, str]] = [
    ("Get-ChildItem -Recurse | Where-Object { $_.Length -gt 1MB }", "PowerShell"),
    ('Write-Host "hi"', "PowerShell"),
    ('$env:FOO = "bar"', "PowerShell"),
    ("dir", "PowerShell"),
    ("Get-Date", "PowerShell BinOp"),
    ('Write-Host("hi")', "PowerShell, parses as BinOp(Name - Call)"),
]

PYTHON_BY_CONSTRUCTION: list[tuple[str, str]] = [
    ("resp = requests.post(url, json=payload)", "assignment from a call, nothing else"),
    ('print("hello")', ""),
    ("print(1+1)", ""),
    ("import os\nprint(os.listdir('.'))", ""),
    ("import sys\nx_state = 41\nprint('set', x_state)", ""),
    ("x_state = 41\nprint('set', x_state)", ""),
    ("d = {'a': 1}\nprint(d)", ""),
    ("def f(x):\n    return x*2\nprint(f(3))", ""),
    ("class A:\n    pass\nprint(A())", ""),
    ("for i in range(3):\n    print(i)", ""),
    ("with open('a.txt') as f:\n    print(f.read())", ""),
    ("try:\n    1/0\nexcept ZeroDivisionError:\n    print('z')", ""),
    ("if True:\n    print(1)", ""),
    ("x = [i*i for i in range(5)]\nprint(x)", ""),
    ('print(f"[RESULT] {1+2}")', ""),
    ("import asyncio\nasync def main():\n    print(1)\nasyncio.run(main())", ""),
    ("result = await call_a()\nprint(result)", "top-level await"),
    ("a, b = await asyncio.gather(call_a(), call_b())\nprint(a, b)", "top-level await"),
    ("import json; print(json.dumps({}))", "semicolon"),
    ("df = pd.read_csv('a.csv')\nprint(df.head())", ""),
    ("df.groupby('region').sum()", "call statement"),
    ("os.system('ls')", "call statement"),
    ("x: int = 5\nprint(x)", ""),
    ("@decorator\ndef f(): pass", ""),
    ("from collections import Counter\nprint(Counter('aab'))", ""),
    ("import os", "bare import"),
    ("data = json.loads(open('orders.json').read())\nprint(len(data))", ""),
    ("match x:\n    case 1:\n        print(1)", ""),
    ("print('a')\r\nprint('b')\r\n", "CRLF"),
    ('print("你好")', "unicode"),
    ("# compute\nimport statistics\nprint(statistics.mean([1,2,3]))", ""),
    ("async def main():\n    pass\nasyncio.run(main())", ""),
    (
        'from skills.mcp_kubernetes_skill import list_pods\nimport asyncio\nasync def main():\n    r = await list_pods()\n    print(f"[RESULT] {r}")\nasyncio.run(main())',
        "skill PTC",
    ),
    ('print("""multi\nline""")', ""),
    ("s = '''\nhello\n'''\nprint(s)", ""),
    ("assert 1 == 1", ""),
    ("x = r'\\d+'\nprint(x)", "invalid-escape SyntaxWarning source"),
]

# Text that opens like Python: the interpreter's SyntaxError tells the model more than a shell's "command not found".
PYTHON_THAT_DOES_NOT_PARSE: list[tuple[str, str]] = [
    ("import os\nprint(os.listdir('.')", "typo, starts with keyword"),
    (
        "from skills.mcp_kubernetes_skill import list_pods, describe_pod if False else c",
        "typo import, starts with keyword",
    ),
]

# Routes that are wrong by construction, pinned as they are so a change to them is deliberate.
# ``DOCUMENTED_LIMITS[i]`` is (command, the route it takes, why that is wrong).
DOCUMENTED_LIMITS: list[tuple[str, str, str]] = [
    (
        "x = 41\nprint('set', x_state",
        "shell",
        "Python that does not parse and does not open with import, from, def or class: the shell reports the error",
    ),
    ('echo("hi")', "python", "valid PowerShell call syntax, but it parses as a Python call statement"),
    ("import screenshot.png", "python", "an ImageMagick `import file` command, but it parses as a Python import"),
]


@pytest.mark.parametrize(("command", "note"), SHELL_WORDS_THAT_PARSE_AS_PYTHON + ORDINARY_SHELL + POWERSHELL)
def test_a_shell_command_runs_in_a_shell(command: str, note: str) -> None:
    assert _route(command) == "shell", note


@pytest.mark.parametrize(("command", "note"), PYTHON_BY_CONSTRUCTION + PYTHON_THAT_DOES_NOT_PARSE)
def test_python_runs_in_the_wrapper(command: str, note: str) -> None:
    assert _route(command) == "python", note


@pytest.mark.parametrize(("command", "route", "reason"), DOCUMENTED_LIMITS)
def test_a_documented_limit_keeps_its_route(command: str, route: str, reason: str) -> None:
    assert _route(command) == route, reason
