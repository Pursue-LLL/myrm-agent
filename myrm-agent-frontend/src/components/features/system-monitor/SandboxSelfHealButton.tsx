import React, { useState } from 'react';
import { SelfHealRebootResult } from './types';

export interface SandboxSelfHealButtonProps {
  sandboxId: string;
  onRebootSuccess?: (result: SelfHealRebootResult) => void;
  className?: string;
}

export const SandboxSelfHealButton: React.FC<SandboxSelfHealButtonProps> = ({
  sandboxId,
  onRebootSuccess,
  className = '',
}) => {
  const [isRebooting, setIsRebooting] = useState<boolean>(false);
  const [result, setResult] = useState<SelfHealRebootResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cooldownSec, setCooldownSec] = useState<number>(0);

  const handleReboot = async () => {
    if (isRebooting || cooldownSec > 0) return;

    setIsRebooting(true);
    setError(null);

    try {
      const response = await fetch(`/api/v1/system/sandbox/${sandboxId}/self-heal-reboot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'User initiated self-healing in UI' }),
      });

      if (!response.ok) {
        throw new Error(`自愈重启失败 (HTTP ${response.status})`);
      }

      const data: SelfHealRebootResult = await response.json();
      setResult(data);
      onRebootSuccess?.(data);

      // Start 10-second cooldown
      setCooldownSec(10);
      const timer = setInterval(() => {
        setCooldownSec((prev) => {
          if (prev <= 1) {
            clearInterval(timer);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '未知自愈异常';
      setError(msg);
    } finally {
      setIsRebooting(false);
    }
  };

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleReboot}
          disabled={isRebooting || cooldownSec > 0}
          className={`inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-medium rounded-md shadow-sm transition-all ${
            isRebooting
              ? 'bg-amber-600 text-white cursor-wait opacity-80'
              : cooldownSec > 0
              ? 'bg-gray-100 text-gray-400 dark:bg-gray-800 dark:text-gray-500 cursor-not-allowed'
              : 'bg-amber-500 hover:bg-amber-600 text-white active:scale-95'
          }`}
          data-testid="self-heal-reboot-btn"
        >
          {isRebooting ? (
            <>
              <svg
                className="animate-spin h-3.5 w-3.5 text-white"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              <span>正在原地换核自愈...</span>
            </>
          ) : cooldownSec > 0 ? (
            <span>自愈冷却中 ({cooldownSec}s)</span>
          ) : (
            <>
              <span className="text-sm">⚡</span>
              <span>原地热重启自愈 (保全磁盘数据)</span>
            </>
          )}
        </button>

        <span className="text-[11px] text-gray-500 dark:text-gray-400">
          5 秒就地重建沙箱容器，不丢失挂载 Volume
        </span>
      </div>

      {result && (
        <div
          className="text-xs p-2.5 rounded border border-emerald-200 dark:border-emerald-800/50 bg-emerald-50 dark:bg-emerald-950/20 text-emerald-700 dark:text-emerald-300 flex items-center justify-between"
          data-testid="self-heal-success-banner"
        >
          <div className="flex items-center gap-1.5">
            <span className="font-semibold">✓ 自愈成功</span>
            <span>- 耗时 {result.recovered_in_seconds}s</span>
            <span>（持久 Volume 数据完好）</span>
          </div>
          <span className="text-[10px] text-emerald-600 dark:text-emerald-400">
            {result.status}
          </span>
        </div>
      )}

      {error && (
        <div
          className="text-xs p-2 rounded border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400"
          data-testid="self-heal-error-banner"
        >
          {error}
        </div>
      )}
    </div>
  );
};
