import React from 'react';
import {
  GitFork,
  FileText,
  Clock,
  User,
  Zap,
  Tag,
  CheckCircle2,
} from 'lucide-react';
import { useMultiRoleRelayStore } from './useMultiRoleRelayStore';

export const StageArtifactSnapshotViewer: React.FC = () => {
  const { selectedSnapshot, openDiffStudio } = useMultiRoleRelayStore();

  if (!selectedSnapshot) {
    return (
      <div
        className="p-8 text-center text-xs text-slate-500 font-mono"
        data-testid="stage-snapshot-empty"
      >
        请在上方接力时序指示器中点击任意角色，查看其交接的中间产物快照
      </div>
    );
  }

  return (
    <article
      aria-label="阶段交接工件原子快照视窗"
      className="p-4 space-y-4 text-slate-100 flex flex-col h-full bg-slate-900"
      data-testid="stage-artifact-snapshot-viewer"
    >
      {/* 头部元数据条 */}
      <header className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-2">
        <div className="flex items-center space-x-2.5">
          <div className="p-2 rounded-lg bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
            <FileText className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="font-bold text-xs text-white">
                {selectedSnapshot.artifactName}
              </h3>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800/60 font-mono">
                v{selectedSnapshot.version}.0
              </span>
            </div>
            <div className="flex items-center space-x-2 text-[11px] text-slate-400 mt-0.5">
              <span className="flex items-center space-x-1">
                <User className="w-3 h-3 text-slate-500" />
                <span>{selectedSnapshot.roleName}交付</span>
              </span>
              <span>•</span>
              <span className="flex items-center space-x-1 font-mono">
                <Zap className="w-3 h-3 text-amber-400" />
                <span>{selectedSnapshot.tokenCount} Tokens</span>
              </span>
            </div>
          </div>
        </div>

        {/* 发起分支修改按钮 */}
        <button
          type="button"
          onClick={() => openDiffStudio(selectedSnapshot.id)}
          aria-label="基于当前快照发起分支微调"
          className="px-3 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-md shadow flex items-center space-x-1.5 transition-all shrink-0 self-start sm:self-auto"
        >
          <GitFork className="w-3.5 h-3.5" />
          <span>分支微调 (Fork Branch)</span>
        </button>
      </header>

      {/* 摘要与上下文说明 */}
      <div className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800 text-xs text-slate-300 flex items-start space-x-2">
        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
        <div>
          <span className="font-semibold text-slate-200">阶段结论摘要：</span>
          <span className="text-slate-300 ml-1">{selectedSnapshot.summary}</span>
        </div>
      </div>

      {/* 原始内容原子预览区 */}
      <div className="flex-1 bg-slate-950 rounded-lg p-3 border border-slate-800 font-mono text-xs overflow-y-auto max-h-[420px]">
        <pre className="text-slate-200 whitespace-pre-wrap leading-relaxed select-all">
          {selectedSnapshot.rawContent}
        </pre>
      </div>
    </article>
  );
};
