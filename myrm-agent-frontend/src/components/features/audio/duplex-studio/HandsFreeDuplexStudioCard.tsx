import React, { useState } from 'react';
import {
  Mic,
  MicOff,
  Radio,
  Sliders,
  ShieldCheck,
  Play,
  RotateCcw,
  Sparkles,
  Bot,
  User,
  Zap,
} from 'lucide-react';
import { useDuplexVoiceStore } from './useDuplexVoiceStore';
import { DuplexAudioWaveformVisualizer } from './DuplexAudioWaveformVisualizer';
import { BargeInFeedbackBanner } from './BargeInFeedbackBanner';
import { BargeInSensitivity } from './duplexVoiceTypes';

export interface HandsFreeDuplexStudioCardProps {
  className?: string;
}

export const HandsFreeDuplexStudioCard: React.FC<
  HandsFreeDuplexStudioCardProps
> = ({ className = '' }) => {
  const {
    status,
    metrics,
    messages,
    currentAgentSpeech,
    currentUserSpeech,
    settings,
    startDuplexSession,
    stopDuplexSession,
    feedMicAudioVolume,
    feedAgentSpeechStream,
    feedUserSpeechStream,
    updateSettings,
    clearHistory,
    reset,
  } = useDuplexVoiceStore();

  const [simText, setSimText] = useState('');
  const [showSettings, setShowSettings] = useState(false);

  const isSessionActive = status !== 'idle';

  const handleToggleSession = () => {
    if (isSessionActive) {
      stopDuplexSession();
    } else {
      startDuplexSession();
    }
  };

  const handleSimulateUserSpeech = (e: React.FormEvent) => {
    e.preventDefault();
    if (!simText.trim()) {
      return;
    }
    // 模拟麦克风音量飙升并提供文字
    feedMicAudioVolume(80);
    feedUserSpeechStream(simText, true);
    setSimText('');
  };

  const handleSimulateAgentSpeak = () => {
    feedAgentSpeechStream(
      '你好！我是你的实时编程助手。我现在正在为您全自动搭建用户中心后端路由和中间件鉴权逻辑，稍后将进行本地编译…',
      false
    );
  };

  return (
    <div
      data-testid="hands-free-duplex-studio-card"
      className={`p-6 max-w-3xl mx-auto rounded-3xl bg-zinc-900/95 border border-zinc-800 shadow-2xl space-y-4 font-sans text-zinc-100 ${className}`}
    >
      {/* 1. 顶部标题与会话开关 */}
      <header className="flex items-center justify-between pb-3 border-b border-zinc-800">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-2xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Radio className={`w-5 h-5 ${isSessionActive ? 'animate-pulse text-indigo-400' : ''}`} />
          </div>
          <div>
            <h2 className="text-sm font-bold text-zinc-100 flex items-center gap-1.5">
              <span>全双工实时语音 Studio · 免打字随时打断</span>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                Barge-In 2.0
              </span>
            </h2>
            <p className="text-xs text-zinc-400">
              Agent 说话时随时开口纠偏，毫秒级静音播报并平滑自愈上下文
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              setShowSettings(!showSettings);
            }}
            aria-label="打开双工设置"
            className="p-2 rounded-xl text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            <Sliders className="w-4 h-4" />
          </button>

          <button
            type="button"
            onClick={handleToggleSession}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold shadow transition-all ${
              isSessionActive
                ? 'bg-rose-600 hover:bg-rose-500 text-white'
                : 'bg-indigo-600 hover:bg-indigo-500 text-white'
            }`}
          >
            {isSessionActive ? (
              <>
                <MicOff className="w-4 h-4" />
                <span>挂断双工通道</span>
              </>
            ) : (
              <>
                <Mic className="w-4 h-4" />
                <span>开启全双工免唤醒</span>
              </>
            )}
          </button>
        </div>
      </header>

      {/* 2. 随时插话打断反馈横幅 */}
      <BargeInFeedbackBanner />

      {/* 3. 音频流波形可视化器 */}
      <DuplexAudioWaveformVisualizer status={status} metrics={metrics} />

      {/* 4. 设置展开抽屉/区域 */}
      {showSettings && (
        <section
          data-testid="duplex-settings-drawer"
          className="p-3.5 rounded-2xl bg-zinc-950/90 border border-zinc-800 space-y-3 text-xs animate-fade-in"
        >
          <div className="flex items-center justify-between">
            <span className="font-semibold text-zinc-200">
              随时插话打断灵敏度 (Barge-In Sensitivity):
            </span>
            <div className="flex items-center gap-1 font-mono text-[11px]">
              {(['low', 'medium', 'high'] as BargeInSensitivity[]).map((sens) => (
                <button
                  key={sens}
                  type="button"
                  onClick={() => {
                    updateSettings({ bargeInSensitivity: sens });
                  }}
                  className={`px-2.5 py-1 rounded-lg border transition-all ${
                    settings.bargeInSensitivity === sens
                      ? 'bg-indigo-600/20 border-indigo-500 text-indigo-300 font-bold'
                      : 'bg-zinc-900 border-zinc-800 text-zinc-400'
                  }`}
                >
                  {sens.toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-zinc-850">
            <span className="text-zinc-300 flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              端侧环境降噪与回声消除 (RNNoise)
            </span>
            <label
              aria-label="端侧环境降噪与回声消除开关"
              className="relative inline-flex items-center cursor-pointer"
            >
              <input
                type="checkbox"
                checked={settings.noiseSuppressionEnabled}
                onChange={(e) => {
                  updateSettings({ noiseSuppressionEnabled: e.target.checked });
                }}
                className="sr-only peer"
              />
              <div className="w-9 h-5 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-600" />
            </label>
          </div>
        </section>
      )}

      {/* 5. 实时对话与转写流 */}
      <section className="space-y-2">
        <div className="flex items-center justify-between text-xs text-zinc-400">
          <span className="font-mono">实时转写流 ({messages.length} 轮次)</span>
          {messages.length > 0 && (
            <button
              type="button"
              onClick={clearHistory}
              className="text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              清空对话
            </button>
          )}
        </div>

        <div className="p-3 rounded-2xl bg-zinc-950/80 border border-zinc-800 min-h-[160px] max-h-60 overflow-y-auto space-y-2 font-mono text-xs">
          {messages.length === 0 && !currentAgentSpeech && !currentUserSpeech && (
            <div className="h-28 flex flex-col items-center justify-center text-zinc-600 space-y-1">
              <Sparkles className="w-5 h-5 text-zinc-700" />
              <span>双工通道待命，说话即可直接交流…</span>
            </div>
          )}

          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`p-2 rounded-xl text-xs ${
                msg.role === 'user'
                  ? 'bg-indigo-950/40 text-indigo-200 border border-indigo-900/40 ml-6'
                  : 'bg-zinc-900/80 text-zinc-200 border border-zinc-800 mr-6'
              }`}
            >
              <div className="flex items-center justify-between text-[10px] text-zinc-500 mb-1">
                <span className="flex items-center gap-1 font-bold">
                  {msg.role === 'user' ? (
                    <User className="w-3 h-3 text-indigo-400" />
                  ) : (
                    <Bot className="w-3 h-3 text-emerald-400" />
                  )}
                  {msg.role === 'user' ? '用户' : '智能体'}
                </span>
                {msg.wasInterrupted && (
                  <span className="text-amber-400 flex items-center gap-0.5">
                    <Zap className="w-2.5 h-2.5" /> 已被用户插话截断
                  </span>
                )}
              </div>
              <p className="leading-relaxed font-sans">{msg.content}</p>
            </div>
          ))}

          {/* 当前正在进行的语音输出 */}
          {currentAgentSpeech && (
            <div className="p-2 rounded-xl bg-emerald-950/20 border border-emerald-500/30 text-emerald-200 text-xs animate-pulse">
              <div className="text-[10px] text-emerald-400 font-bold mb-1 flex items-center gap-1">
                <Bot className="w-3 h-3" />
                <span>智能体实时播报中 (可直接开口打断):</span>
              </div>
              <p className="font-sans leading-relaxed">{currentAgentSpeech}</p>
            </div>
          )}

          {/* 当前正在收音的用户语音 */}
          {currentUserSpeech && (
            <div className="p-2 rounded-xl bg-indigo-950/30 border border-indigo-500/30 text-indigo-300 text-xs animate-pulse">
              <div className="text-[10px] text-indigo-400 font-bold mb-1 flex items-center gap-1">
                <User className="w-3 h-3" />
                <span>正在聆听用户语音:</span>
              </div>
              <p className="font-sans leading-relaxed">{currentUserSpeech}</p>
            </div>
          )}
        </div>
      </section>

      {/* 6. 快捷仿真与单步打断测试面板 */}
      <footer className="pt-2 border-t border-zinc-800 flex flex-wrap items-center justify-between gap-2 text-xs">
        <form
          onSubmit={handleSimulateUserSpeech}
          className="flex items-center gap-1.5 flex-1 max-w-md"
        >
          <input
            type="text"
            value={simText}
            onChange={(e) => {
              setSimText(e.target.value);
            }}
            placeholder="模拟开口说话插话内容…"
            className="flex-1 px-3 py-1.5 rounded-xl bg-zinc-950 border border-zinc-800 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-indigo-500"
          />
          <button
            type="submit"
            aria-label="模拟开口打断"
            className="px-3 py-1.5 rounded-xl bg-amber-600 hover:bg-amber-500 text-white font-semibold flex items-center gap-1 transition-colors"
          >
            <Zap className="w-3.5 h-3.5" />
            <span>插话纠偏</span>
          </button>
        </form>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={handleSimulateAgentSpeak}
            className="px-3 py-1.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-emerald-300 font-medium transition-colors flex items-center gap-1"
          >
            <Play className="w-3 h-3" />
            <span>模拟 Agent 说话</span>
          </button>

          <button
            type="button"
            onClick={reset}
            aria-label="重置双工状态"
            className="p-1.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </footer>
    </div>
  );
};
