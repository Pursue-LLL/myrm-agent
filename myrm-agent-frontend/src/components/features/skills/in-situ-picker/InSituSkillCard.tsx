/**
 * In-Situ Skill Card Component
 * 会话内就地技能卡片组件：支持一键装配、预估开销与安全检测状态
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 行数严格受控在 200 行以内；
 * 5. a11y 语义标签与交互状态。
 */

import React from 'react';
import {
  Check,
  Plus,
  ShieldAlert,
  ShieldCheck,
  Star,
  Wrench,
  Zap,
} from 'lucide-react';
import { InSituSkillDescriptor } from './inSituSkillPickerTypes';
import { useInSituSkillPickerStore } from './useInSituSkillPickerStore';

export interface InSituSkillCardProps {
  skill: InSituSkillDescriptor;
}

export const InSituSkillCard: React.FC<InSituSkillCardProps> = ({ skill }) => {
  const { toggleMountSkill, setHoveredSkillId } = useInSituSkillPickerStore();

  const handleToggle = (e: React.MouseEvent<HTMLButtonElement>): void => {
    e.stopPropagation();
    toggleMountSkill(skill.id);
  };

  return (
    <div
      data-testid={`in-situ-skill-card-${skill.id}`}
      onMouseEnter={() => {
        setHoveredSkillId(skill.id);
      }}
      onMouseLeave={() => {
        setHoveredSkillId(null);
      }}
      className={`flex flex-col justify-between rounded-lg border p-3.5 text-xs transition-all duration-200 ${
        skill.isMounted
          ? 'border-indigo-500/60 bg-indigo-950/20 shadow-sm'
          : 'border-neutral-800 bg-neutral-900/60 hover:border-neutral-700 hover:bg-neutral-900'
      }`}
    >
      {/* 头部：标题、版本、作者与安全徽标 */}
      <div>
        <div className="flex items-center justify-between gap-1.5">
          <div className="flex items-center gap-2 truncate">
            <h4 className="font-semibold text-neutral-200 truncate">
              {skill.name}
            </h4>
            <span className="rounded bg-neutral-800 px-1.5 py-0.2 text-[10px] font-mono text-neutral-400">
              v{skill.version}
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            {skill.safetyScanStatus === 'clean' ? (
              <span
                title="已通过 Myrm 原生安全沙箱与静态权限审计"
                className="flex items-center gap-0.5 text-[10px] text-emerald-400"
              >
                <ShieldCheck className="h-3 w-3" />
                <span className="hidden sm:inline">安全</span>
              </span>
            ) : (
              <span
                title="安全检测中或存在权限风险"
                className="flex items-center gap-0.5 text-[10px] text-amber-400"
              >
                <ShieldAlert className="h-3 w-3" />
                <span className="hidden sm:inline">注意</span>
              </span>
            )}
          </div>
        </div>

        {/* 描述 */}
        <p className="mt-1.5 line-clamp-2 text-[11px] text-neutral-400">
          {skill.description}
        </p>

        {/* 标签流 */}
        <div className="mt-2 flex flex-wrap items-center gap-1">
          <span className="rounded bg-indigo-950/50 px-1.5 py-0.5 text-[10px] font-medium text-indigo-300 ring-1 ring-indigo-500/30">
            {skill.category}
          </span>
          {skill.tags.map((tag) => (
            <span
              key={tag}
              className="rounded bg-neutral-800/80 px-1.5 py-0.5 text-[10px] text-neutral-400"
            >
              {tag}
            </span>
          ))}
        </div>
      </div>

      {/* 底部指标栏与挂载动作 */}
      <div className="mt-3 flex items-center justify-between border-t border-neutral-800/60 pt-2 text-neutral-500">
        <div className="flex items-center gap-2.5 text-[10px] font-mono">
          <span className="flex items-center gap-1 text-amber-400/90">
            <Star className="h-2.5 w-2.5 fill-amber-400/90" />
            <span>{skill.stars}</span>
          </span>

          <span className="flex items-center gap-1">
            <Wrench className="h-2.5 w-2.5 text-neutral-400" />
            <span>{skill.toolCount} 工具</span>
          </span>

          <span className="flex items-center gap-1">
            <Zap className="h-2.5 w-2.5 text-indigo-400" />
            <span>~{skill.estimatedTokenCost} tok</span>
          </span>
        </div>

        <button
          type="button"
          onClick={handleToggle}
          data-testid={`mount-toggle-btn-${skill.id}`}
          className={`flex items-center gap-1 rounded px-2.5 py-1 text-xs font-medium transition-all ${
            skill.isMounted
              ? 'border border-indigo-500/40 bg-indigo-950/50 text-indigo-300 hover:bg-rose-950/40 hover:text-rose-300 hover:border-rose-500/40'
              : 'bg-indigo-600 text-white hover:bg-indigo-500 shadow-sm'
          }`}
        >
          {skill.isMounted ? (
            <>
              <Check className="h-3 w-3" />
              <span>已挂载</span>
            </>
          ) : (
            <>
              <Plus className="h-3 w-3" />
              <span>+ 挂载</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
};
