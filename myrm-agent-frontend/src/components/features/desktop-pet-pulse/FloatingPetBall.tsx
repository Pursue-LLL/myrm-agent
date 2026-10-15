/**
 * FloatingPetBall.tsx
 * 桌面微型悬浮桌宠主控球：实时脉冲光晕、智能体身份投影、多智能体轻量堆叠徽标与快捷唤醒
 */

import React, { useMemo } from 'react';
import {
  Activity,
  AlertOctagon,
  ArrowDownCircle,
  CheckCircle2,
  Mic,
  Pause,
  Play,
  ShieldAlert,
  Sparkles,
} from 'lucide-react';
import {
  computeStackedAgentBadges,
  derivePetVisualConfig,
} from './desktopPetPulseEngine';
import { useDesktopPetPulseStore } from './useDesktopPetPulseStore';

export interface FloatingPetBallProps {
  className?: string;
  onDoubleClick?: () => void;
  onVoiceClick?: () => void;
  onMigrationClick?: () => void;
}

export const FloatingPetBall: React.FC<FloatingPetBallProps> = ({
  className = '',
  onDoubleClick,
  onVoiceClick,
  onMigrationClick,
}) => {
  const petStatus = useDesktopPetPulseStore((state) => state.petStatus);
  const isPaused = useDesktopPetPulseStore((state) => state.isPaused);
  const activeApproval = useDesktopPetPulseStore((state) => state.activeApproval);
  const primaryAgent = useDesktopPetPulseStore((state) => state.primaryAgent);
  const allAgents = useDesktopPetPulseStore((state) => state.allAgents);
  const activeQueue = useDesktopPetPulseStore((state) => state.activeQueue);
  const isQuickActionOpen = useDesktopPetPulseStore(
    (state) => state.isQuickActionOpen
  );
  const togglePause = useDesktopPetPulseStore((state) => state.togglePause);
  const toggleQuickAction = useDesktopPetPulseStore(
    (state) => state.toggleQuickAction
  );
  const toggleVoiceInput = useDesktopPetPulseStore(
    (state) => state.toggleVoiceInput
  );
  const toggleMigrationModal = useDesktopPetPulseStore(
    (state) => state.toggleMigrationModal
  );
  const requestOpenMainWindow = useDesktopPetPulseStore(
    (state) => state.requestOpenMainWindow
  );

  const visualConfig = useMemo(() => {
    return derivePetVisualConfig(
      petStatus,
      activeApproval !== null,
      petStatus === 'error'
    );
  }, [petStatus, activeApproval]);

  const stackedBadges = useMemo(() => {
    return computeStackedAgentBadges(
      primaryAgent !== null ? primaryAgent.agentId : null,
      allAgents,
      activeQueue
    );
  }, [primaryAgent, allAgents, activeQueue]);

  const handleBallDoubleClick = (): void => {
    requestOpenMainWindow();
    if (onDoubleClick !== undefined) {
      onDoubleClick();
    }
  };

  const handleVoiceButtonClick = (e: React.MouseEvent): void => {
    e.stopPropagation();
    toggleVoiceInput();
    if (onVoiceClick !== undefined) {
      onVoiceClick();
    }
  };

  const handleMigrationButtonClick = (e: React.MouseEvent): void => {
    e.stopPropagation();
    toggleMigrationModal(true);
    if (onMigrationClick !== undefined) {
      onMigrationClick();
    }
  };

  const handlePauseButtonClick = (e: React.MouseEvent): void => {
    e.stopPropagation();
    togglePause();
  };

  const renderExpressionIcon = (): React.ReactElement => {
    switch (visualConfig.expression) {
      case 'concerned': {
        return <AlertOctagon className="w-5 h-5 text-red-400" />;
      }
      case 'alert_shake': {
        return <ShieldAlert className="w-5 h-5 text-amber-400 animate-bounce" />;
      }
      case 'celebrate': {
        return <CheckCircle2 className="w-5 h-5 text-emerald-400" />;
      }
      case 'focused': {
        return <Activity className="w-5 h-5 text-emerald-400 animate-spin" />;
      }
      case 'pulsing': {
        return <Sparkles className="w-5 h-5 text-blue-400 animate-pulse" />;
      }
      case 'calm':
      default: {
        return <Sparkles className="w-5 h-5 text-slate-300" />;
      }
    }
  };

  return (
    <section
      data-testid="desktop-floating-pet-ball"
      aria-label="桌面微型悬浮桌宠"
      className={`relative inline-flex flex-col items-center select-none ${className}`}
    >
      {/* 呼吸光晕底座 */}
      <div
        data-testid="pet-halo-ring"
        className="absolute -inset-2 rounded-full transition-all duration-700 pointer-events-none"
        style={{
          boxShadow: `0 0 24px 6px ${visualConfig.haloColor}`,
          opacity: isPaused ? 0.2 : 0.85,
        }}
      />

      {/* 悬浮球主体 */}
      <button
        type="button"
        data-testid="pet-main-avatar-button"
        aria-label={`智能体桌宠: ${primaryAgent?.name ?? '就绪'}, 状态: ${visualConfig.badgeLabel}`}
        onClick={() => toggleQuickAction()}
        onDoubleClick={handleBallDoubleClick}
        className="relative w-14 h-14 rounded-full bg-slate-900 border-2 border-slate-700/80 shadow-2xl flex items-center justify-center cursor-pointer hover:scale-105 active:scale-95 transition-transform"
        style={{
          borderColor: primaryAgent?.colorTheme ?? '#3b82f6',
        }}
      >
        {renderExpressionIcon()}

        {/* 暂停状态遮罩小标 */}
        {isPaused && (
          <span
            data-testid="pet-paused-indicator"
            className="absolute inset-0 bg-slate-950/70 rounded-full flex items-center justify-center"
          >
            <Pause className="w-4 h-4 text-amber-400" />
          </span>
        )}

        {/* 多智能体堆叠徽标 */}
        {stackedBadges.length > 0 && (
          <span
            data-testid="pet-stacked-agent-badge"
            className="absolute -top-1 -right-1 px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-blue-600 text-white border border-slate-900 shadow-md flex items-center justify-center"
            title={`并发智能体队列: ${stackedBadges.map((b) => b.name).join(', ')}`}
          >
            +{stackedBadges.length}
          </span>
        )}
      </button>

      {/* 智能体身份微型标签 */}
      <div
        data-testid="pet-identity-capsule"
        className="mt-1.5 px-2 py-0.5 rounded-full bg-slate-900/90 border border-slate-700/60 shadow-lg flex items-center gap-1 max-w-[120px]"
      >
        <span
          className="w-1.5 h-1.5 rounded-full shrink-0"
          style={{
            backgroundColor: primaryAgent?.colorTheme ?? '#3b82f6',
          }}
        />
        <span className="text-[11px] font-medium text-slate-200 truncate">
          {primaryAgent?.name ?? 'Myrm'}
        </span>
      </div>

      {/* 快捷悬停/伴随快捷工具条 */}
      <div
        data-testid="pet-quick-toolbar"
        className="mt-1 flex items-center gap-1 bg-slate-900/80 p-0.5 rounded-full border border-slate-800"
      >
        <button
          type="button"
          data-testid="pet-voice-shortcut-btn"
          aria-label="一键开启语音任务直通"
          onClick={handleVoiceButtonClick}
          className="p-1 rounded-full text-slate-400 hover:text-blue-400 hover:bg-slate-800 transition-colors"
          title="点击开启语音任务直通"
        >
          <Mic className="w-3.5 h-3.5" />
        </button>

        <button
          type="button"
          data-testid="pet-pause-shortcut-btn"
          aria-label={isPaused ? '恢复执行' : '暂停执行'}
          onClick={handlePauseButtonClick}
          className="p-1 rounded-full text-slate-400 hover:text-amber-400 hover:bg-slate-800 transition-colors"
          title={isPaused ? '恢复任务' : '一键暂停'}
        >
          {isPaused ? (
            <Play className="w-3.5 h-3.5" />
          ) : (
            <Pause className="w-3.5 h-3.5" />
          )}
        </button>

        <button
          type="button"
          data-testid="pet-migration-shortcut-btn"
          aria-label="打开数据平滑迁移中心"
          onClick={handleMigrationButtonClick}
          className="p-1 rounded-full text-slate-400 hover:text-emerald-400 hover:bg-slate-800 transition-colors"
          title="数据无感平滑迁移"
        >
          <ArrowDownCircle className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* 快速提示微文本 */}
      {isQuickActionOpen && (
        <span
          data-testid="pet-quick-open-tag"
          className="sr-only"
        >
          快捷抽屉已展开
        </span>
      )}
    </section>
  );
};
