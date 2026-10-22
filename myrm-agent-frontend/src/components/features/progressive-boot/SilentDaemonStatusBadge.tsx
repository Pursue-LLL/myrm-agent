import React from 'react';
import { ShieldCheck, Activity, Bell, ChevronRight } from 'lucide-react';
import { useProgressiveBootStore } from './useProgressiveBootStore';

export const SilentDaemonStatusBadge: React.FC = () => {
  const { services, silencedNotices, isDrawerOpen, toggleDrawer } =
    useProgressiveBootStore();

  const allReady = services.every((s) => s.isReady);
  const readyCount = services.filter((s) => s.isReady).length;
  const noticeCount = silencedNotices.length;

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={() => {
          toggleDrawer();
        }}
        aria-label="查看后台静默服务与渐进能力披露抽屉"
        aria-expanded={isDrawerOpen}
        className="group inline-flex items-center gap-2 rounded-full border border-slate-700/60 bg-slate-900/80 px-3 py-1.5 text-xs text-slate-300 shadow-sm backdrop-blur-sm transition-all hover:border-indigo-500/50 hover:bg-slate-800/90 active:scale-95 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
      >
        <span className="relative flex h-2 w-2">
          {allReady ? (
            <>
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </>
          ) : (
            <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500" />
          )}
        </span>

        <span className="flex items-center gap-1.5 font-medium">
          <Activity className="h-3.5 w-3.5 text-slate-400 group-hover:text-indigo-400 transition-colors" />
          <span>
            {allReady ? (
              <span className="text-slate-300">
                后台 <strong className="text-emerald-400">{readyCount}</strong>{' '}
                项服务静默就绪
              </span>
            ) : (
              <span className="text-amber-300">
                服务预热中 ({readyCount}/{services.length})
              </span>
            )}
          </span>
        </span>

        {noticeCount > 0 && (
          <span className="inline-flex items-center gap-1 rounded-full bg-indigo-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-300 border border-indigo-500/30">
            <Bell className="h-2.5 w-2.5 text-indigo-400" />
            {noticeCount} 条已静默
          </span>
        )}

        <ChevronRight
          className={`h-3 w-3 text-slate-500 transition-transform duration-200 ${
            isDrawerOpen ? 'rotate-90 text-indigo-400' : 'group-hover:translate-x-0.5'
          }`}
        />
      </button>

      {allReady && noticeCount === 0 && (
        <span className="hidden sm:inline-flex items-center gap-1 text-[11px] text-slate-400">
          <ShieldCheck className="h-3 w-3 text-emerald-500" />
          零阻断平滑就绪
        </span>
      )}
    </div>
  );
};
