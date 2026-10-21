import React from 'react';
import { Copy, ShieldCheck, Wrench, Layers, Key, Check } from 'lucide-react';
import type { InheritanceOptions, MasterAssetSnapshot } from './botCreatorStudioTypes';

interface MasterInheritanceToggleCardProps {
  isInheriting: boolean;
  options: InheritanceOptions;
  masterAssets: MasterAssetSnapshot;
  onToggleInheritance: (enable: boolean) => void;
  onToggleOption: (option: keyof InheritanceOptions, enable: boolean) => void;
}

export const MasterInheritanceToggleCard: React.FC<MasterInheritanceToggleCardProps> = ({
  isInheriting,
  options,
  masterAssets,
  onToggleInheritance,
  onToggleOption,
}) => {
  return (
    <div
      className={`rounded-lg border p-3.5 transition-all backdrop-blur-sm ${
        isInheriting
          ? 'border-blue-500/40 bg-blue-950/20 shadow-sm'
          : 'border-slate-800 bg-slate-900/60'
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <div className="rounded bg-blue-500/10 p-1.5 text-blue-400">
            <Copy className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xs font-semibold text-slate-100">
                一键继承主 Agent 核心资产
              </span>
              <span className="rounded bg-emerald-500/10 px-1.5 py-0.2 text-[10px] font-medium text-emerald-400">
                免重复配置
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              自动复用当前已就绪的主模型、已授权系统工具、MCP 扩展与安全凭证
            </p>
          </div>
        </div>

        <button
          type="button"
          role="switch"
          aria-checked={isInheriting}
          aria-label="一键继承主智能体配置开关"
          onClick={() => {
            onToggleInheritance(!isInheriting);
          }}
          className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
            isInheriting ? 'bg-blue-600' : 'bg-slate-700'
          }`}
        >
          <span
            className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200 ease-in-out ${
              isInheriting ? 'translate-x-4' : 'translate-x-0'
            }`}
          />
        </button>
      </div>

      {isInheriting && (
        <div className="mt-3 grid grid-cols-2 gap-2 border-t border-slate-800/80 pt-2.5 text-xs">
          <label className="flex items-center space-x-2 rounded border border-slate-800 bg-slate-900/80 p-2 text-slate-300">
            <input
              type="checkbox"
              checked={options.inheritModel}
              onChange={(e) => {
                onToggleOption('inheritModel', e.target.checked);
              }}
              className="rounded border-slate-700 text-blue-600 focus:ring-blue-500"
            />
            <ShieldCheck className="h-3.5 w-3.5 text-blue-400" />
            <div className="min-w-0 flex-1 truncate">
              <span className="text-[11px]">模型: {masterAssets.defaultModel}</span>
            </div>
          </label>

          <label className="flex items-center space-x-2 rounded border border-slate-800 bg-slate-900/80 p-2 text-slate-300">
            <input
              type="checkbox"
              checked={options.inheritTools}
              onChange={(e) => {
                onToggleOption('inheritTools', e.target.checked);
              }}
              className="rounded border-slate-700 text-blue-600 focus:ring-blue-500"
            />
            <Wrench className="h-3.5 w-3.5 text-amber-400" />
            <div className="min-w-0 flex-1 truncate">
              <span className="text-[11px]">工具: {masterAssets.enabledTools.length} 项</span>
            </div>
          </label>

          <label className="flex items-center space-x-2 rounded border border-slate-800 bg-slate-900/80 p-2 text-slate-300">
            <input
              type="checkbox"
              checked={options.inheritMcp}
              onChange={(e) => {
                onToggleOption('inheritMcp', e.target.checked);
              }}
              className="rounded border-slate-700 text-blue-600 focus:ring-blue-500"
            />
            <Layers className="h-3.5 w-3.5 text-purple-400" />
            <div className="min-w-0 flex-1 truncate">
              <span className="text-[11px]">MCP: {masterAssets.enabledMcpServers.length} 个服务</span>
            </div>
          </label>

          <label className="flex items-center space-x-2 rounded border border-slate-800 bg-slate-900/80 p-2 text-slate-300">
            <input
              type="checkbox"
              checked={options.inheritCredentials}
              onChange={(e) => {
                onToggleOption('inheritCredentials', e.target.checked);
              }}
              className="rounded border-slate-700 text-blue-600 focus:ring-blue-500"
            />
            <Key className="h-3.5 w-3.5 text-emerald-400" />
            <div className="min-w-0 flex-1 truncate">
              <span className="text-[11px]">安全凭据直通引用</span>
            </div>
          </label>
        </div>
      )}

      {!isInheriting && (
        <div className="mt-2 text-[11px] text-slate-400">
          已关闭自动继承，您可在下方独立选择大模型认知层级与工具集。
        </div>
      )}
    </div>
  );
};
