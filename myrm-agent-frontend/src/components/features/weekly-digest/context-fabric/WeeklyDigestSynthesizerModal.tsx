import React, { useState } from 'react';
import {
  FileText,
  Sparkles,
  Send,
  Copy,
  Check,
  X,
  Share2,
  RefreshCw,
  Layers,
  ChevronRight,
  ShieldCheck,
} from 'lucide-react';
import { useWeeklyDigestStore } from './useWeeklyDigestStore';
import { DigestStylePreset } from './weeklyDigestTypes';

export const WeeklyDigestSynthesizerModal: React.FC = () => {
  const {
    isSynthesizerModalOpen,
    currentDigest,
    activeStylePreset,
    isSynthesizing,
    lastExportStatus,
    closeSynthesizerModal,
    synthesizeDigest,
    refineDigest,
    exportDigest,
  } = useWeeklyDigestStore();

  const [refineInput, setRefineInput] = useState('');
  const [copiedRecently, setCopiedRecently] = useState(false);

  if (!isSynthesizerModalOpen || !currentDigest) {
    return null;
  }

  const handleStyleChange = (style: DigestStylePreset) => {
    synthesizeDigest(style);
  };

  const handleRefineSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!refineInput.trim() || isSynthesizing) {
      return;
    }
    const text = refineInput;
    setRefineInput('');
    refineDigest(text);
  };

  const handleCopyMarkdown = async () => {
    const success = await exportDigest('clipboard');
    if (success) {
      setCopiedRecently(true);
      setTimeout(() => setCopiedRecently(false), 2000);
    }
  };

  const handleExportFeishu = async () => {
    await exportDigest('feishu');
  };

  const styleTabs: Array<{ id: DigestStylePreset; label: string; desc: string }> = [
    { id: 'executive', label: '高管审阅版', desc: '聚焦关键指标与业务落地收益' },
    { id: 'technical', label: '研发技术向', desc: '包含代码细节、RFC 决策与踩坑记录' },
    { id: 'bullet', label: '极简子弹点', desc: '极简条目，适合晨会与即时沟通' },
  ];

  return (
    <>
      <div
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm transition-opacity"
        aria-hidden="true"
      />
      <dialog
        open
        aria-labelledby="digest-modal-title"
        className="fixed inset-0 z-50 m-auto w-full max-w-4xl max-h-[90vh] bg-slate-900 border border-slate-700/80 rounded-xl shadow-2xl p-0 flex flex-col text-slate-100 overflow-hidden"
        data-testid="weekly-digest-synthesizer-modal"
      >
        {/* 顶部标题与行动区 */}
        <header className="px-6 py-4 border-b border-slate-800 bg-slate-950/70 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-indigo-600/30 text-indigo-400 border border-indigo-500/40">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 id="digest-modal-title" className="font-bold text-base text-white">
                  全自动工作周报合成与复盘中心
                </h3>
                <span className="text-xs px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 font-mono border border-indigo-800/60">
                  {currentDigest.weekIdentifier}
                </span>
              </div>
              <p className="text-xs text-slate-400">
                对标火山引擎 OpenViking 规范，基于多渠道事实证据一键萃取高质周报
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={handleCopyMarkdown}
              aria-label="复制周报 Markdown"
              className="px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-md flex items-center space-x-1.5 transition-colors"
            >
              {copiedRecently ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-emerald-300">已复制</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span>复制 Markdown</span>
                </>
              )}
            </button>

            <button
              type="button"
              onClick={handleExportFeishu}
              aria-label="直落导出到飞书文档"
              className="px-3 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-md shadow flex items-center space-x-1.5 transition-all"
            >
              <Share2 className="w-3.5 h-3.5" />
              <span>直落飞书文档</span>
            </button>

            <button
              type="button"
              onClick={closeSynthesizerModal}
              aria-label="关闭周报弹窗"
              className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors ml-1"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* 风格切换选项卡 */}
        <div className="px-6 py-2.5 bg-slate-950/40 border-b border-slate-800/80 flex items-center justify-between">
          <div
            className="flex items-center space-x-1 bg-slate-900 p-1 rounded-lg border border-slate-800 text-xs"
            role="tablist"
            aria-label="周报风格模板"
          >
            {styleTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={activeStylePreset === tab.id}
                disabled={isSynthesizing}
                onClick={() => handleStyleChange(tab.id)}
                className={`px-3 py-1.5 rounded-md font-medium transition-all ${
                  activeStylePreset === tab.id
                    ? 'bg-indigo-600 text-white shadow'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="text-[11px] text-slate-400 flex items-center space-x-1">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>事实溯源：全部内容严格基于已勾选的工作足迹</span>
          </div>
        </div>

        {/* 周报内容预览主视窗 */}
        <div
          className="flex-1 p-6 overflow-y-auto bg-slate-900/60 font-mono text-xs leading-relaxed text-slate-200 whitespace-pre-wrap select-text"
          data-testid="digest-preview-content"
        >
          {isSynthesizing ? (
            <div className="flex flex-col items-center justify-center py-16 space-y-3 text-indigo-400">
              <RefreshCw className="w-6 h-6 animate-spin" />
              <span className="text-xs font-sans text-slate-400">
                正在深度萃取全域工作足迹并合成周报...
              </span>
            </div>
          ) : (
            currentDigest.markdownContent
          )}
        </div>

        {/* 底部自然语言交互微调栏 */}
        <footer className="p-4 border-t border-slate-800 bg-slate-950/80 space-y-2">
          <form onSubmit={handleRefineSubmit} className="flex items-center space-x-2">
            <div className="p-2 text-indigo-400 shrink-0">
              <Sparkles className="w-4 h-4" />
            </div>
            <input
              type="text"
              value={refineInput}
              onChange={(e) => setRefineInput(e.target.value)}
              placeholder="输入自然语言微调周报（例如：‘把技术细节缩短一些’、‘突出项目收益’、‘切换为极简子弹点’）..."
              disabled={isSynthesizing}
              className="flex-1 bg-slate-900 text-white text-xs px-3.5 py-2 rounded-lg border border-slate-700 focus:outline-none focus:border-indigo-500 transition-colors"
            />
            <button
              type="submit"
              disabled={!refineInput.trim() || isSynthesizing}
              aria-label="发送微调指令"
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg flex items-center space-x-1.5 transition-all"
            >
              <Send className="w-3.5 h-3.5" />
              <span>微调</span>
            </button>
          </form>

          {lastExportStatus && (
            <div className="text-[11px] text-emerald-400 flex items-center space-x-1 pl-2">
              <Check className="w-3 h-3" />
              <span>
                成功处理投递目标：{lastExportStatus.target} (
                {new Date(lastExportStatus.timestamp).toLocaleTimeString()})
              </span>
            </div>
          )}
        </footer>
      </dialog>
    </>
  );
};
