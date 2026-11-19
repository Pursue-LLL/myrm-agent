"""Bash code execution tool description (prompt visible to the LLM).

Kept apart from ``bash_code_execute_tool.py`` so the tool factory stays focused on wiring.

[INPUT]
- utils.locale::is_chinese (POS: BCP-47 Chinese detection for description locale)

[OUTPUT]
- DEFAULT_BASH_TOOL_DESCRIPTION_LOCALE: Default English locale constant ("en")
- TOOL_DESCRIPTION_EN: English tool description SSOT
- TOOL_DESCRIPTION_ZH: Chinese tool description SSOT
- resolve_bash_code_execute_tool_description(): Locale-aware resolver

[POS]
Prompt content displayed to the LLM. Defines the contract for calling
``bash_code_execute_tool``: the four capabilities (shell with the rule for interactive programs, Python source,
combining steps with the unknown-return-shape rule, the skill/MCP entrypoint), native-tool routing, what a call
leaves for the next one, the two output markers with failure handling, and the progress markers of background
jobs. Parameter limits live in the ``BashInput`` field texts, and how to manage a background job (including a
job waiting for input) lives in the ``bash_process_tool`` description, so neither is repeated here.
"""

from __future__ import annotations

from typing import Final

from myrm_agent_harness.utils.locale import is_chinese

DEFAULT_BASH_TOOL_DESCRIPTION_LOCALE: Final[str] = "en"

TOOL_DESCRIPTION_ZH: Final[str] = """
执行 Shell 命令或 Python 代码。

## 能力

1. **Shell**:git、构建测试、包管理、curl、mv/cp/rm。前台命令里的交互提示无法应答:请使用非交互参数(`-y`、`--yes`),或用 `run_in_background` 启动交互式程序,再经 `bash_process_tool` 应答。
2. **Python**:把原生 Python 源码直接作为 `command` 传入(支持多行)。
3. **合并步骤**:相关工作放进同一次调用(Python 的 `if`/`while`/`try`、`asyncio.gather`,或 `&&` / `|`)。**返回结构不明确不是拆分的理由**:在同一块打印真实值 `[OBSERVATION]` 后继续,且**严禁**索引既没有文档、也没打印过的字段。只有后续参数必须看到结果才能构造时才拆分。
4. **Skill/MCP 函数**是 async:每次调用都要 `await`,并遵循该技能的调用约定。入口写法:

```python
import asyncio

async def main():
    first, second = await asyncio.gather(call_a(), call_b())
    print(f"[OBSERVATION] first={first}, second={second}")
    result = await call_c(x=first, y=second)  # only if constructible
    print(f"[RESULT] {result}")

asyncio.run(main())
```

## 优先使用专用工具

- 读/写/编辑:**必须**用 `file_read_tool` / `file_write_tool` / `file_edit_tool`,**不要** echo/cat/sed/awk/tee/perl。
- 找文件/搜内容/列目录:**必须**用 `glob_tool` / `grep_tool`,**不要** bash `find/grep/ls` 递归扫描。

`bash_code_execute_tool` 适用于:系统/运行时操作(mv/cp/rm、包管理、构建测试、git、curl)、Python/脚本执行、后台长任务。

## 状态

- **每次调用都当作全新开始**:Python 变量与 import 不会带到下一次调用,shell 的 `cd` / `export` / 函数也不保证保留。把步骤合并进同一次调用(`cd 目录 && 命令`),或把中间数据写到文件。

## 输出与错误

- Python 只允许打印两类行:`print(f"[OBSERVATION] {变量}")` 查看未知值;`print(f"[RESULT] {结果}")` 输出最终结果。内容只放下一步需要的部分(大数据只给摘要,不要 dump 原始对象)。不要其他 print,不写解释性注释。
- 失败时先读 stderr 定位根因再修复;**严禁**原样重跑同一命令。

## 后台任务

后台脚本可以输出 `echo 'MYRM_PROGRESS {"percent": 42, "message": "Compiling"}'`(或 `{"current": 3, "total": 10}`),界面进度条会自动更新,无需 LLM 参与。检查点用 `MYRM_CHECKPOINT {"message": "..."}`。
""".strip()

TOOL_DESCRIPTION_EN: Final[str] = """
Run a shell command or Python code.

## Capabilities
1. **Shell**: git, build/test, package install, curl, mv/cp/rm. An interactive prompt in a foreground command cannot be answered: pass non-interactive flags (`-y`, `--yes`), or start an interactive program with `run_in_background` and answer it through `bash_process_tool`.
2. **Python**: pass raw Python source as `command` (multi-line is fine).
3. **Combine steps**: do related work in ONE call (Python `if`/`while`/`try`, `asyncio.gather`, or `&&` / `|`). **An unknown return shape is NOT a reason to split**: print the real value as `[OBSERVATION]` and continue in the same block, and **NEVER** index a field you have not seen documented or printed. Split only when later arguments cannot be built without seeing the result.
4. **Skill/MCP functions** are async: `await` every call and follow the skill's calling rules. Entrypoint:

```python
import asyncio

async def main():
    first, second = await asyncio.gather(call_a(), call_b())
    print(f"[OBSERVATION] first={first}, second={second}")
    result = await call_c(x=first, y=second)  # only if constructible
    print(f"[RESULT] {result}")

asyncio.run(main())
```

## Prefer Dedicated Tools
- Read / Write / Edit: **MUST** use `file_read_tool` / `file_write_tool` / `file_edit_tool`. Do **NOT** use echo/cat/sed/awk/tee/perl.
- Find files / search content / list dirs: **MUST** use `glob_tool` / `grep_tool`. Do **NOT** use bash `find/grep/ls` recursively.

`bash_code_execute_tool` is for: system/runtime operations (mv/cp/rm, build, test, git, curl), Python/script execution, and background tasks.

## State
- **Treat every call as a fresh start**: Python variables and imports do not carry over, and shell `cd` / `export` / functions are not guaranteed to carry over either. Combine steps in one call (`cd dir && command`), or write intermediate data to a file.

## Output and Errors
- In Python, print only two kinds of lines: `print(f"[OBSERVATION] {variable}")` inspects an unknown value; `print(f"[RESULT] {result}")` gives the final output. Put in them only what the next step needs (summaries of large data, never raw dumps). No other prints, no explanatory comments.
- On failure, read stderr and fix the cause; never rerun the same command unchanged.

## Background Tasks
Background scripts can emit `echo 'MYRM_PROGRESS {"percent": 42, "message": "Compiling"}'` (or `{"current": 3, "total": 10}`) to automatically update UI progress bars without LLM turns. Use `MYRM_CHECKPOINT {"message": "..."}` for checkpoints.
""".strip()


def resolve_bash_code_execute_tool_description(
    locale: str | None = DEFAULT_BASH_TOOL_DESCRIPTION_LOCALE,
) -> str:
    """Resolve LLM-facing bash_code_execute_tool description based on locale.

    Defaults to English when locale is omitted or non-Chinese.
    """
    if is_chinese(locale):
        return TOOL_DESCRIPTION_ZH
    return TOOL_DESCRIPTION_EN


__all__ = [
    "DEFAULT_BASH_TOOL_DESCRIPTION_LOCALE",
    "TOOL_DESCRIPTION_EN",
    "TOOL_DESCRIPTION_ZH",
    "resolve_bash_code_execute_tool_description",
]
