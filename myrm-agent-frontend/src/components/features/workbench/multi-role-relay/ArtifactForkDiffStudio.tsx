import React, { useState, useEffect } from 'react';
import {
  GitFork,
  Check,
  X,
  Split,
  Edit3,
  FileText,
  AlertCircle,
  Tag,
} from 'lucide-react';
import { useMultiRoleRelayStore } from './useMultiRoleRelayStore';
import { computeContentDiffLines } from './relayPipelineEngine';

export const ArtifactForkDiffStudio: React.FC = () => {
  const {
    selectedSnapshot,
    isDiffStudioOpen,
    closeDiffStudio,
    createFork,
    applyForkBranch,
  } = useMultiRoleRelayStore();

  const [branchName, setBranchName] = useState('');
  const [modifiedText, setModifiedText] = useState('');
  const [userNote, setUserNote] = useState('');
  const [activeTab, setActiveTab] = useState<'edit' | 'diff'>('diff');

  useEffect(() => {
    if (selectedSnapshot) {
      setModifiedText(selectedSnapshot.rawContent);
      setBranchName(`fork-from-${selectedSnapshot.role}-v${selectedSnapshot.version + 1}`);
      setUserNote('');
    }
  }, [selectedSnapshot]);

  if (!isDiffStudioOpen || !selectedSnapshot) {
    return null;
  }

  const diffLines = computeContentDiffLines(
    selectedSnapshot.rawContent,
    modifiedText
  );

  const handleApply = () => {
    const branch = createFork(branchName, modifiedText, userNote);
    if (branch) {
      applyForkBranch(branch.id);
    }
  };

  return (
    <>
      <div
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm transition-opacity"
        aria-hidden="true"
      />
      <dialog
        open
        aria-labelledby="fork-studio-title"
        className="fixed inset-0 z-50 m-auto w-full max-w-3xl bg-slate-900 border border-slate-700/80 rounded-xl shadow-2xl p-0 flex flex-col text-slate-100 overflow-hidden"
        data-testid="artifact-fork-diff-studio"
      >
        {/* 头部导航与标题 */}
        <header className="px-5 py-3.5 border-b border-slate-800 bg-slate-950/80 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="p-1.5 rounded-lg bg-indigo-600/30 text-indigo-400 border border-indigo-500/40">
              <GitFork className="w-4 h-4" />
            </div>
            <div>
              <h3 id="fork-studio-title" className="font-bold text-xs text-white">
                中间产物分支修改与双向对比工作室
              </h3>
              <p className="text-[10px] text-slate-400">
                对【{selectedSnapshot.roleName}】交付的快照创建独立修改分支，修正后再交付后续角色
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeDiffStudio}
            aria-label="关闭分支修改工作台"
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        {/* 选项卡切换：编辑视图 vs 差量对比 */}
        <div className="px-5 py-2 bg-slate-950/40 border-b border-slate-800 flex items-center justify-between text-xs">
          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={() => setActiveTab('diff')}
              className={`px-3 py-1 rounded text-xs font-medium flex items-center space-x-1.5 transition-colors ${
                activeTab === 'diff'
                  ? 'bg-indigo-600 text-white'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              <Split className="w-3 h-3" />
              <span>差量比对 (Diff View)</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('edit')}
              className={`px-3 py-1 rounded text-xs font-medium flex items-center space-x-1.5 transition-colors ${
                activeTab === 'edit'
                  ? 'bg-indigo-600 text-white'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              <Edit3 className="w-3 h-3" />
              <span>源码编辑 (Editor)</span>
            </button>
          </div>

          <div className="flex items-center space-x-2 text-[11px]">
            <span className="text-slate-400 font-mono">基准版本: v{selectedSnapshot.version}.0</span>
          </div>
        </div>

        {/* 主编辑/对比视窗 */}
        <div className="p-5 flex-1 overflow-y-auto max-h-[380px] space-y-4">
          {activeTab === 'edit' ? (
            <div className="space-y-1.5">
              <label
                htmlFor="modified-content-textarea"
                className="text-xs font-semibold text-slate-300 block"
              >
                分支修改后内容
              </label>
              <textarea
                id="modified-content-textarea"
                value={modifiedText}
                onChange={(e) => setModifiedText(e.target.value)}
                rows={12}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 text-xs font-mono text-slate-200 focus:outline-none focus:border-indigo-500 leading-relaxed"
              />
            </div>
          ) : (
            <div className="space-y-1 font-mono text-xs bg-slate-950 p-3 rounded-lg border border-slate-800 max-h-[320px] overflow-y-auto">
              {diffLines.map((line, idx) => {
                let colorCls = 'text-slate-300';
                let prefix = ' ';
                let bgCls = '';

                if (line.type === 'added') {
                  colorCls = 'text-emerald-400';
                  bgCls = 'bg-emerald-950/40';
                  prefix = '+';
                } else if (line.type === 'removed') {
                  colorCls = 'text-rose-400 line-through';
                  bgCls = 'bg-rose-950/40';
                  prefix = '-';
                }

                return (
                  <div
                    key={`${line.lineNumber}-${idx}`}
                    className={`flex items-start px-2 py-0.5 rounded ${bgCls} ${colorCls}`}
                  >
                    <span className="w-6 text-slate-600 select-none text-[10px]">
                      {line.lineNumber}
                    </span>
                    <span className="w-4 select-none font-bold">{prefix}</span>
                    <span className="flex-1 whitespace-pre-wrap">{line.text}</span>
                  </div>
                );
              })}
            </div>
          )}

          {/* 分支命名与人工修改备注 */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-slate-800">
            <div>
              <label
                htmlFor="fork-branch-name-input"
                className="text-xs font-semibold text-slate-300 block mb-1"
              >
                分支标识名称
              </label>
              <input
                id="fork-branch-name-input"
                type="text"
                value={branchName}
                onChange={(e) => setBranchName(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1 text-xs text-slate-200 font-mono"
              />
            </div>
            <div>
              <label
                htmlFor="fork-user-note-input"
                className="text-xs font-semibold text-slate-300 block mb-1"
              >
                修改原因与下流指示 (User Note)
              </label>
              <input
                id="fork-user-note-input"
                type="text"
                value={userNote}
                onChange={(e) => setUserNote(e.target.value)}
                placeholder="如：修正预估汇率偏差，指引撰稿人按谨慎口径成文"
                className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1 text-xs text-slate-200"
              />
            </div>
          </div>
        </div>

        {/* 底部操作区 */}
        <footer className="px-5 py-3 border-t border-slate-800 bg-slate-950/80 flex items-center justify-between">
          <div className="flex items-center space-x-1.5 text-[11px] text-amber-400">
            <AlertCircle className="w-3.5 h-3.5" />
            <span>提交分支后将自动以此作为后续智能体的输入前置条件</span>
          </div>

          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={closeDiffStudio}
              className="px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleApply}
              aria-label="提交分支并推向下游 Agent"
              className="px-4 py-1.5 text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white rounded shadow flex items-center space-x-1.5 transition-colors"
            >
              <Check className="w-3.5 h-3.5" />
              <span>提交分支并推向下游 Agent</span>
            </button>
          </div>
        </footer>
      </dialog>
    </>
  );
};
