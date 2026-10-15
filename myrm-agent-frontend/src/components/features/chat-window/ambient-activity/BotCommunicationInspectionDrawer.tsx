import React, { useEffect, useState } from 'react';
import {
  Bot,
  Check,
  Clock,
  Copy,
  Cpu,
  Radio,
  ShieldCheck,
  X,
  Zap,
} from 'lucide-react';
import { BotActivityItem } from './ambientActivityTypes';
import { useAmbientActivityStore } from './useAmbientActivityStore';

interface BotCommunicationInspectionDrawerProps {
  className?: string;
}

export const BotCommunicationInspectionDrawer: React.FC<
  BotCommunicationInspectionDrawerProps
> = ({ className = '' }) => {
  const isOpen = useAmbientActivityStore(
    (state) => state.isInspectionDrawerOpen,
  );
  const toggleDrawer = useAmbientActivityStore(
    (state) => state.toggleInspectionDrawer,
  );
  const activitiesMap = useAmbientActivityStore((state) => state.activities);
  const selectedId = useAmbientActivityStore(
    (state) => state.selectedActivityId,
  );
  const setSelectedId = useAmbientActivityStore(
    (state) => state.setSelectedActivity,
  );

  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        toggleDrawer(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, toggleDrawer]);

  if (!isOpen) {
    return null;
  }

  const activitiesList = Object.values(activitiesMap).sort(
    (a, b) => b.timestamp - a.timestamp,
  );
  const currentItem: BotActivityItem | undefined =
    (selectedId ? activitiesMap[selectedId] : undefined) ?? activitiesList[0];

  const handleCopyPayload = () => {
    if (currentItem && currentItem.payloadSnippet) {
      void navigator.clipboard.writeText(currentItem.payloadSnippet);
      setCopied(true);
      setTimeout(() => {
        setCopied(false);
      }, 1500);
    }
  };

  return (
    <dialog
      open
      aria-label="机器协同通信信封深度审计抽屉"
      className="fixed inset-0 z-50 m-0 flex h-full w-full items-center justify-end border-0 bg-background/80 p-0 backdrop-blur-sm"
    >
      <div
        data-testid="bot-inspection-drawer"
        className={`flex h-full w-full max-w-xl flex-col border-l border-border bg-background p-5 shadow-2xl transition-all ${className}`}
      >
        {/* 顶部标题栏 */}
        <div className="flex items-center justify-between border-b border-border/50 pb-3">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <ShieldCheck className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                机器协同通信信封深度审计
              </h3>
              <p className="text-xs text-muted-foreground">
                全链路穿透可解释性 · 原始信封与开销记录
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              toggleDrawer(false);
            }}
            aria-label="关闭审计抽屉"
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* 主体双列或折叠布局 */}
        <div className="mt-4 flex flex-1 flex-col gap-4 overflow-hidden">
          {/* 左侧/上方条目横向快速切换 */}
          <div className="flex shrink-0 gap-2 overflow-x-auto pb-1">
            {activitiesList.map((act) => {
              const isSelected = currentItem?.id === act.id;
              return (
                <button
                  key={act.id}
                  type="button"
                  onClick={() => {
                    setSelectedId(act.id);
                  }}
                  className={`flex shrink-0 items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition-all ${
                    isSelected
                      ? 'border-primary bg-primary/10 font-semibold text-primary'
                      : 'border-border/60 bg-muted/20 text-muted-foreground hover:bg-muted/50'
                  }`}
                >
                  <Bot className="h-3 w-3" />
                  <span className="truncate max-w-[120px]">
                    @{act.sourceAgent} ➔ @{act.targetAgent}
                  </span>
                </button>
              );
            })}
          </div>

          {/* 详细信封报文卡片 */}
          {currentItem ? (
            <div className="flex flex-1 flex-col overflow-y-auto rounded-xl border border-border/70 bg-muted/10 p-4 text-xs">
              {/* 元数据指标栏 */}
              <div className="grid grid-cols-2 gap-2 border-b border-border/40 pb-3">
                <div className="flex items-center gap-1.5 text-muted-foreground">
                  <Clock className="h-3.5 w-3.5 text-primary" />
                  <span>耗时: {currentItem.latencyMs}ms</span>
                </div>
                <div className="flex items-center gap-1.5 text-muted-foreground">
                  <Zap className="h-3.5 w-3.5 text-amber-500" />
                  <span>Token 消耗: {currentItem.tokenCost} tok</span>
                </div>
                <div className="flex items-center gap-1.5 text-muted-foreground">
                  <Radio className="h-3.5 w-3.5 text-blue-500" />
                  <span>状态: {currentItem.status}</span>
                </div>
                <div className="flex items-center gap-1.5 text-muted-foreground">
                  <Cpu className="h-3.5 w-3.5 text-emerald-500" />
                  <span className="truncate">
                    会话: {currentItem.sessionId}
                  </span>
                </div>
              </div>

              {/* 动作描述 */}
              <div className="mt-3">
                <span className="font-medium text-foreground">
                  协作动作摘要:
                </span>
                <p className="mt-1 rounded-lg bg-background p-2 text-foreground font-mono">
                  {currentItem.actionSummary}
                </p>
              </div>

              {/* 原始报文 Payload 预览 */}
              <div className="mt-3 flex flex-1 flex-col">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-foreground">
                    原始通信信封报文 (Payload Envelope):
                  </span>
                  <button
                    type="button"
                    onClick={handleCopyPayload}
                    aria-label="复制信封报文"
                    className="flex items-center gap-1 rounded px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground"
                  >
                    {copied ? (
                      <>
                        <Check className="h-3 w-3 text-emerald-500" />
                        <span className="text-emerald-500">已复制</span>
                      </>
                    ) : (
                      <>
                        <Copy className="h-3 w-3" />
                        <span>复制</span>
                      </>
                    )}
                  </button>
                </div>

                <pre className="mt-1.5 flex-1 overflow-x-auto rounded-lg border border-border/50 bg-background/90 p-3 font-mono text-[11px] text-foreground/90 whitespace-pre-wrap">
                  {currentItem.payloadSnippet || '(空报文载荷)'}
                </pre>
              </div>
            </div>
          ) : (
            <div className="flex flex-1 items-center justify-center text-muted-foreground">
              暂无通信信封数据
            </div>
          )}
        </div>
      </div>
    </dialog>
  );
};
