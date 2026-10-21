/**
 * TemplateBot Marketplace Modal Component
 * 预制岗位智能体模板市场大盘、一键克隆团队架构与角色开箱即用实例化弹窗
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. a11y 无障碍标准（使用原生 dialog 标签）。
 */

import React, { useEffect } from 'react';
import {
  Users,
  Search,
  Sparkles,
  Check,
  Plus,
  X,
  Layers,
  Star,
  Bot,
} from 'lucide-react';
import {
  TemplateBotRole,
  TemplateRoleCategory,
} from './templateBotTypes';
import {
  BUILT_IN_TEAM_ROSTERS,
  filterTemplateBots,
} from './templateBotCatalog';
import { useTemplateBotStore } from './useTemplateBotStore';

const CATEGORIES: readonly { id: TemplateRoleCategory | 'all'; label: string }[] = [
  { id: 'all', label: '全部分类' },
  { id: 'management', label: '统筹管理' },
  { id: 'engineering', label: '全栈工程' },
  { id: 'research', label: '深度研究' },
  { id: 'finance', label: '算力财务' },
  { id: 'operations', label: '质量可靠' },
];

export const TemplateBotMarketplaceModal: React.FC = () => {
  const {
    isMarketplaceModalOpen,
    selectedCategory,
    searchKeyword,
    instantiatedBotIds,
    setMarketplaceModalOpen,
    setSelectedCategory,
    setSearchKeyword,
    instantiateBot,
    cloneTeamRoster,
  } = useTemplateBotStore();

  // Esc 键关闭监听
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        setMarketplaceModalOpen(false);
      }
    };

    if (isMarketplaceModalOpen) {
      window.addEventListener('keydown', handleKeyDown);
    }

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isMarketplaceModalOpen, setMarketplaceModalOpen]);

  if (!isMarketplaceModalOpen) {
    return null;
  }

  const filteredBots = filterTemplateBots(
    selectedCategory === 'all' ? undefined : selectedCategory,
    searchKeyword
  );

  return (
    <dialog
      open
      data-testid="template-bot-marketplace-modal"
      aria-modal="true"
      aria-label="岗位智能体模板市场与团队克隆大盘"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 overflow-y-auto bg-transparent border-none m-0 max-w-none max-h-none w-full h-full"
    >
      {/* 遮罩背景点击层 */}
      <div
        aria-hidden="true"
        data-testid="marketplace-backdrop-overlay"
        className="fixed inset-0 bg-black/70 backdrop-blur-sm"
        onClick={() => {
          setMarketplaceModalOpen(false);
        }}
      />

      {/* 模态卡片主体 */}
      <div
        data-testid="template-bot-modal-content"
        className="relative z-10 w-full max-w-4xl rounded-2xl border border-neutral-800 bg-neutral-900 text-neutral-100 shadow-2xl p-6 space-y-5 overflow-hidden max-h-[90vh] flex flex-col"
      >
        {/* 顶部标题栏与关闭 */}
        <div className="flex items-center justify-between border-b border-neutral-800 pb-4 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/20 text-indigo-400">
              <Users className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-white">
                岗位智能体模板市场 (TemplateBot Hub)
              </h2>
              <p className="text-xs text-neutral-400 font-mono">
                开箱即用的预制岗位角色与一键克隆团队架构预设
              </p>
            </div>
          </div>

          <button
            type="button"
            data-testid="close-marketplace-modal-btn"
            onClick={() => {
              setMarketplaceModalOpen(false);
            }}
            className="rounded-lg p-1.5 text-neutral-400 hover:bg-neutral-800 hover:text-white transition-colors"
            aria-label="关闭模板市场"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* 搜索与分类 Tab 栏 */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-1 overflow-x-auto pb-1 sm:pb-0">
            {CATEGORIES.map((cat) => (
              <button
                type="button"
                key={cat.id}
                data-testid={`category-tab-${cat.id}`}
                onClick={() => {
                  setSelectedCategory(cat.id);
                }}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors whitespace-nowrap ${
                  selectedCategory === cat.id
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-neutral-400 hover:bg-neutral-800 hover:text-neutral-200'
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>

          <div className="relative w-full sm:w-64">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-neutral-400" />
            <input
              type="text"
              value={searchKeyword}
              onChange={(e) => {
                setSearchKeyword(e.target.value);
              }}
              data-testid="template-search-input"
              placeholder="搜索岗位、技能或部门..."
              className="w-full rounded-lg border border-neutral-800 bg-neutral-950 py-1.5 pl-8 pr-3 text-xs text-white placeholder-neutral-500 focus:border-indigo-500 focus:outline-none"
            />
          </div>
        </div>

        {/* 滚动主体内容 */}
        <div className="overflow-y-auto space-y-6 pr-1 flex-1">
          {/* 一键克隆团队预设板块 */}
          <div className="space-y-2.5">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-neutral-300">
              <Layers className="h-4 w-4 text-indigo-400" />
              <span>开箱即用精选团队预设 (Team Rosters)</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {BUILT_IN_TEAM_ROSTERS.map((roster) => (
                <div
                  key={roster.teamId}
                  data-testid={`team-roster-card-${roster.teamId}`}
                  className="flex flex-col justify-between rounded-xl border border-neutral-800 bg-neutral-950/60 p-3.5 space-y-3"
                >
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-[11px] font-mono">
                      <span className="rounded bg-indigo-500/20 px-1.5 py-0.5 text-indigo-300 font-bold uppercase">
                        {roster.collaborationTopology}
                      </span>
                      <span className="text-neutral-500">
                        {roster.roles.length} 个协同岗位
                      </span>
                    </div>

                    <h4 className="text-xs font-semibold text-white">
                      {roster.teamName}
                    </h4>
                    <p className="line-clamp-2 text-[11px] text-neutral-400 leading-relaxed">
                      {roster.description}
                    </p>
                  </div>

                  <button
                    type="button"
                    data-testid={`clone-team-btn-${roster.teamId}`}
                    onClick={() => {
                      cloneTeamRoster(roster.teamId);
                    }}
                    className="flex w-full items-center justify-center gap-1 rounded-lg bg-indigo-600/90 py-1.5 text-xs font-medium text-white hover:bg-indigo-600 transition-colors shadow-sm"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    <span>一键克隆团队架构</span>
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* 独立岗位智能体卡片库 */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between text-xs font-semibold text-neutral-300">
              <span className="flex items-center gap-1.5">
                <Bot className="h-4 w-4 text-cyan-400" />
                <span>独立数字员工岗位库 (Single TemplateBots)</span>
              </span>
              <span className="font-mono text-[11px] text-neutral-500">
                共 {filteredBots.length} 个角色
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
              {filteredBots.map((bot: TemplateBotRole) => {
                const isInstantiated = instantiatedBotIds.includes(bot.id);

                return (
                  <div
                    key={bot.id}
                    data-testid={`template-bot-card-${bot.id}`}
                    className="flex flex-col justify-between rounded-xl border border-neutral-800 bg-neutral-950/60 p-3.5 space-y-3"
                  >
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/20 font-mono text-[10px] font-bold text-indigo-400">
                          {bot.avatarBadge}
                        </span>
                        <div className="flex items-center gap-1 font-mono text-[10px] text-neutral-400">
                          <Star className="h-3 w-3 text-amber-400 fill-amber-400" />
                          <span>{bot.starsCount}</span>
                        </div>
                      </div>

                      <div>
                        <div className="text-xs font-semibold text-white truncate">
                          {bot.name}
                        </div>
                        <div className="text-[10px] text-neutral-500 font-mono">
                          {bot.department}
                        </div>
                      </div>

                      <p className="line-clamp-2 text-[11px] text-neutral-400 leading-relaxed">
                        {bot.summary}
                      </p>

                      <div className="flex flex-wrap gap-1 pt-0.5">
                        {bot.recommendedSkillIds.slice(0, 2).map((skillId) => (
                          <span
                            key={skillId}
                            className="rounded bg-neutral-900 border border-neutral-800 px-1.5 py-0.2 font-mono text-[9px] text-neutral-400"
                          >
                            {skillId}
                          </span>
                        ))}
                      </div>
                    </div>

                    <button
                      type="button"
                      data-testid={`instantiate-bot-btn-${bot.id}`}
                      disabled={isInstantiated}
                      onClick={() => {
                        instantiateBot(bot.id);
                      }}
                      className={`flex w-full items-center justify-center gap-1 rounded-lg py-1.5 text-xs font-medium transition-colors ${
                        isInstantiated
                          ? 'bg-neutral-800 text-emerald-400 border border-emerald-500/30'
                          : 'bg-neutral-800 hover:bg-neutral-700 text-neutral-200'
                      }`}
                    >
                      {isInstantiated ? (
                        <>
                          <Check className="h-3.5 w-3.5 text-emerald-400" />
                          <span>已实例化就绪</span>
                        </>
                      ) : (
                        <>
                          <Plus className="h-3.5 w-3.5" />
                          <span>实例化此岗位</span>
                        </>
                      )}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </dialog>
  );
};
