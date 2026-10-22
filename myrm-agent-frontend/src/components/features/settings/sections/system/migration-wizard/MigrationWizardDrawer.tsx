import React from 'react';
import {
  Wand2,
  X,
  Bot,
  Layers,
  Wrench,
  CheckCircle2,
  ArrowRight,
  Check,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { useMigrationWizardStore } from './useMigrationWizardStore';

export const MigrationWizardDrawer: React.FC = () => {
  const {
    isDrawerOpen,
    radarReport,
    progress,
    toggleAssetSelection,
    selectAll,
    startMigration,
    closeDrawer,
  } = useMigrationWizardStore();

  if (!isDrawerOpen) {
    return null;
  }

  const { agents, skills, mcpServers } = radarReport;
  const selectedAgentsCount = agents.filter((a) => a.selected).length;
  const selectedSkillsCount = skills.filter((s) => s.selected).length;
  const selectedMcpCount = mcpServers.filter((m) => m.selected).length;
  const totalSelectedCount = selectedAgentsCount + selectedSkillsCount + selectedMcpCount;

  const handleStartMigration = (): void => {
    void startMigration();
  };

  return (
    <dialog
      open
      aria-modal="true"
      aria-labelledby="migration-drawer-title"
      className="fixed inset-0 z-50 flex items-center justify-center w-full h-full p-4 bg-black/60 backdrop-blur-sm"
    >
      <section
        role="document"
        className="w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden border rounded-xl shadow-2xl bg-slate-900 border-slate-800 text-slate-100 animate-in fade-in zoom-in-95 duration-150"
      >
        {/* 顶部 Header */}
        <header className="flex items-center justify-between px-6 py-4 border-b border-slate-800/80 bg-slate-950/40 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-sky-500/10 text-sky-400 border border-sky-500/20">
              <Wand2 className="w-5 h-5" />
            </div>
            <div>
              <h2 id="migration-drawer-title" className="text-base font-semibold leading-tight text-white">
                本地生态免 SSH 零摩擦迁移向导
              </h2>
              <p className="text-xs text-slate-400">
                将 OpenClaw / Hermes / Cursor 配置一键无损转译为 Myrm 标准资产
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeDrawer}
            className="p-1.5 transition-colors rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
            aria-label="关闭迁移抽屉"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        {/* 身体内容区 */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {progress.status === 'completed' ? (
            <div className="p-6 border rounded-xl bg-emerald-950/30 border-emerald-500/30 text-center space-y-3.5">
              <div className="inline-flex p-3 rounded-full bg-emerald-500/20 text-emerald-400">
                <CheckCircle2 className="w-8 h-8" />
              </div>
              <h3 className="text-base font-semibold text-white">迁移完成！资产已全量就绪</h3>
              <p className="text-xs text-slate-300 max-w-md mx-auto">
                已成功无损转译并导入{' '}
                <span className="font-semibold text-emerald-400">{progress.migratedCount} 项生态资产</span>
                。包含 Agent 人设、自研技能包以及 MCP 工具通道，可在工作台中直接唤醒调用。
              </p>
              <div className="pt-2">
                <button
                  type="button"
                  onClick={closeDrawer}
                  className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium transition-colors border rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white border-emerald-500"
                >
                  <span>进入工作台体验</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ) : progress.status === 'migrating' ? (
            <div className="p-6 border rounded-xl bg-slate-950/60 border-slate-800 text-center space-y-4">
              <div className="space-y-1">
                <h3 className="text-sm font-semibold text-white">正在执行无损跨生态转译流水线...</h3>
                <p className="text-xs font-mono text-sky-400">{progress.currentStepText}</p>
              </div>
              <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden border border-slate-700/80">
                <div
                  className="bg-sky-500 h-2 transition-all duration-300 rounded-full"
                  style={{ width: `${progress.progressPercentage}%` }}
                />
              </div>
            </div>
          ) : (
            <>
              {/* 全选操作栏 */}
              <div className="flex items-center justify-between p-3 border rounded-lg bg-slate-950/60 border-slate-800 text-xs">
                <div className="flex items-center gap-2 text-slate-300">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  <span>已勾选 {totalSelectedCount} 项待迁移资产</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => selectAll(true)}
                    className="text-xs text-sky-400 hover:text-sky-300"
                  >
                    全选
                  </button>
                  <span className="text-slate-600">|</span>
                  <button
                    type="button"
                    onClick={() => selectAll(false)}
                    className="text-xs text-slate-400 hover:text-slate-300"
                  >
                    取消全选
                  </button>
                </div>
              </div>

              {/* 智能体资产 */}
              <div className="space-y-2.5">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
                  <Bot className="w-4 h-4 text-indigo-400" />
                  <span>智能体人设与 Prompts ({selectedAgentsCount}/{agents.length})</span>
                </div>
                <div className="grid grid-cols-1 gap-2">
                  {agents.map((agent) => (
                    <label
                      key={agent.id}
                      className={`flex items-start gap-3 p-3 border rounded-lg cursor-pointer transition-colors ${
                        agent.selected
                          ? 'bg-indigo-950/20 border-indigo-500/30 text-white'
                          : 'bg-slate-950/40 border-slate-800/80 text-slate-400'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={agent.selected}
                        onChange={() => toggleAssetSelection('agents', agent.id)}
                        className="mt-1 rounded border-slate-700 bg-slate-900 text-sky-600 focus:ring-0 focus:ring-offset-0"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium text-white">{agent.originalName}</span>
                          <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                            {agent.source}
                          </span>
                        </div>
                        <p className="mt-1 text-[11px] font-mono text-slate-400 truncate">
                          {agent.promptPreview}
                        </p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              {/* 自研技能包 */}
              <div className="space-y-2.5">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
                  <Layers className="w-4 h-4 text-emerald-400" />
                  <span>自研技能包 ({selectedSkillsCount}/{skills.length})</span>
                </div>
                <div className="grid grid-cols-1 gap-2">
                  {skills.map((skill) => (
                    <label
                      key={skill.id}
                      className={`flex items-start gap-3 p-3 border rounded-lg cursor-pointer transition-colors ${
                        skill.selected
                          ? 'bg-emerald-950/20 border-emerald-500/30 text-white'
                          : 'bg-slate-950/40 border-slate-800/80 text-slate-400'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={skill.selected}
                        onChange={() => toggleAssetSelection('skills', skill.id)}
                        className="mt-1 rounded border-slate-700 bg-slate-900 text-emerald-600 focus:ring-0 focus:ring-offset-0"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-mono font-medium text-white">{skill.skillName}</span>
                          <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                            {skill.source}
                          </span>
                        </div>
                        <p className="mt-0.5 text-[11px] text-slate-400">{skill.description}</p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              {/* MCP 服务 */}
              <div className="space-y-2.5">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
                  <Wrench className="w-4 h-4 text-amber-400" />
                  <span>MCP 工具服务器 ({selectedMcpCount}/{mcpServers.length})</span>
                </div>
                <div className="grid grid-cols-1 gap-2">
                  {mcpServers.map((mcp) => (
                    <label
                      key={mcp.id}
                      className={`flex items-start gap-3 p-3 border rounded-lg cursor-pointer transition-colors ${
                        mcp.selected
                          ? 'bg-amber-950/20 border-amber-500/30 text-white'
                          : 'bg-slate-950/40 border-slate-800/80 text-slate-400'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={mcp.selected}
                        onChange={() => toggleAssetSelection('mcpServers', mcp.id)}
                        className="mt-1 rounded border-slate-700 bg-slate-900 text-amber-600 focus:ring-0 focus:ring-offset-0"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-mono font-medium text-white">{mcp.serverName}</span>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                            {mcp.transportType}
                          </span>
                        </div>
                        <p className="mt-0.5 text-[10px] font-mono text-slate-400 truncate">
                          {mcp.commandOrUrl}
                        </p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        {/* 底部 Footer */}
        {progress.status !== 'completed' && (
          <footer className="flex items-center justify-between px-6 py-4 border-t border-slate-800/80 bg-slate-950/40 shrink-0">
            <span className="text-xs text-slate-400">
              已选 {totalSelectedCount} 项 · 100% 保持历史执行脚本不变
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={closeDrawer}
                disabled={progress.status === 'migrating'}
                className="px-3.5 py-1.5 text-xs font-medium transition-colors border rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border-slate-700 disabled:opacity-50"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleStartMigration}
                disabled={totalSelectedCount === 0 || progress.status === 'migrating'}
                className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium transition-colors border rounded-lg bg-sky-600 hover:bg-sky-500 text-white border-sky-500 shadow-sm disabled:opacity-50"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>立即一键无损迁移</span>
              </button>
            </div>
          </footer>
        )}
      </section>
    </dialog>
  );
};
