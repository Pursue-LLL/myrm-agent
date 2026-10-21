import React, { useState } from 'react';
import {
  Mic,
  Bot,
  Sparkles,
  Volume2,
} from 'lucide-react';
import { useFloatingPetStore } from './useFloatingPetStore';
import {
  calculateDockPositionClasses,
  getPetGlowStyle,
} from './floatingPetEngine';
import { MiniTaskBubble } from './MiniTaskBubble';

export interface CompanionFloatingPetProps {
  onOpenMainWindow?: (taskId: string) => void;
  className?: string;
}

export const CompanionFloatingPet: React.FC<CompanionFloatingPetProps> = ({
  onOpenMainWindow,
  className = '',
}) => {
  const {
    mood,
    position,
    isVoiceRecording,
    activeTask,
    isBubbleExpanded,
    startPushToTalk,
    stopPushToTalk,
    toggleBubbleExpanded,
  } = useFloatingPetStore();

  const [simulatedVoiceInput, setSimulatedVoiceInput] = useState('');

  const glowStyle = getPetGlowStyle(mood);
  const positionClass = calculateDockPositionClasses(position);

  const handlePointerDown = () => {
    startPushToTalk();
  };

  const handlePointerUp = () => {
    // 模拟或真实松手，如果未提供特定语音输入，传入默认示例以触发长任务发射
    const transcript =
      simulatedVoiceInput || '帮做一个书画作品定制的报价工具，自动计算价格并保存记录';
    stopPushToTalk(transcript);
    setSimulatedVoiceInput('');
  };

  const handleClickBall = () => {
    if (!isVoiceRecording) {
      toggleBubbleExpanded();
    }
  };

  return (
    <div
      data-testid="companion-floating-pet"
      className={`fixed z-50 select-none ${positionClass} ${className}`}
    >
      {/* 迷你进度气泡 (依附在挂件侧边) */}
      <MiniTaskBubble onOpenMainWindow={onOpenMainWindow} />

      {/* 桌宠灵动球体本体 */}
      <div className="relative group">
        {/* 外层状态呼吸光环 (Micro-Status Ring) */}
        <div
          className={`absolute -inset-1.5 rounded-full border-2 transition-all duration-300 pointer-events-none ${glowStyle.ringColor}`}
        />

        {/* 核心交互按钮 */}
        <button
          type="button"
          onClick={handleClickBall}
          onMouseDown={handlePointerDown}
          onMouseUp={handlePointerUp}
          onTouchStart={handlePointerDown}
          onTouchEnd={handlePointerUp}
          title={
            isVoiceRecording
              ? '松开发射任务'
              : '长按说话发起任务，单击展开状态'
          }
          aria-label="桌面伴随灵动挂件"
          className="relative w-14 h-14 rounded-full bg-zinc-900 border border-zinc-700/80 shadow-2xl flex flex-col items-center justify-center cursor-pointer active:scale-95 hover:scale-105 transition-all overflow-hidden focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
        >
          {isVoiceRecording ? (
            <div className="flex flex-col items-center justify-center text-red-400 animate-pulse">
              <Mic className="w-6 h-6 animate-bounce" />
              <div className="flex gap-0.5 mt-0.5">
                <span className="w-1 h-2 bg-red-400 rounded-full animate-ping" />
                <span className="w-1 h-3 bg-red-400 rounded-full animate-pulse" />
                <span className="w-1 h-2 bg-red-400 rounded-full animate-ping" />
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center text-zinc-200">
              {mood === 'celebrating' ? (
                <Sparkles className="w-6 h-6 text-amber-400 animate-bounce" />
              ) : mood === 'working' ? (
                <Volume2 className="w-6 h-6 text-cyan-400 animate-pulse" />
              ) : (
                <Bot className="w-6 h-6 text-indigo-400 group-hover:rotate-12 transition-transform" />
              )}
            </div>
          )}
        </button>

        {/* 状态徽标 (悬浮或任务中显示) */}
        {activeTask && (
          <div
            className={`absolute -bottom-2 left-1/2 -translate-x-1/2 px-1.5 py-0.2 rounded-full text-[9px] font-mono border whitespace-nowrap shadow-sm pointer-events-none ${glowStyle.badgeBg} ${glowStyle.badgeText}`}
          >
            {activeTask.progress}%
          </div>
        )}
      </div>
    </div>
  );
};
