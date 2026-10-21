import React, { useState } from 'react';
import {
  Mic,
  MicOff,
  Sparkles,
  Send,
  RotateCcw,
  BookOpen,
  Undo2,
  CheckCircle2,
  Code2,
} from 'lucide-react';
import { useSpeechBiasStore } from './useSpeechBiasStore';
import { CorrectionRecord } from './speechBiasTypes';

export interface VoiceDevConfirmCardProps {
  onConfirmSend?: (finalText: string) => void;
  onCancel?: () => void;
  className?: string;
}

export const VoiceDevConfirmCard: React.FC<VoiceDevConfirmCardProps> = ({
  onConfirmSend,
  onCancel,
  className = '',
}) => {
  const {
    status,
    rawTranscript,
    correctedTranscript,
    activeCorrections,
    isAutoCorrectEnabled,
    startListening,
    finalizeTranscript,
    revertCorrection,
    toggleAutoCorrect,
    setDrawerOpen,
    reset,
  } = useSpeechBiasStore();

  const [isEditing, setIsEditing] = useState(false);
  const [editedText, setEditedText] = useState('');

  const handleStartRecording = () => {
    setIsEditing(false);
    startListening();
  };

  const handleStopRecording = () => {
    finalizeTranscript();
  };

  const handleStartEdit = () => {
    setEditedText(correctedTranscript || rawTranscript);
    setIsEditing(true);
  };

  const handleSaveEdit = () => {
    setIsEditing(false);
    finalizeTranscript(editedText);
  };

  const handleSend = () => {
    const textToSend = isEditing ? editedText : (correctedTranscript || rawTranscript);
    if (!textToSend || textToSend.trim() === '') {
      return;
    }
    if (onConfirmSend) {
      onConfirmSend(textToSend);
    }
    reset();
  };

  const handleCancel = () => {
    reset();
    if (onCancel) {
      onCancel();
    }
  };

  const renderStatusBadge = () => {
    if (status === 'listening') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20 animate-pulse">
          <span className="w-2 h-2 rounded-full bg-red-500 animate-ping" />
          正在录音听写...
        </span>
      );
    }
    if (status === 'correcting') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
          <Sparkles className="w-3.5 h-3.5 animate-spin" />
          声学与上下文术语纠偏中...
        </span>
      );
    }
    if (status === 'ready') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <CheckCircle2 className="w-3.5 h-3.5" />
          纠偏完毕 · 可直接发送
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-zinc-800 text-zinc-400 border border-zinc-700">
        就绪
      </span>
    );
  };

  return (
    <div
      data-testid="voice-dev-confirm-card"
      className={`relative w-full rounded-xl border border-zinc-700/80 bg-zinc-900/95 backdrop-blur-md p-4 shadow-2xl transition-all ${className}`}
    >
      {/* 头部状态与设置栏 */}
      <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Mic className="w-4 h-4" />
          </div>
          <span className="text-sm font-semibold text-zinc-200">代码上下文感知语音听写</span>
          {renderStatusBadge()}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              toggleAutoCorrect();
            }}
            title="切换术语自动纠偏"
            className={`px-2.5 py-1 text-xs rounded-md transition-colors border ${
              isAutoCorrectEnabled
                ? 'bg-indigo-600/20 text-indigo-300 border-indigo-500/40 hover:bg-indigo-600/30'
                : 'bg-zinc-800 text-zinc-400 border-zinc-700 hover:bg-zinc-750'
            }`}
          >
            <span className="flex items-center gap-1">
              <Sparkles className="w-3 h-3" />
              自动纠偏 {isAutoCorrectEnabled ? '开' : '关'}
            </span>
          </button>

          <button
            type="button"
            onClick={() => {
              setDrawerOpen(true);
            }}
            title="管理代码库偏置词典"
            className="p-1.5 rounded-md text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 border border-zinc-700 transition-colors"
          >
            <BookOpen className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 听写内容展示与就地编辑区 */}
      <div className="my-3 min-h-[72px]">
        {isEditing ? (
          <div className="space-y-2">
            <textarea
              value={editedText}
              onChange={(e) => {
                setEditedText(e.target.value);
              }}
              className="w-full h-20 p-2.5 text-sm bg-zinc-950/80 text-zinc-200 rounded-lg border border-indigo-500/40 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none font-mono"
              placeholder="在此微调识别指令..."
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setIsEditing(false);
                }}
                className="px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleSaveEdit}
                className="px-2.5 py-1 text-xs bg-indigo-600 text-white rounded hover:bg-indigo-500"
              >
                完成编辑
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            <button
              type="button"
              onClick={handleStartEdit}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  handleStartEdit();
                }
              }}
              className="w-full text-left p-3 rounded-lg bg-zinc-950/50 border border-zinc-800/80 text-sm text-zinc-200 font-mono leading-relaxed cursor-text hover:border-zinc-700 transition-colors focus:outline-none focus:ring-1 focus:ring-indigo-500/50"
            >
              {correctedTranscript || rawTranscript || (
                <span className="text-zinc-500 italic">点击开始录音，说出开发需求或命令...</span>
              )}
            </button>

            {/* 原始识别对照（仅当存在纠偏且纠偏后内容不同时展示） */}
            {correctedTranscript && rawTranscript && correctedTranscript !== rawTranscript && (
              <div className="flex items-center gap-1.5 text-xs text-zinc-500 px-1">
                <span className="font-sans">原始语音输入:</span>
                <span className="line-through text-zinc-400 font-mono">{rawTranscript}</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 纠偏徽标 Chip 列表 */}
      {activeCorrections.length > 0 && !isEditing && (
        <div className="mb-3 pt-2 border-t border-zinc-850">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-medium text-zinc-400 flex items-center gap-1">
              <Code2 className="w-3.5 h-3.5 text-indigo-400" />
              已智能校准的技术术语 (点击可撤销单项):
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {activeCorrections.map((corr: CorrectionRecord) => (
              <button
                key={corr.id}
                type="button"
                onClick={() => {
                  revertCorrection(corr.id);
                }}
                title={`点击撤销：${corr.original} -> ${corr.corrected}`}
                className="group inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs bg-indigo-950/40 border border-indigo-500/30 text-indigo-300 hover:border-red-500/40 hover:bg-red-950/30 hover:text-red-300 transition-colors"
              >
                <span className="line-through text-indigo-400/60 group-hover:text-red-400/60 text-[11px]">
                  {corr.original}
                </span>
                <span className="text-zinc-400 text-[10px]">→</span>
                <span className="font-semibold">{corr.corrected}</span>
                <Undo2 className="w-3 h-3 ml-0.5 opacity-60 group-hover:opacity-100" />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 底部操作控制条 */}
      <div className="flex items-center justify-between pt-2 border-t border-zinc-800">
        <div className="flex items-center gap-2">
          {status === 'listening' ? (
            <button
              type="button"
              onClick={handleStopRecording}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-600 text-white hover:bg-red-500 shadow-md transition-colors"
            >
              <MicOff className="w-3.5 h-3.5" />
              停止听写
            </button>
          ) : (
            <button
              type="button"
              onClick={handleStartRecording}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 text-zinc-200 hover:bg-zinc-700 border border-zinc-700 transition-colors"
            >
              <Mic className="w-3.5 h-3.5 text-indigo-400" />
              {rawTranscript ? '重新录音' : '开始听写'}
            </button>
          )}

          {rawTranscript && (
            <button
              type="button"
              onClick={handleCancel}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              <RotateCcw className="w-3 h-3" />
              重置
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleSend}
            disabled={!correctedTranscript && !rawTranscript}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed shadow-md transition-colors"
          >
            <Send className="w-3.5 h-3.5" />
            发给智能体 (Enter)
          </button>
        </div>
      </div>
    </div>
  );
};
