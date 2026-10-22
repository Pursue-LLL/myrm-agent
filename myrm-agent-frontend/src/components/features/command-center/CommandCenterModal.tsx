import React, { useEffect } from 'react';
import {
  MessageSquare,
  Server,
  BarChart3,
  Wrench,
  X,
  Gauge,
} from 'lucide-react';
import { useCommandCenterStore } from './useCommandCenterStore';
import { isCommandCenterShortcut } from './commandCenterEngine';
import { CommandCenterTab } from './commandCenterTypes';
import { CommandCenterSessionsTab } from './CommandCenterSessionsTab';
import { CommandCenterSystemTab } from './CommandCenterSystemTab';
import { CommandCenterUsageTab } from './CommandCenterUsageTab';
import { CommandCenterMaintenanceTab } from './CommandCenterMaintenanceTab';

export const CommandCenterModal: React.FC = () => {
  const { isOpen, activeTab, openModal, closeModal, setActiveTab } =
    useCommandCenterStore();

  // 注册系统级/全局键盘监听（Cmd+. / Ctrl+. / Cmd+K / Ctrl+K / ESC）
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const { isOpen: currentOpen, closeModal: close, openModal: open } =
        useCommandCenterStore.getState();

      if (isCommandCenterShortcut(e)) {
        e.preventDefault();
        if (currentOpen) {
          close();
        } else {
          open('sessions');
        }
        return;
      }

      if (e.key === 'Escape' && currentOpen) {
        e.preventDefault();
        close();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  if (!isOpen) {
    return null;
  }

  const tabs: Array<{ id: CommandCenterTab; label: string; icon: React.ComponentType<{ className?: string }> }> = [
    { id: 'sessions', label: '会话速查与导出', icon: MessageSquare },
    { id: 'system', label: '网关体态与日志', icon: Server },
    { id: 'usage', label: '用量与资产排行', icon: BarChart3 },
    { id: 'maintenance', label: '维护与排障中心', icon: Wrench },
  ];

  return (
    <dialog
      open
      aria-modal="true"
      data-testid="command-center-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-md p-4 w-full h-full border-0 select-none"
    >
      <div className="relative w-full max-w-4xl bg-slate-950/95 border border-slate-800 rounded-3xl p-6 shadow-2xl flex flex-col justify-between max-h-[85vh]">
        {/* 顶部标题栏与 Tab 切换 */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-800/80">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-3 py-1 bg-slate-900 border border-slate-800 rounded-xl">
              <Gauge className="w-4 h-4 text-indigo-400" />
              <span className="font-bold text-xs text-slate-100 tracking-wide">
                COMMAND CENTER
              </span>
            </div>

            <div className="flex items-center bg-slate-900/60 p-0.5 rounded-xl border border-slate-800/80 text-xs">
              {tabs.map((tab) => {
                const IconComponent = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                      isActive
                        ? 'bg-indigo-600 text-white shadow-sm'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <IconComponent className="w-3.5 h-3.5" />
                    <span>{tab.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <button
            type="button"
            onClick={closeModal}
            className="p-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-white transition-colors"
            title="关闭 (ESC)"
            aria-label="关闭"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 内容面板 */}
        <div className="my-3 flex-1 overflow-hidden">
          {activeTab === 'sessions' && <CommandCenterSessionsTab />}
          {activeTab === 'system' && <CommandCenterSystemTab />}
          {activeTab === 'usage' && <CommandCenterUsageTab />}
          {activeTab === 'maintenance' && <CommandCenterMaintenanceTab />}
        </div>

        {/* 底部快捷键与架构克制提示 */}
        <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-500 font-mono">
          <div className="flex items-center gap-2">
            <span>快捷唤起: ⌘. / Ctrl+.</span>
            <span>·</span>
            <span>指令面板: ⌘K / Ctrl+K</span>
            <span>·</span>
            <span>退出: ESC</span>
          </div>
          <span>Myrm Production Cockpit v2026.8</span>
        </div>
      </div>
    </dialog>
  );
};
