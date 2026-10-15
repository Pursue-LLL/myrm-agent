import React, { useState } from 'react';
import {
  Check,
  Cpu,
  Database,
  FileCode,
  Layers,
  Lock,
  RefreshCw,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import { StorageBackendType, TransformFormat } from './localFirstTypes';
import { useLocalFirstStore } from './useLocalFirstStore';

interface LocalFirstPrivacySandboxCardProps {
  className?: string;
  onSanitized?: (resultCount: number) => void;
}

export const LocalFirstPrivacySandboxCard: React.FC<
  LocalFirstPrivacySandboxCardProps
> = ({ className = '', onSanitized }) => {
  const inputText = useLocalFirstStore((state) => state.inputText);
  const setInputText = useLocalFirstStore((state) => state.setInputText);
  const lastResult = useLocalFirstStore(
    (state) => state.lastSanitizeResult,
  );
  const runLocalSanitize = useLocalFirstStore(
    (state) => state.runLocalSanitize,
  );
  const runFormatConvert = useLocalFirstStore(
    (state) => state.runFormatConvert,
  );
  const transformedText = useLocalFirstStore(
    (state) => state.transformedText,
  );
  const activeBackend = useLocalFirstStore(
    (state) => state.activeBackend,
  );
  const setActiveBackend = useLocalFirstStore(
    (state) => state.setActiveBackend,
  );

  const [activeFormat, setActiveFormat] = useState<TransformFormat>('json');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSanitize = () => {
    setErrorMessage(null);
    const res = runLocalSanitize();
    if (onSanitized) {
      onSanitized(res.maskedCount);
    }
  };

  const handleConvert = (format: TransformFormat) => {
    setActiveFormat(format);
    setErrorMessage(null);
    try {
      runFormatConvert(inputText, format);
    } catch (e) {
      const err = e instanceof Error ? e.message : '格式转换失败';
      setErrorMessage(err);
    }
  };

  return (
    <div
      data-testid="local-first-privacy-sandbox-card"
      className={`my-3 w-full max-w-xl rounded-xl border border-primary/25 bg-background/95 p-4 text-xs shadow-md backdrop-blur-md dark:bg-muted/30 ${className}`}
    >
      {/* 头部标题与隐私安全微标 */}
      <div className="flex items-start justify-between gap-2 border-b border-border/40 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <ShieldCheck className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-semibold text-foreground text-sm">
                纯客户端隐私沙盒
              </span>
              <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                100% 离线计算 · 零网络上传
              </span>
            </div>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              脱敏处理与格式转换就地在浏览器完成，绝不上报服务器
            </p>
          </div>
        </div>

        {/* 存储引擎漫游下拉 */}
        <div className="flex items-center gap-1 text-[11px]">
          <Database className="h-3 w-3 text-muted-foreground" />
          <select
            aria-label="漫游存储引擎"
            value={activeBackend}
            onChange={(e) => {
              setActiveBackend(e.target.value as StorageBackendType);
            }}
            className="rounded-md border border-border/60 bg-background px-1.5 py-0.5 text-[11px] text-foreground focus:outline-hidden"
          >
            <option value="local_storage">LocalStorage (本地持久)</option>
            <option value="indexed_db">IndexedDB (大容量本地)</option>
            <option value="upstash_redis">Upstash Redis (轻量漫游)</option>
            <option value="memory">纯内存临时 (无痕)</option>
          </select>
        </div>
      </div>

      {/* 文本输入区域 */}
      <div className="mt-3">
        <label
          htmlFor="local-first-text-input"
          className="block text-[11px] font-medium text-muted-foreground"
        >
          待处理文本或 JSON 数据:
        </label>
        <textarea
          id="local-first-text-input"
          rows={3}
          value={inputText}
          placeholder="在此输入需要脱敏的文本（含手机、邮箱、API Key 或身份证）或 JSON 数组..."
          onChange={(e) => {
            setInputText(e.target.value);
          }}
          className="mt-1 w-full rounded-lg border border-border/60 bg-background p-2 font-mono text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-hidden focus:ring-1 focus:ring-primary"
        />
      </div>

      {/* 脱敏执行与结果指示 */}
      <div className="mt-2.5 flex items-center justify-between">
        <button
          type="button"
          onClick={handleSanitize}
          className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1 font-medium text-white hover:bg-emerald-500 transition-colors shadow-xs"
        >
          <Lock className="h-3 w-3" />
          <span>本地脱敏 (Zero-Upload)</span>
        </button>

        {lastResult && (
          <div className="flex items-center gap-2 text-[11px] text-emerald-600 dark:text-emerald-400">
            <Check className="h-3.5 w-3.5" />
            <span>
              已脱敏 {lastResult.maskedCount} 处敏感信息 (
              {lastResult.detectedTypes.join('/') || '未发现敏感项'}) · 耗时{' '}
              {lastResult.executionTimeMs}ms
            </span>
          </div>
        )}
      </div>

      {/* 客户端就地格式转换工具栏 */}
      <div className="mt-3.5 border-t border-border/30 pt-3">
        <div className="flex items-center justify-between text-[11px]">
          <span className="font-medium text-foreground">
            客户端格式就地互转:
          </span>
          <div className="flex items-center gap-1">
            {(['json', 'csv', 'markdown_table', 'yaml'] as TransformFormat[]).map(
              (fmt) => (
                <button
                  key={fmt}
                  type="button"
                  onClick={() => {
                    handleConvert(fmt);
                  }}
                  className={`rounded-md px-2 py-0.5 transition-colors ${
                    activeFormat === fmt
                      ? 'bg-primary text-primary-foreground font-semibold'
                      : 'border border-border/60 bg-muted/20 text-muted-foreground hover:bg-muted/50'
                  }`}
                >
                  {fmt}
                </button>
              ),
            )}
          </div>
        </div>

        {errorMessage && (
          <p className="mt-1.5 text-[11px] text-red-500">{errorMessage}</p>
        )}

        {transformedText && (
          <pre className="mt-2 max-h-32 overflow-auto rounded-lg border border-border/50 bg-muted/20 p-2 font-mono text-[10px] text-foreground/90 whitespace-pre-wrap">
            {transformedText}
          </pre>
        )}
      </div>
    </div>
  );
};
