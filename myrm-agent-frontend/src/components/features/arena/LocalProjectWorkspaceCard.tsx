import React, { useState } from 'react';
import {
  FolderGit2,
  HardDrive,
  ShieldCheck,
  Unlink,
  CheckCircle2,
  AlertCircle,
  FolderOpen,
} from 'lucide-react';
import { useArenaStore } from './useArenaStore';

export interface LocalProjectWorkspaceCardProps {
  readonly className?: string;
}

export const LocalProjectWorkspaceCard: React.FC<LocalProjectWorkspaceCardProps> = ({
  className = '',
}) => {
  const { localProject, bindLocalProject, unbindLocalProject } = useArenaStore();

  const [inputPath, setInputPath] = useState('');
  const [inputName, setInputName] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleBind = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    const success = bindLocalProject(inputPath, inputName);
    if (!success) {
      setErrorMsg('路径不合法，必须提供系统绝对路径或 ~ 格式主目录路径');
    } else {
      setInputPath('');
      setInputName('');
    }
  };

  return (
    <div
      data-testid="local-project-workspace-card"
      className={`rounded-2xl border border-slate-700/80 bg-slate-900/90 p-4 shadow-xl backdrop-blur-md text-slate-100 ${className}`}
    >
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-400">
            <HardDrive className="h-4 w-4" />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-slate-100">
              本地物理工作区与数据主权
            </h4>
            <p className="text-[10px] text-slate-400">
              项目代码与工件全量保存在本地设备 · 离线随时可用
            </p>
          </div>
        </div>

        {localProject?.isBound && (
          <div className="flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-[10px] font-medium text-emerald-400">
            <ShieldCheck className="h-3 w-3" />
            <span>本地优先离线可用</span>
          </div>
        )}
      </div>

      {localProject?.isBound ? (
        <div className="mt-3.5 space-y-3">
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-200 flex items-center gap-1.5">
                <FolderGit2 className="h-4 w-4 text-indigo-400" />
                {localProject.projectName}
              </span>
              <span className="text-[10px] text-slate-400">
                托管文件: {localProject.fileCount} 个
              </span>
            </div>
            <p className="mt-1 font-mono text-[11px] text-slate-400 truncate">
              {localProject.projectPath}
            </p>
          </div>

          <div className="flex items-center justify-between pt-1">
            <span className="text-[10px] text-slate-500">
              断网模式下仍可通过物理目录直接编辑与执行
            </span>
            <button
              type="button"
              onClick={unbindLocalProject}
              className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-300 hover:border-slate-600 hover:text-white transition-colors"
            >
              <Unlink className="h-3 w-3" />
              <span>解除目录绑定</span>
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleBind} className="mt-3.5 space-y-2.5">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <label htmlFor="project-name-input" className="block text-[11px] text-slate-400 mb-1">
                项目显示名称
              </label>
              <input
                id="project-name-input"
                type="text"
                placeholder="例如: 电商微服务重构"
                value={inputName}
                onChange={(e) => {
                  setInputName(e.target.value);
                }}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-hidden"
              />
            </div>
            <div>
              <label htmlFor="project-path-input" className="block text-[11px] text-slate-400 mb-1">
                宿主机物理绝对路径
              </label>
              <input
                id="project-path-input"
                type="text"
                placeholder="例如: ~/projects/my-web"
                value={inputPath}
                onChange={(e) => {
                  setInputPath(e.target.value);
                }}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-slate-100 font-mono placeholder-slate-500 focus:border-indigo-500 focus:outline-hidden"
              />
            </div>
          </div>

          {errorMsg && (
            <div className="flex items-center gap-1.5 text-rose-400 text-[11px]">
              <AlertCircle className="h-3.5 w-3.5" />
              <span>{errorMsg}</span>
            </div>
          )}

          <div className="flex items-center justify-between pt-1">
            <span className="text-[10px] text-slate-500">
              数据仅存于本机磁盘，绝不上传第三方云端
            </span>
            <button
              type="submit"
              className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-medium text-white shadow-xs hover:bg-indigo-500 transition-colors"
            >
              <FolderOpen className="h-3.5 w-3.5" />
              <span>立即绑定本地物理工作区</span>
            </button>
          </div>
        </form>
      )}
    </div>
  );
};
