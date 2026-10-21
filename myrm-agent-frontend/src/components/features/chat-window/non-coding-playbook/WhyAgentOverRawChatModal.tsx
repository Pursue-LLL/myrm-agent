import React, { useEffect } from 'react';
import {
  Check,
  CheckCircle2,
  HelpCircle,
  Shield,
  Sparkles,
  X,
  XCircle,
  Zap,
} from 'lucide-react';
import { STATIC_COMPARISON_FEATURES } from './nonCodingPlaybookEngine';
import { useNonCodingPlaybookStore } from './useNonCodingPlaybookStore';

interface WhyAgentOverRawChatModalProps {
  className?: string;
}

export const WhyAgentOverRawChatModal: React.FC<
  WhyAgentOverRawChatModalProps
> = ({ className = '' }) => {
  const isComparisonModalOpen = useNonCodingPlaybookStore(
    (state) => state.isComparisonModalOpen,
  );
  const toggleComparisonModal = useNonCodingPlaybookStore(
    (state) => state.toggleComparisonModal,
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isComparisonModalOpen) {
        toggleComparisonModal(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isComparisonModalOpen, toggleComparisonModal]);

  if (!isComparisonModalOpen) {
    return null;
  }

  return (
    <dialog
      open
      aria-label="为什么选择 Myrm AI 伙伴而不是纯网页对话框对比看板"
      className="fixed inset-0 z-50 m-0 flex h-full w-full items-center justify-center border-0 bg-background/80 p-4 backdrop-blur-md"
    >
      <div
        data-testid="why-agent-comparison-modal"
        className={`w-full max-w-2xl rounded-2xl border border-border/80 bg-background p-5 shadow-2xl ${className}`}
      >
        {/* 头部标题 */}
        <div className="flex items-center justify-between border-b border-border/40 pb-3">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                为什么选择 Myrm 协同伙伴，而不是普通网页 Chat？
              </h3>
              <p className="text-xs text-muted-foreground">
                解构真实 Agent 生产力与传统语言模型聊天室的四大本质区别
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              toggleComparisonModal(false);
            }}
            aria-label="关闭对比看板弹窗"
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* 四大核心维度对比列表 */}
        <div className="mt-3.5 max-h-[60vh] space-y-3 overflow-y-auto pr-1 text-xs">
          {STATIC_COMPARISON_FEATURES.map((feat) => (
            <div
              key={feat.id}
              className="rounded-xl border border-border/60 bg-muted/15 p-3"
            >
              <div className="flex items-center gap-1.5 font-semibold text-foreground">
                <Shield className="h-3.5 w-3.5 text-primary" />
                <span>{feat.title}</span>
              </div>

              <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                {/* 传统纯网页 Chat */}
                <div className="rounded-lg border border-border/40 bg-background/60 p-2.5">
                  <div className="flex items-center gap-1 font-medium text-muted-foreground">
                    <XCircle className="h-3.5 w-3.5 text-rose-500/80" />
                    <span>普通网页 Chat</span>
                  </div>
                  <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                    {feat.rawWebChat}
                  </p>
                </div>

                {/* Myrm Agent 伙伴 */}
                <div className="rounded-lg border border-primary/30 bg-primary/5 p-2.5">
                  <div className="flex items-center gap-1 font-medium text-primary">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                    <span>Myrm 协同 Agent</span>
                  </div>
                  <p className="mt-1 text-[11px] leading-relaxed text-foreground/90 font-medium">
                    {feat.myrmAgent}
                  </p>
                </div>
              </div>

              <div className="mt-2 rounded bg-muted/40 px-2 py-1 text-[10px] text-muted-foreground border border-border/30">
                <span className="font-medium text-foreground/80">业务实操收益: </span>
                {feat.advantageDetail}
              </div>
            </div>
          ))}
        </div>

        {/* 底部关闭按钮 */}
        <div className="mt-4 flex items-center justify-end border-t border-border/40 pt-3">
          <button
            type="button"
            onClick={() => {
              toggleComparisonModal(false);
            }}
            className="rounded-lg bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            我明白了，立即开始体验
          </button>
        </div>
      </div>
    </dialog>
  );
};
