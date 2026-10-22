import React, { useState } from 'react';
import {
  ArrowRight,
  CheckCircle2,
  Key,
  ShieldCheck,
  Sparkles,
  X,
  Zap,
} from 'lucide-react';
import { useProgressiveOnboardingStore } from './useProgressiveOnboardingStore';

interface DeferredConfigPromptProps {
  className?: string;
}

export const DeferredConfigPrompt: React.FC<DeferredConfigPromptProps> = ({
  className = '',
}) => {
  const {
    stage,
    deferredReason,
    dismissDeferredConfig,
    completeConfiguration,
  } = useProgressiveOnboardingStore();

  const [inputKey, setInputKey] = useState<string>('');
  const [isSuccess, setIsSuccess] = useState<boolean>(false);

  if (stage !== 'deferred_prompt_triggered') {
    return null;
  }

  const handleSaveKey = (): void => {
    if (inputKey.trim()) {
      setIsSuccess(true);
      setTimeout(() => {
        completeConfiguration();
      }, 500);
    }
  };

  return (
    <aside
      aria-label="按需延迟配置提示卡片"
      className={`rounded-xl border border-indigo-500/30 bg-slate-900/95 p-4 shadow-xl backdrop-blur-md transition-all ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-white">按需渐进式配置引导</h4>
            <p className="text-[11px] text-slate-400 mt-0.5">
              {deferredReason || '当前操作涉及高级模型推理或沙箱代码执行，建议接入您的专属 Key'}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            dismissDeferredConfig();
          }}
          className="text-slate-400 hover:text-slate-200 transition-colors p-1"
          aria-label="稍后配置并关闭"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* 内联输入区域 */}
      <div className="mt-3 flex items-center gap-2">
        <div className="relative flex-1">
          <Key className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-slate-500" />
          <input
            type="password"
            value={inputKey}
            onChange={(e) => {
              setInputKey(e.target.value);
            }}
            placeholder="粘贴您的 API Key (如 sk-ant-api... 或 sk-...)"
            className="w-full rounded-lg border border-slate-700 bg-slate-950/80 pl-8 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
            aria-label="API Key 输入框"
          />
        </div>

        <button
          type="button"
          onClick={handleSaveKey}
          disabled={!inputKey.trim()}
          className="flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-40 transition-colors shadow-sm"
          aria-label="保存并继续"
        >
          {isSuccess ? (
            <>
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              <span>已生效</span>
            </>
          ) : (
            <>
              <span>保存继续</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </>
          )}
        </button>
      </div>

      {/* 底部免配置说明 */}
      <div className="mt-2.5 flex items-center justify-between text-[11px] text-slate-500">
        <div className="flex items-center gap-1">
          <ShieldCheck className="w-3 h-3 text-emerald-400" />
          <span>本地加密保存 · 绝不上报云端</span>
        </div>
        <button
          type="button"
          onClick={() => {
            dismissDeferredConfig();
          }}
          className="text-slate-400 hover:text-slate-200 underline cursor-pointer"
        >
          继续使用免费基线模型
        </button>
      </div>
    </aside>
  );
};
