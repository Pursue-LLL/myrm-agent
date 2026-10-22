import React, { useState } from 'react';
import {
  Mic,
  MicOff,
  Sparkles,
  Bot,
  Play,
  RotateCcw,
  FastForward,
} from 'lucide-react';
import { usePetSpeechLoopStore } from './usePetSpeechLoopStore';
import { PetLoopStageBadge } from './PetLoopStageBadge';
import { MiniApprovalDrawer } from './MiniApprovalDrawer';

export interface PetSpeechLoopOverlayProps {
  className?: string;
}

export const PetSpeechLoopOverlay: React.FC<PetSpeechLoopOverlayProps> = ({
  className = '',
}) => {
  const {
    currentPhase,
    voiceStatus,
    transcript,
    interimTranscript,
    steps,
    petMood,
    bubbleMessage,
    isWiggling,
    startVoiceCapture,
    stopVoiceCapture,
    feedVoiceInput,
    advanceToNextPhase,
    reset,
  } = usePetSpeechLoopStore();

  const [inputSimText, setInputSimText] = useState('');

  const isCapturing = voiceStatus === 'listening';

  const handleToggleVoice = () => {
    if (isCapturing) {
      stopVoiceCapture();
    } else {
      startVoiceCapture();
    }
  };

  const handleSimulateVoiceSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputSimText.trim()) {
      return;
    }
    feedVoiceInput(inputSimText, true);
    setInputSimText('');
  };

  return (
    <div
      data-testid="pet-speech-loop-overlay"
      className={`relative inline-flex flex-col items-center select-none font-sans ${className}`}
    >
      {/* 1. 头顶实时对话气泡 */}
      {(bubbleMessage || interimTranscript) && (
        <div
          data-testid="pet-speech-bubble"
          className="mb-2 max-w-xs px-3 py-2 rounded-2xl bg-zinc-900/95 border border-indigo-500/40 shadow-xl backdrop-blur-md text-xs text-zinc-100 animate-bounce-subtle"
        >
          <div className="flex items-center gap-1.5 font-medium">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
            <span className="leading-relaxed">
              {interimTranscript ? `听取中: "${interimTranscript}"` : bubbleMessage}
            </span>
          </div>
          {/* 气泡小箭头 */}
          <div className="absolute left-1/2 -bottom-1.5 -translate-x-1/2 w-3 h-3 bg-zinc-900 border-r border-b border-indigo-500/40 rotate-45" />
        </div>
      )}

      {/* 2. 四阶流水线状态胶囊 (Plan-Code-Exec-Verify) */}
      {steps.length > 0 && (
        <div className="mb-2">
          <PetLoopStageBadge steps={steps} />
        </div>
      )}

      {/* 3. 桌宠本体卡片与交互底座 */}
      <div className="relative flex flex-col items-center">
        {/* 桌宠外圈微发光与动效 */}
        <div
          data-testid="pet-sprite-container"
          className={`relative p-3 rounded-full bg-zinc-900/90 border border-zinc-700/80 shadow-2xl backdrop-blur-md transition-all ${
            isWiggling ? 'animate-wiggle' : ''
          } ${
            isCapturing
              ? 'ring-4 ring-indigo-500/40 border-indigo-500 animate-pulse'
              : ''
          }`}
        >
          {/* 桌宠形象图标 */}
          <div
            className={`w-12 h-12 rounded-full flex items-center justify-center transition-colors ${
              petMood === 'celebrating'
                ? 'bg-emerald-500/20 text-emerald-400'
                : petMood === 'thinking'
                  ? 'bg-amber-500/20 text-amber-400'
                  : petMood === 'coding'
                    ? 'bg-cyan-500/20 text-cyan-400'
                    : isCapturing
                      ? 'bg-indigo-600/30 text-indigo-300'
                      : 'bg-zinc-800 text-zinc-300'
            }`}
          >
            <Bot className="w-7 h-7" />
          </div>

          {/* 麦克风快捷呼唤悬浮按钮 */}
          <button
            type="button"
            onClick={handleToggleVoice}
            aria-label={isCapturing ? '停止语音倾听' : '开启语音免打字唤醒'}
            className={`absolute -bottom-1 -right-1 p-1.5 rounded-full shadow-lg transition-transform hover:scale-110 ${
              isCapturing
                ? 'bg-rose-500 text-white animate-pulse'
                : 'bg-indigo-600 hover:bg-indigo-500 text-white'
            }`}
          >
            {isCapturing ? (
              <MicOff className="w-3.5 h-3.5" />
            ) : (
              <Mic className="w-3.5 h-3.5" />
            )}
          </button>
        </div>

        {/* 状态情绪标签 */}
        <span className="mt-1 text-[10px] font-mono font-medium text-zinc-400">
          [{petMood.toUpperCase()}] {currentPhase}
        </span>
      </div>

      {/* 4. 快捷控制与免打字模拟工具条 (针对非麦克风输入与自动化单步推演) */}
      <div className="mt-3 flex flex-col items-center gap-1.5">
        <form
          onSubmit={handleSimulateVoiceSubmit}
          className="flex items-center gap-1.5"
        >
          <input
            type="text"
            value={inputSimText}
            onChange={(e) => {
              setInputSimText(e.target.value);
            }}
            placeholder="对着桌宠说点什么…"
            className="w-48 px-2.5 py-1 text-xs rounded-xl bg-zinc-950/80 border border-zinc-800 text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-indigo-500"
          />
          <button
            type="submit"
            aria-label="发送语音模拟指令"
            className="p-1 px-2 rounded-xl bg-zinc-800 hover:bg-indigo-600 text-zinc-200 hover:text-white text-xs font-semibold transition-colors flex items-center gap-1"
          >
            <Play className="w-3 h-3" />
            <span>说出</span>
          </button>
        </form>

        {currentPhase !== 'idle' && (
          <div className="flex items-center gap-1 text-[11px] font-mono">
            <button
              type="button"
              onClick={advanceToNextPhase}
              className="flex items-center gap-1 px-2 py-0.5 rounded-lg bg-zinc-900 border border-zinc-800 hover:border-zinc-700 text-indigo-400 transition-colors"
            >
              <FastForward className="w-3 h-3" />
              <span>推进一步</span>
            </button>
            <button
              type="button"
              onClick={reset}
              className="flex items-center gap-1 px-2 py-0.5 rounded-lg bg-zinc-900 border border-zinc-800 hover:border-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              <RotateCcw className="w-3 h-3" />
              <span>重置</span>
            </button>
          </div>
        )}
      </div>

      {/* 5. 侧边微型拍板抽屉挂载 */}
      <MiniApprovalDrawer />
    </div>
  );
};
