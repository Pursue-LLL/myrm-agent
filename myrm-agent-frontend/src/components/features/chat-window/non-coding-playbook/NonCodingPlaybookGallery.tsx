import React from 'react';
import {
  ArrowRight,
  FileSpreadsheet,
  FileText,
  Filter,
  HelpCircle,
  Layers,
  Search,
  Sparkles,
  Zap,
} from 'lucide-react';
import {
  filterPlaybooksByCategory,
  getCategoryMeta,
  searchPlaybooks,
} from './nonCodingPlaybookEngine';
import { PlaybookCategory, PlaybookScenario } from './nonCodingPlaybookTypes';
import { useNonCodingPlaybookStore } from './useNonCodingPlaybookStore';

interface NonCodingPlaybookGalleryProps {
  onSelectScenario?: (scenario: PlaybookScenario) => void;
  className?: string;
}

const CATEGORY_TABS: Array<{ id: PlaybookCategory | 'all'; label: string }> = [
  { id: 'all', label: '全部场景' },
  { id: 'finance', label: '财务发票' },
  { id: 'admin', label: '行政办公' },
  { id: 'research', label: '研报分析' },
  { id: 'legal', label: '合同法务' },
  { id: 'content', label: '媒体创作' },
  { id: 'general', label: '通用统揽' },
];

export const NonCodingPlaybookGallery: React.FC<
  NonCodingPlaybookGalleryProps
> = ({ onSelectScenario, className = '' }) => {
  const scenarios = useNonCodingPlaybookStore((state) => state.scenarios);
  const selectedCategory = useNonCodingPlaybookStore(
    (state) => state.selectedCategory,
  );
  const searchKeyword = useNonCodingPlaybookStore(
    (state) => state.searchKeyword,
  );
  const setSelectedCategory = useNonCodingPlaybookStore(
    (state) => state.setSelectedCategory,
  );
  const setSearchKeyword = useNonCodingPlaybookStore(
    (state) => state.setSearchKeyword,
  );
  const openScenarioModal = useNonCodingPlaybookStore(
    (state) => state.openScenarioModal,
  );
  const toggleComparisonModal = useNonCodingPlaybookStore(
    (state) => state.toggleComparisonModal,
  );

  const categoryFiltered = filterPlaybooksByCategory(
    scenarios,
    selectedCategory,
  );
  const finalFiltered = searchPlaybooks(categoryFiltered, searchKeyword);

  const handleCardClick = (scenario: PlaybookScenario) => {
    openScenarioModal(scenario);
    if (onSelectScenario) {
      onSelectScenario(scenario);
    }
  };

  return (
    <div
      data-testid="non-coding-playbook-gallery"
      className={`w-full rounded-2xl border border-border/60 bg-background/95 p-4 shadow-sm backdrop-blur-md ${className}`}
    >
      {/* 头部导航与 Agent 优势引导栏 */}
      <div className="flex flex-col gap-3 pb-4 sm:flex-row sm:items-center sm:justify-between border-b border-border/40">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Layers className="h-3.5 w-3.5" />
            </div>
            <h3 className="text-sm font-semibold text-foreground">
              非编码日常任务工作流画廊
            </h3>
            <span className="rounded bg-primary/15 px-1.5 py-0.5 text-[10px] font-medium text-primary">
              开箱即用向导
            </span>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            告别空白输入框提问焦虑，选择真实办公场景，一键装填执行专属工作流
          </p>
        </div>

        <button
          type="button"
          onClick={() => {
            toggleComparisonModal(true);
          }}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border/70 bg-muted/40 px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted"
        >
          <HelpCircle className="h-3.5 w-3.5 text-primary" />
          <span>与网页 Chat 相比有何优势？</span>
        </button>
      </div>

      {/* 分类标签栏与搜索栏 */}
      <div className="mt-3 flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          {CATEGORY_TABS.map((tab) => {
            const isActive = selectedCategory === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => {
                  setSelectedCategory(tab.id);
                }}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-primary text-primary-foreground shadow-xs'
                    : 'bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground'
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>

        <div className="relative w-full sm:w-60">
          <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
          <input
            type="text"
            value={searchKeyword}
            onChange={(e) => {
              setSearchKeyword(e.target.value);
            }}
            placeholder="搜索日常任务、工具或产出..."
            className="h-7 w-full rounded-md border border-border/60 bg-background pl-8 pr-2 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-hidden focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      {/* 场景卡片网格 */}
      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {finalFiltered.map((scenario) => {
          const catMeta = getCategoryMeta(scenario.category);

          return (
            <div
              key={scenario.id}
              data-testid={`scenario-card-${scenario.id}`}
              className="flex flex-col justify-between rounded-xl border border-border/60 bg-muted/10 p-3.5 transition-all hover:border-primary/40 hover:bg-muted/20 hover:shadow-xs"
            >
              <div>
                <div className="flex items-center justify-between gap-1.5">
                  <span
                    className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${catMeta.badgeClass}`}
                  >
                    {catMeta.label}
                  </span>
                  {scenario.starsCount && (
                    <span className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
                      <Sparkles className="h-2.5 w-2.5 text-amber-500" />
                      {scenario.starsCount} 人常用
                    </span>
                  )}
                </div>

                <h4 className="mt-2 text-xs font-semibold text-foreground">
                  {scenario.title}
                </h4>
                <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
                  {scenario.description}
                </p>

                {/* 执行流程流水线微展示 */}
                <div className="mt-2.5 rounded-lg bg-background/70 p-2 border border-border/30">
                  <span className="block text-[10px] font-medium text-foreground/80 mb-1">
                    执行蓝图流水线:
                  </span>
                  <div className="space-y-1">
                    {scenario.pipelineFlow.slice(0, 3).map((flow, idx) => (
                      <div
                        key={flow}
                        className="flex items-center gap-1.5 text-[10px] text-muted-foreground"
                      >
                        <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full bg-primary/10 font-mono text-[9px] text-primary">
                          {idx + 1}
                        </span>
                        <span className="truncate">{flow}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* 预期成果 */}
                <div className="mt-2 flex items-center gap-1 text-[10px] text-muted-foreground">
                  <FileSpreadsheet className="h-3 w-3 shrink-0 text-emerald-500" />
                  <span className="truncate">成果: {scenario.expectedOutput}</span>
                </div>
              </div>

              {/* 底部启动配置按钮 */}
              <div className="mt-3.5 pt-2 border-t border-border/30">
                <button
                  type="button"
                  onClick={() => {
                    handleCardClick(scenario);
                  }}
                  className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-primary/10 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary hover:text-primary-foreground"
                >
                  <Zap className="h-3 w-3" />
                  <span>一键配置并装填执行</span>
                  <ArrowRight className="h-3 w-3" />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {finalFiltered.length === 0 && (
        <div className="my-8 text-center text-xs text-muted-foreground">
          未检索到符合条件的日常非编码工作流，请尝试更换关键词或分类。
        </div>
      )}
    </div>
  );
};
