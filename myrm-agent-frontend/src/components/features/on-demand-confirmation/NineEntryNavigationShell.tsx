import React from 'react';
import {
  PlusCircle,
  Clock,
  MessageSquare,
  Puzzle,
  Bot,
  Smartphone,
  HardDrive,
  LayoutDashboard,
  History,
  Command,
} from 'lucide-react';
import { useOnDemandConfirmationStore } from './useOnDemandConfirmationStore';
import { NINE_ENTRY_NAV_ITEMS } from './onDemandConfirmationEngine';
import { NineEntryId, EntryCategory } from './onDemandConfirmationTypes';

export const NineEntryNavigationShell: React.FC = () => {
  const { activeNavEntryId, setActiveNavEntryId } = useOnDemandConfirmationStore();

  const getEntryIcon = (id: NineEntryId) => {
    switch (id) {
      case 'new_task':
        return <PlusCircle className="w-4 h-4 text-emerald-400" />;
      case 'cron_jobs':
        return <Clock className="w-4 h-4 text-purple-400" />;
      case 'main_chat':
        return <MessageSquare className="w-4 h-4 text-indigo-400" />;
      case 'skills_mcp':
        return <Puzzle className="w-4 h-4 text-sky-400" />;
      case 'agents':
        return <Bot className="w-4 h-4 text-amber-400" />;
      case 'mobile_pair':
        return <Smartphone className="w-4 h-4 text-teal-400" />;
      case 'drive_projects':
        return <HardDrive className="w-4 h-4 text-rose-400" />;
      case 'kanban_roadmap':
        return <LayoutDashboard className="w-4 h-4 text-blue-400" />;
      case 'recent_history':
        return <History className="w-4 h-4 text-slate-400" />;
    }
  };

  const getCategoryTitle = (cat: EntryCategory) => {
    switch (cat) {
      case 'lifecycle':
        return '任务生命周期';
      case 'collaboration':
        return '协同与网络';
      case 'assets':
        return '资产与看板';
    }
  };

  const categories: EntryCategory[] = ['lifecycle', 'collaboration', 'assets'];

  return (
    <nav
      data-testid="nine-entry-nav-shell"
      aria-label="九大工作流入口中枢导航"
      className="w-64 bg-slate-950/95 border-r border-slate-800 p-3 flex flex-col justify-between h-full select-none text-xs"
    >
      <div className="space-y-4">
        {/* 顶部标题 */}
        <div className="flex items-center justify-between pb-2.5 border-b border-slate-800 px-1">
          <div className="flex items-center gap-2 font-bold text-slate-200">
            <Command className="w-4 h-4 text-indigo-400" />
            <span>工作流中枢</span>
          </div>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
            9 入口
          </span>
        </div>

        {/* 分类入口列表 */}
        {categories.map((category) => {
          const items = NINE_ENTRY_NAV_ITEMS.filter(
            (item) => item.category === category
          );

          return (
            <div key={category} className="space-y-1">
              <span className="px-2 text-[10px] font-mono uppercase tracking-wider text-slate-500">
                {getCategoryTitle(category)}
              </span>

              <div className="space-y-0.5">
                {items.map((item) => {
                  const isActive = activeNavEntryId === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setActiveNavEntryId(item.id)}
                      data-testid={`nine-nav-entry-${item.id}`}
                      className={`w-full text-left flex items-center justify-between px-2.5 py-2 rounded-xl transition-all cursor-pointer ${
                        isActive
                          ? 'bg-indigo-950/70 border border-indigo-500/50 text-white font-medium shadow-xs'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60 border border-transparent'
                      }`}
                      title={item.description}
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        {getEntryIcon(item.id)}
                        <span className="truncate">{item.label}</span>
                      </div>

                      <div className="flex items-center gap-1.5 shrink-0">
                        {item.badge && (
                          <span className="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-indigo-500 text-white leading-none">
                            {item.badge}
                          </span>
                        )}
                        <span className="text-[10px] font-mono text-slate-600">
                          {item.shortcut}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {/* 底部工作台快捷提示 */}
      <div className="pt-2.5 border-t border-slate-800/80 px-2 text-[10px] text-slate-500 font-mono flex items-center justify-between">
        <span>全局快捷键映射激活</span>
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
      </div>
    </nav>
  );
};
