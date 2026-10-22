import React from 'react';
import {
  Lock,
  Users,
  ChevronDown,
  ShieldCheck,
  Check,
  Building,
  HardDrive,
  Sparkles,
} from 'lucide-react';
import { useWorkspaceScopeStore } from './useWorkspaceScopeStore';
import type { TeamWorkspaceEntity, WorkspaceScope } from './workspaceScopeTypes';

export const WorkspaceScopeSwitcher: React.FC = () => {
  const {
    currentScope,
    activeTeamId,
    teams,
    isScopeDropdownOpen,
    lastIsolationAudit,
    switchScope,
    toggleDropdown,
  } = useWorkspaceScopeStore();

  const activeTeam = teams.find((t) => t.id === activeTeamId) ?? teams[0];

  const handleSelectPersonal = (): void => {
    switchScope('personal');
  };

  const handleSelectTeam = (team: TeamWorkspaceEntity): void => {
    switchScope('team', team.id);
  };

  return (
    <div className="relative inline-block text-left text-slate-100">
      {/* 顶部常驻穿梭触发按钮 */}
      <button
        type="button"
        onClick={() => toggleDropdown()}
        aria-haspopup="true"
        aria-expanded={isScopeDropdownOpen}
        className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium transition-all rounded-lg border bg-slate-900/90 hover:bg-slate-800 border-slate-800 hover:border-slate-700 text-slate-200 hover:text-white shadow-sm"
      >
        {currentScope === 'personal' ? (
          <>
            <span className="p-1 rounded bg-sky-500/10 text-sky-400 border border-sky-500/20">
              <Lock className="w-3.5 h-3.5" />
            </span>
            <span className="font-semibold text-white">个人私有空间</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
              本地沙箱
            </span>
          </>
        ) : (
          <>
            <span className="p-1 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <Users className="w-3.5 h-3.5" />
            </span>
            <span className="font-semibold text-white truncate max-w-[140px]">
              {activeTeam?.name ?? '团队协同'}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800">
              云端企业
            </span>
          </>
        )}
        <ChevronDown
          className={`w-3.5 h-3.5 text-slate-400 transition-transform duration-150 ${
            isScopeDropdownOpen ? 'rotate-180' : ''
          }`}
        />
      </button>

      {/* 穿梭下拉浮层 */}
      {isScopeDropdownOpen && (
        <div
          role="menu"
          aria-orientation="vertical"
          className="absolute left-0 z-50 w-72 mt-2 origin-top-left border rounded-xl shadow-2xl bg-slate-900 border-slate-800 p-2 space-y-2 animate-in fade-in zoom-in-95 duration-100"
        >
          {/* 选项组 1：个人私有独立沙箱 */}
          <div className="space-y-1">
            <span className="px-2.5 py-1 text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
              独立安全环境
            </span>
            <button
              type="button"
              role="menuitem"
              onClick={handleSelectPersonal}
              className={`w-full flex items-start gap-2.5 p-2.5 rounded-lg text-left transition-colors ${
                currentScope === 'personal'
                  ? 'bg-sky-950/40 border border-sky-500/30 text-white'
                  : 'hover:bg-slate-800/80 text-slate-300'
              }`}
            >
              <div className="p-1.5 rounded-md bg-sky-500/10 text-sky-400 border border-sky-500/20 shrink-0 mt-0.5">
                <HardDrive className="w-4 h-4" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-white">个人私有工作空间</span>
                  {currentScope === 'personal' && (
                    <Check className="w-3.5 h-3.5 text-sky-400" />
                  )}
                </div>
                <p className="mt-0.5 text-[11px] text-slate-400 leading-tight">
                  直连本机独立磁盘沙箱，私有知识库与密钥严格隔离。
                </p>
              </div>
            </button>
          </div>

          {/* 选项组 2：团队协同企业沙箱 */}
          <div className="pt-2 border-t border-slate-800/80 space-y-1">
            <span className="px-2.5 py-1 text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
              团队协同空间 (Control Plane)
            </span>
            {teams.map((team) => {
              const isTeamActive = currentScope === 'team' && activeTeamId === team.id;
              return (
                <button
                  key={team.id}
                  type="button"
                  role="menuitem"
                  onClick={() => handleSelectTeam(team)}
                  className={`w-full flex items-start gap-2.5 p-2.5 rounded-lg text-left transition-colors ${
                    isTeamActive
                      ? 'bg-indigo-950/40 border border-indigo-500/30 text-white'
                      : 'hover:bg-slate-800/80 text-slate-300'
                  }`}
                >
                  <div className="p-1.5 rounded-md bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shrink-0 mt-0.5">
                    <Building className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-white truncate">
                        {team.name}
                      </span>
                      {isTeamActive && (
                        <Check className="w-3.5 h-3.5 text-indigo-400" />
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-1 text-[10px] text-slate-400">
                      <span>{team.memberCount} 位成员</span>
                      <span>•</span>
                      <span className="capitalize">{team.role}</span>
                      <span>•</span>
                      <span>{team.sharedProjectsCount} 个共享项目</span>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          {/* 底部零泄露硬隔离徽章 */}
          <div className="p-2 border-t border-slate-800/80 bg-slate-950/40 rounded-b-lg">
            <div className="flex items-center gap-1.5 text-[10px] text-emerald-400 font-medium">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Zero-Leak 硬隔离看门狗已生效</span>
            </div>
            <p className="mt-0.5 text-[10px] text-slate-500 leading-tight">
              切换空间时瞬时清空临时会话流并锁定私密 Key，杜绝代码泄露。
            </p>
            {lastIsolationAudit && (
              <div className="mt-1 text-[9px] font-mono text-slate-500">
                最近隔离审计: {new Date(lastIsolationAudit.switchedAt).toLocaleTimeString()} · 状态正常
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
