"""SkillAgent tool building logic — meta-tools, todo progress, wiki tools.

[INPUT]
- meta_tools::get_meta_tools (POS: Meta-tools factory)
- meta_tools.skills.manage::create_skill_manage_tool (POS: skill_manage_tool built from the write backend)
- tool_management::ToolRegistry (POS: Tool registration and resolution)
- agent.meta_tools.progress (POS: Main-agent todo_write factory)
- toolkits.wiki (POS: Wiki tools)

[OUTPUT]
- SkillAgentToolsMixin: Mixin providing tool building methods for SkillAgent

[POS]
Tool building mixin for SkillAgent. Assembles meta-tools, skill_manage_tool (from ``write_backend``, unless the
caller supplies one), todo_write (planning, or a top-level agent resuming workspace todos), wiki tools, and
RUNTIME_ONLY hooks; under ``config.no_builtin_tools`` the registry refuses every built-in meta tool, the
skill_manage_tool built from ``write_backend`` included. The skill market tool is not built here: the host mounts it
through ``tools=``.
The class-body annotations are the contract with the host class.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from langchain_core.tools import BaseTool

from myrm_agent_harness.agent.meta_tools import get_meta_tools
from myrm_agent_harness.agent.middlewares._session_context import get_is_subagent
from myrm_agent_harness.agent.tool_management import (
    ToolBindMode,
    ToolSource,
)
from myrm_agent_harness.toolkits.storage import storage_config
from myrm_agent_harness.utils.logger_utils import get_agent_logger

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from langchain.agents.middleware import AgentMiddleware
    from langchain_core.language_models import BaseChatModel

    from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
    from myrm_agent_harness.agent.tool_management import ToolRegistry
    from myrm_agent_harness.agent.types import AgentRuntimeConfig
    from myrm_agent_harness.backends.skills.protocols import SkillBackend
    from myrm_agent_harness.backends.skills.scanning import ScanningSkillWriteBackend
    from myrm_agent_harness.backends.skills.state_manager import SkillStateManager
    from myrm_agent_harness.backends.skills.types import SkillInstance, SkillMetadata
    from myrm_agent_harness.toolkits.wiki import SemanticSearchFn, WikiCompiler, WikiStructure

logger = get_agent_logger(__name__)


class SkillAgentToolsMixin:
    """Mixin providing tool building methods for SkillAgent.

    The annotations below are the host contract: the state ``BaseAgent`` and ``SkillAgent`` assign in
    ``__init__`` (``_task_workspace_root`` is the chat sandbox path for progress persistence). Reads are
    type-checked against it, and an attribute the host no longer assigns raises ``AttributeError`` at the
    first read instead of silently falling back to a default. The mixin itself sets only the wiki handles,
    which stay ``None`` until the wiki tools are mounted.
    """

    llm: BaseChatModel
    config: AgentRuntimeConfig
    user_tools: list[BaseTool]
    user_middlewares: list[AgentMiddleware[Any, Any]]
    _cached_middlewares: list[AgentMiddleware[Any, Any]] | None
    skill_backend: SkillBackend | None
    write_backend: ScanningSkillWriteBackend | None
    state_manager: SkillStateManager | None
    skill_configs: dict[str, dict[str, object]] | None
    _skill_env_map: dict[str, dict[str, str]] | None
    _default_skill_instances: dict[str, str]
    _file_access_mode: FileAccessMode
    _enable_shell_tools: bool
    _enable_answer_tool: bool
    _enable_planning: bool
    _available_tool_names: frozenset[str] | None
    _available_tool_groups: frozenset[str] | None
    _task_workspace_root: str | None
    _wiki_base_dir: Path | str | None
    _wiki_public_dirs: list[Path | str]
    _wiki_public_dir_labels: dict[str, str]
    _wiki_search_fn: SemanticSearchFn | None
    _wiki_scope_id: str | None

    _tool_registry: ToolRegistry
    _wiki_compiler: WikiCompiler | None
    _wiki_structure: WikiStructure | None

    if TYPE_CHECKING:

        async def _get_cached_skills(self) -> list[SkillMetadata]: ...

    def _prompt_locale(self) -> str:
        """Language of the model-facing tool and prompt text: the prompt locale, else the UI locale, else English."""
        return self.config.prompt_locale or self.config.locale or "en"

    async def _build_tools(self) -> list[BaseTool]:
        """Build tool list via ToolRegistry."""
        from myrm_agent_harness.agent.streaming.utils import normalize_tool_names

        skills = await self._get_cached_skills()

        skill_env_map = dict(self._skill_env_map) if self._skill_env_map else {}
        skill_instance_by_name: dict[str, SkillInstance] = {}
        if self.state_manager and self._default_skill_instances and self.skill_backend is not None:
            for skill_name, instance_name in self._default_skill_instances.items():
                try:
                    instance = await self.state_manager.load_instance(
                        backend=self.skill_backend,
                        skill_name=skill_name,
                        instance_name=instance_name,
                    )
                    if instance:
                        skill_instance_by_name[skill_name] = instance
                        skill_env_map[skill_name] = instance.config.env_overrides
                        logger.info("Loaded skill instance: %s.%s", skill_name, instance_name)
                except Exception as e:
                    logger.warning(
                        "Failed to load skill instance %s.%s: %s",
                        skill_name,
                        instance_name,
                        e,
                    )

        registry = self._tool_registry
        prompt_locale = self._prompt_locale()

        meta_tools = get_meta_tools(
            skills,
            self.skill_backend,
            skill_env_map=skill_env_map,
            skill_configs=self.skill_configs,
            registry=registry,
            file_access_mode=self._file_access_mode,
            enable_shell_tools=self._enable_shell_tools,
            enable_answer_tool=self._enable_answer_tool,
            available_tool_names=self._available_tool_names,
            available_tool_groups=self._available_tool_groups,
            skill_instances=skill_instance_by_name or None,
            locale=prompt_locale,
        )

        # Built from ``write_backend``, this is a built-in meta tool like the rest: ``no_builtin_tools`` leaves it out.
        # One the host passes in through ``tools=`` is a host tool and stays.
        user_has_manage_tool = any(getattr(tool, "name", None) == "skill_manage_tool" for tool in self.user_tools)
        if self.write_backend is not None and not user_has_manage_tool:
            from myrm_agent_harness.agent.meta_tools.skills.manage import (
                create_skill_manage_tool,
            )

            meta_tools.append(create_skill_manage_tool(self.write_backend, self.skill_backend, locale=prompt_locale))
            logger.info("skill_manage_tool built from write_backend")

        todo_tool = self._create_todo_write_tool()
        if todo_tool is not None:
            meta_tools.append(todo_tool)

        wiki_tools = self._create_wiki_tools()
        if wiki_tools:
            meta_tools.extend(wiki_tools)

        registry.register_many(meta_tools, source=ToolSource.META)
        registry.register_many(normalize_tool_names(self.user_tools), source=ToolSource.USER)

        all_middlewares: list[object] = list(self.user_middlewares)
        if self._cached_middlewares:
            seen_ids = {id(mw) for mw in all_middlewares}
            all_middlewares.extend(mw for mw in self._cached_middlewares if id(mw) not in seen_ids)

        for middleware in all_middlewares:
            get_tools = getattr(middleware, "get_tools", None)
            if callable(get_tools):
                try:
                    mw_tools = cast("Sequence[BaseTool] | None", get_tools())
                    if mw_tools:
                        for t in mw_tools:
                            is_internal = t.name.startswith("_")
                            bind_mode = ToolBindMode.RUNTIME_ONLY if is_internal else ToolBindMode.TURN1
                            registry.register(t, source=ToolSource.MIDDLEWARE, bind_mode=bind_mode)
                except Exception as e:
                    logger.warning(
                        "Failed to load tools from middleware %s: %s",
                        middleware.__class__.__name__,
                        e,
                    )

        from myrm_agent_harness.agent.meta_tools.discover_capability.discover_capability_tool import (
            sync_discover_capability_tool,
        )

        sync_discover_capability_tool(
            registry,
            skills=skills,
            skill_configs=self.skill_configs,
            available_tool_names=self._available_tool_names,
            available_tool_groups=self._available_tool_groups,
            locale=prompt_locale,
        )

        resolved = registry.resolve()

        self._runtime_skill_count = len(skills)
        self._runtime_tool_count = len(resolved)

        logger.info(
            "SkillAgent._build_tools resolved %d tools, %d skills: %s",
            len(resolved),
            len(skills),
            [t.name for t in resolved],
        )
        return resolved

    def _workspace_has_todos(self) -> bool:
        """Return True when any chat has a persisted todo list in the workspace."""
        from myrm_agent_harness.agent.meta_tools.progress.storage import workspace_todos_exist

        return workspace_todos_exist(workspace_root=self._resolve_task_workspace_root())

    def _should_load_todo_write_tool(self) -> bool:
        """todo_write loads for planning, or for a top-level agent resuming todos; a delegated child resumes nothing."""
        if self._enable_planning:
            return True
        if not get_is_subagent() and self._workspace_has_todos():
            logger.info("todo_write: loading for existing workspace todos (resume)")
            return True
        return False

    def _resolve_task_workspace_root(self) -> str | None:
        """Resolve chat workspace for progress persistence."""
        from myrm_agent_harness.agent.middlewares._session_context import (
            get_workspace_root,
        )

        live_root = get_workspace_root()
        if live_root:
            return live_root
        bound_root = self._task_workspace_root
        if isinstance(bound_root, str) and bound_root.strip():
            return bound_root.strip()
        return None

    def _create_todo_write_tool(self) -> BaseTool | None:
        """Auto-create todo_write when planning is enabled or workspace has todos."""
        if not self._should_load_todo_write_tool():
            logger.info("todo_write: skipped (planning disabled, no existing todos)")
            return None
        if any(getattr(t, "name", getattr(t, "tool_name", None)) == "todo_write" for t in self.user_tools):
            logger.info("todo_write: user-provided override detected, skipping auto-creation")
            return None

        try:
            from myrm_agent_harness.agent.meta_tools.progress.todo_write_tool import (
                create_todo_write_tool,
            )

            tool = create_todo_write_tool(workspace_root=self._resolve_task_workspace_root())
            logger.info("todo_write auto-created")
            return tool
        except Exception as e:
            logger.warning("todo_write auto-creation failed: %s", e)
            return None

    def _create_wiki_tools(self) -> list[BaseTool]:
        """Auto-create wiki tools if wiki_base_dir is configured.

        Creates 3 LangChain tools for the agent: wiki_ingest, wiki_query, wiki_apply.
        Manual compile and maintain remain Settings/REST-only operations.
        """
        if self._wiki_base_dir is None:
            return []

        try:
            from myrm_agent_harness.toolkits.wiki import (
                WikiCompiler,
                WikiConfig,
                WikiQueryEngine,
                WikiStructure,
                create_wiki_tools,
            )

            structure = WikiStructure(
                self._wiki_base_dir,
                public_dirs=self._wiki_public_dirs,
                public_dir_labels=self._wiki_public_dir_labels,
            )
            structure.ensure_structure()
            config = WikiConfig()
            compiler = WikiCompiler(self.llm, structure, config)
            query_engine = WikiQueryEngine(
                self.llm,
                structure,
                config,
                search_fn=self._wiki_search_fn,
            )
            self._wiki_structure = structure
            self._wiki_compiler = compiler

            tools = create_wiki_tools(
                compiler,
                query_engine,
                structure,
                wiki_scope_id=self._wiki_scope_id,
                locale=self._prompt_locale(),
            )

            logger.info(
                "wiki tools auto-created (3 tools, base_dir=%s, shared=%d)",
                self._wiki_base_dir,
                len(self._wiki_public_dirs),
            )
            return tools
        except Exception as e:
            logger.warning("wiki tools creation failed: %s", e)
            return []

    async def _get_skill_storage_paths(self) -> list[str]:
        """Get all skill storage paths (absolute)."""
        skills = await self._get_cached_skills()
        base_path = storage_config.get_base_path()
        return [str(base_path / skill.storage_path) for skill in skills if skill.storage_path]
