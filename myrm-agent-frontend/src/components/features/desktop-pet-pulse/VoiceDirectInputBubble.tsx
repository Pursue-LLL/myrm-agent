/**
 * VoiceDirectInputBubble.tsx
 * 全局一键语音任务直通气泡：声波图标入口、实时音量波形与自动派发新任务
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Mic, MicOff, Send, X, Volume2, Sparkles } from 'lucide-react';
import { useDesktopPetPulseStore } from './useDesktopPetPulseStore';
import type { VoiceTaskDispatchPayload } from './desktopPetPulseTypes';

export interface VoiceDirectInputBubbleProps {
  className?: string;
  onDispatchTask?: (payload: VoiceTaskDispatchPayload) => void;
  onClose?: () => void;
}

export const VoiceDirectInputBubble: React.FC<VoiceDirectInputBubbleProps> = ({
  className = '',
  onDispatchTask,
  onClose,
}) => {
  const isVoiceInputActive = useDesktopPetPulseStore(
    (state) => state.isVoiceInputActive
  );
  const voiceState = useDesktopPetPulseStore((state) => state.voiceState);
  const primaryAgent = useDesktopPetPulseStore((state) => state.primaryAgent);
  const toggleVoiceInput = useDesktopPetPulseStore(
    (state) => state.toggleVoiceInput
  );
  const updateVoiceState = useDesktopPetPulseStore(
    (state) => state.updateVoiceState
  );
  const triggerDirectVoiceDispatch = useDesktopPetPulseStore(
    (state) => state.triggerDirectVoiceDispatch
  );

  const [promptText, setPromptText] = useState('');
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const stopRecording = useCallback((): void => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    updateVoiceState({
      isRecording: false,
      isTranscribing: false,
    });
  }, [updateVoiceState]);

  const startRecording = useCallback((): void => {
    updateVoiceState({
      isRecording: true,
      isTranscribing: false,
      audioLevel: 0.6,
      durationMs: 0,
      error: null,
    });

    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
    }

    timerRef.current = setInterval(() => {
      updateVoiceState({
        durationMs: (voiceState.durationMs || 0) + 200,
        audioLevel: 0.3 + Math.random() * 0.7,
      });
    }, 200);
  }, [updateVoiceState, voiceState.durationMs]);

  useEffect(() => {
    if (isVoiceInputActive && !voiceState.isRecording && promptText === '') {
      startRecording();
    }
    return () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
      }
    };
  }, [isVoiceInputActive, voiceState.isRecording, promptText, startRecording]);

  if (!isVoiceInputActive) {
    return null;
  }

  const handleClose = (): void => {
    stopRecording();
    toggleVoiceInput(false);
    if (onClose !== undefined) {
      onClose();
    }
  };

  const handleToggleRecord = (): void => {
    if (voiceState.isRecording) {
      stopRecording();
      // 模拟模拟语音转写成功
      if (promptText.trim() === '') {
        setPromptText('分析当前最新的用户反馈并生成执行计划');
      }
    } else {
      startRecording();
    }
  };

  const handleSubmit = (): void => {
    const finalPrompt = promptText.trim();
    if (finalPrompt === '') {
      return;
    }

    stopRecording();
    const payload = triggerDirectVoiceDispatch(finalPrompt, true);
    if (onDispatchTask !== undefined) {
      onDispatchTask(payload);
    }
    setPromptText('');
    toggleVoiceInput(false);
  };

  const durationSec = Math.floor(voiceState.durationMs / 1000);

  return (
    <section
      data-testid="voice-direct-input-bubble"
      aria-label="全局一键语音任务直通气泡"
      className={`absolute bottom-full mb-3 left-1/2 -translate-x-1/2 w-80 bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-2xl shadow-2xl p-3 z-50 flex flex-col gap-2.5 ${className}`}
    >
      {/* 头部标题与指派智能体提示 */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center gap-1.5">
          <Sparkles className="w-4 h-4 text-blue-400" />
          <span className="text-xs font-semibold text-slate-200">
            语音任务直通
          </span>
          <span
            className="text-[10px] px-1.5 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-800"
            title="派发目标智能体"
          >
            {primaryAgent?.name ?? '默认智能体'}
          </span>
        </div>
        <button
          type="button"
          data-testid="close-voice-bubble-btn"
          aria-label="关闭语音面板"
          onClick={handleClose}
          className="p-1 rounded-full text-slate-400 hover:text-slate-200 hover:bg-slate-800"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* 动态声波可视化条 */}
      <div
        data-testid="voice-waveform-container"
        className="h-10 bg-slate-950/60 rounded-lg flex items-center justify-center gap-1 px-3 border border-slate-800/80"
      >
        {voiceState.isRecording ? (
          <>
            <Volume2 className="w-4 h-4 text-emerald-400 animate-pulse mr-1" />
            {[0.4, 0.8, 0.5, 0.9, 0.3, 0.7, 1.0, 0.6, 0.4].map((scale, i) => (
              <span
                key={i}
                data-testid="waveform-bar"
                className="w-1 bg-emerald-500 rounded-full transition-all duration-150"
                style={{
                  height: `${Math.max(
                    6,
                    Math.round(28 * scale * voiceState.audioLevel)
                  )}px`,
                }}
              />
            ))}
            <span className="ml-2 text-[10px] font-mono text-emerald-400">
              {durationSec}s
            </span>
          </>
        ) : (
          <span className="text-xs text-slate-400">点击麦克风开始录音</span>
        )}
      </div>

      {/* 转写文本展示或输入微调框 */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor="voice-prompt-textarea"
          className="text-[11px] text-slate-400"
        >
          指令识别与微调:
        </label>
        <textarea
          id="voice-prompt-textarea"
          data-testid="voice-prompt-textarea"
          value={promptText}
          onChange={(e) => setPromptText(e.target.value)}
          placeholder="说出指令或在此输入，如：'帮我汇总今日未结工单'..."
          rows={2}
          className="w-full text-xs bg-slate-950 border border-slate-700/80 rounded-lg p-2 text-slate-200 focus:outline-none focus:border-blue-500 resize-none"
        />
      </div>

      {/* 底部动作条 */}
      <div className="flex items-center justify-between pt-1">
        <button
          type="button"
          data-testid="toggle-record-btn"
          onClick={handleToggleRecord}
          className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
            voiceState.isRecording
              ? 'bg-red-500/20 text-red-300 border-red-500/40 hover:bg-red-500/30'
              : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
          }`}
        >
          {voiceState.isRecording ? (
            <>
              <MicOff className="w-3.5 h-3.5" />
              <span>停止录音</span>
            </>
          ) : (
            <>
              <Mic className="w-3.5 h-3.5" />
              <span>重新录音</span>
            </>
          )}
        </button>

        <button
          type="button"
          data-testid="dispatch-voice-task-btn"
          disabled={promptText.trim() === ''}
          onClick={handleSubmit}
          className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed shadow-md transition-colors"
        >
          <Send className="w-3.5 h-3.5" />
          <span>直通派发</span>
        </button>
      </div>
    </section>
  );
};
