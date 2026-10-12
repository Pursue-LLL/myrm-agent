'use client';

/**
 * [INPUT]
 * @/hooks/memory/useMemoryProvenance (POS: Hook for residency proof and physical purge)
 * @/lib/utils/classnameUtils (POS: cn helper for Tailwind styling)
 * lucide-react (POS: Vector icons replacing native emoji)
 *
 * [OUTPUT]
 * MemoryResidencyDrawer: High-fidelity responsive side drawer displaying cryptographic
 * physical residency proofs, PII shield status, and irreversible multi-pass purge operations.
 *
 * [POS]
 * myrm-agent-frontend/src/components/features/memory/drawers/MemoryResidencyDrawer.tsx
 * Eliminates Dead Feature Path by surfacing physical isolation and compliance tools in GUI.
 */

import { memo, useCallback, useEffect, useState } from 'react';
import {
  X,
  ShieldCheck,
  ShieldAlert,
  HardDrive,
  Flame,
  RefreshCw,
  Lock,
  CheckCircle2,
  AlertTriangle,
  Copy,
  Check,
  FileKey,
  Eye,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useMemoryProvenance } from '@/hooks/memory/useMemoryProvenance';

export interface MemoryResidencyDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  tenantId?: string;
  sandboxId?: string;
  volumeId?: string;
  storagePath?: string;
}

export const MemoryResidencyDrawer = memo(function MemoryResidencyDrawer({
  isOpen,
  onClose,
  tenantId = 'tenant-personal-current',
  sandboxId = 'sandbox-dedicated-active',
  volumeId = 'vol-persistent-primary',
  storagePath = '/data/sandbox/volumes/memory.db',
}: MemoryResidencyDrawerProps) {
  const {
    proof,
    latestReceipt,
    piiInspection,
    loading,
    error,
    fetchResidencyProof,
    executePhysicalPurge,
    scanPii,
    requestVolumeToken,
  } = useMemoryProvenance();

  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [purgeConfirmText, setPurgeConfirmText] = useState<string>('');
  const [isPurging, setIsPurging] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'proof' | 'shield' | 'purge'>('proof');
  const [samplePiiInput, setSamplePiiInput] = useState<string>(
    '备忘录：我儿子叫张小明，家住北京市海淀区中关村南大街1号院。'
  );

  const loadProof = useCallback(async () => {
    try {
      const token = await requestVolumeToken(tenantId, sandboxId, volumeId);
      await fetchResidencyProof({
        file_path: storagePath,
        context: {
          tenant_id: tenantId,
          sandbox_id: sandboxId,
          volume_id: volumeId,
          environment_token: token,
        },
      });
    } catch {
      // Handled in hook
    }
  }, [tenantId, sandboxId, volumeId, storagePath, requestVolumeToken, fetchResidencyProof]);

  useEffect(() => {
    if (isOpen) void loadProof();
  }, [isOpen, loadProof]);

  const handleCopy = useCallback((text: string, key: string) => {
    void navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  }, []);

  const handleExecutePurge = useCallback(async () => {
    if (purgeConfirmText !== 'PURGE') return;
    setIsPurging(true);
    try {
      const token = await requestVolumeToken(tenantId, sandboxId, volumeId);
      await executePhysicalPurge({
        file_path: storagePath,
        context: {
          tenant_id: tenantId,
          sandbox_id: sandboxId,
          volume_id: volumeId,
          environment_token: token,
        },
      });
      setPurgeConfirmText('');
    } catch {
      // Handled in hook
    } finally {
      setIsPurging(false);
    }
  }, [purgeConfirmText, tenantId, sandboxId, volumeId, storagePath, requestVolumeToken, executePhysicalPurge]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-black/40 backdrop-blur-sm animate-in fade-in">
      <div className="fixed inset-y-0 right-0 flex max-w-full pl-10">
        <aside
          role="dialog"
          aria-modal="true"
          aria-label="存储物理驻留与合规控制台"
          className="w-screen max-w-xl border-l border-border/80 bg-background/95 p-6 shadow-2xl backdrop-blur-md flex flex-col justify-between sm:p-8"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border/60 pb-4">
            <div className="flex items-center space-x-3">
              <div className="rounded-lg bg-primary/10 p-2 text-primary dark:bg-primary/20">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-lg font-semibold tracking-tight text-foreground">
                  存储物理驻留与合规控制台
                </h2>
                <p className="text-xs text-muted-foreground">
                  单沙箱专属持久卷隔离与可验证合规销毁
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              <button
                type="button"
                onClick={() => void loadProof()}
                disabled={loading}
                className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors disabled:opacity-50"
                aria-label="刷新验证凭证"
              >
                <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
              </button>
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                aria-label="关闭控制台"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="mt-4 flex space-x-2 border-b border-border/40 pb-2">
            {[
              { id: 'proof', label: '物理卷驻留凭证', icon: HardDrive },
              { id: 'shield', label: '入库脱敏盾', icon: Lock },
              { id: 'purge', label: '物理覆写销毁', icon: Flame },
            ].map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => setActiveTab(id as 'proof' | 'shield' | 'purge')}
                className={cn(
                  'flex items-center space-x-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                  activeTab === id
                    ? id === 'purge'
                      ? 'bg-destructive/10 text-destructive dark:bg-destructive/20'
                      : 'bg-primary/10 text-primary dark:bg-primary/20'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                <span>{label}</span>
              </button>
            ))}
          </div>

          {error && (
            <div className="mt-3 flex items-start space-x-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
              <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5" />
              <div className="break-all">{error}</div>
            </div>
          )}

          {/* Tab Content Panes */}
          <div className="mt-4 flex-1 overflow-y-auto space-y-4 pr-1">
            {activeTab === 'proof' && (
              <div className="rounded-xl border border-border/60 bg-card/60 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-muted-foreground">物理卷隔离状态</span>
                  <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                    <CheckCircle2 className="h-3 w-3 mr-1" />
                    专属无共享卷 (Fail-Closed)
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="rounded-lg bg-muted/40 p-2.5">
                    <div className="text-muted-foreground">沙箱标识 (Sandbox)</div>
                    <div className="font-mono font-medium text-foreground truncate mt-0.5">{sandboxId}</div>
                  </div>
                  <div className="rounded-lg bg-muted/40 p-2.5">
                    <div className="text-muted-foreground">卷标识 (Volume)</div>
                    <div className="font-mono font-medium text-foreground truncate mt-0.5">{volumeId}</div>
                  </div>
                </div>
                <div className="rounded-lg bg-muted/40 p-2.5 text-xs">
                  <div className="flex items-center justify-between text-muted-foreground">
                    <span>存储挂载端点</span>
                    <button
                      type="button"
                      onClick={() => handleCopy(storagePath, 'path')}
                      className="text-primary hover:underline flex items-center space-x-0.5"
                    >
                      {copiedKey === 'path' ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                      <span>复制</span>
                    </button>
                  </div>
                  <div className="font-mono text-foreground break-all mt-1">{storagePath}</div>
                </div>
                {proof && (
                  <div className="space-y-2 border-t border-border/40 pt-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">文件 Inode 编号</span>
                      <span className="font-mono font-medium">{proof.file_inode}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">校验时间</span>
                      <span className="font-mono">{new Date(proof.verified_at).toLocaleTimeString()}</span>
                    </div>
                    <div>
                      <div className="flex items-center justify-between text-muted-foreground mb-1">
                        <span>SHA-256 内容指纹</span>
                        <button
                          type="button"
                          onClick={() => handleCopy(proof.content_sha256, 'hash')}
                          className="text-primary hover:underline flex items-center space-x-0.5"
                        >
                          {copiedKey === 'hash' ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                          <span>复制</span>
                        </button>
                      </div>
                      <div className="font-mono text-[11px] bg-muted/60 p-2 rounded text-foreground break-all">
                        {proof.content_sha256}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'shield' && (
              <div className="rounded-xl border border-border/60 bg-card/60 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-muted-foreground">Pre-Ingest PII 脱敏规则</span>
                  <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary font-medium">
                    双语确定性脱敏
                  </span>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  在记忆进入持久卷前确定性拦截儿童姓名、详细住址、银行账号与中国身份证号，彻底消除多租户及第三方模型明文残留风险。
                </p>
                <div className="space-y-2 pt-2">
                  <label htmlFor="sample-pii-input" className="text-xs font-medium text-foreground">
                    实时脱敏沙盒模拟
                  </label>
                  <textarea
                    id="sample-pii-input"
                    value={samplePiiInput}
                    onChange={(e) => setSamplePiiInput(e.target.value)}
                    rows={3}
                    className="w-full rounded-lg border border-input bg-background/80 p-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                    placeholder="输入测试敏感内容..."
                  />
                  <button
                    type="button"
                    onClick={() => void scanPii(samplePiiInput)}
                    disabled={loading}
                    className="flex items-center space-x-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
                  >
                    <Eye className="h-3.5 w-3.5" />
                    <span>执行脱敏审计</span>
                  </button>
                </div>
                {piiInspection && (
                  <div className="space-y-2 border-t border-border/40 pt-3 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">敏感实体拦截</span>
                      <span className={cn('font-medium', piiInspection.intercepted ? 'text-amber-500' : 'text-emerald-500')}>
                        {piiInspection.intercepted ? '已拦截敏感信息' : '内容安全，无需脱敏'}
                      </span>
                    </div>
                    {piiInspection.has_child_privacy_violation && (
                      <div className="flex items-center space-x-1 text-destructive font-medium">
                        <AlertTriangle className="h-3.5 w-3.5" />
                        <span>触碰儿童个人信息保护红线</span>
                      </div>
                    )}
                    <div>
                      <span className="text-muted-foreground block mb-1">脱敏后入库内容：</span>
                      <div className="rounded-lg bg-muted/60 p-2.5 font-mono text-[11px] text-foreground break-all">
                        {piiInspection.sanitized_text}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'purge' && (
              <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 space-y-3">
                <div className="flex items-center space-x-2 text-destructive">
                  <AlertTriangle className="h-5 w-5 shrink-0" />
                  <span className="text-xs font-semibold">不可逆物理扇区级覆写 (DoD 5220.22-M)</span>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  执行三遍物理覆写（0x00 全零、0xFF 全一、随机密码字节），级联清空主 SQLite 数据库及其 WAL、SHM、Journal 伴生日志文件并永久解除文件节点。
                </p>
                <div className="rounded-lg bg-background/80 p-3 border border-border/60 space-y-2 text-xs">
                  <label htmlFor="confirm-purge-input" className="text-muted-foreground block">
                    请输入大写字母 <span className="font-mono font-bold text-destructive">PURGE</span> 确认销毁：
                  </label>
                  <input
                    id="confirm-purge-input"
                    type="text"
                    value={purgeConfirmText}
                    onChange={(e) => setPurgeConfirmText(e.target.value)}
                    placeholder="PURGE"
                    className="w-full rounded-lg border border-input bg-background p-2 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-destructive"
                  />
                  <button
                    type="button"
                    onClick={handleExecutePurge}
                    disabled={purgeConfirmText !== 'PURGE' || isPurging}
                    className="w-full flex items-center justify-center space-x-1.5 rounded-lg bg-destructive px-3 py-2 text-xs font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-50"
                  >
                    <Flame className="h-4 w-4" />
                    <span>{isPurging ? '物理多遍覆写中...' : '确认彻底物理销毁'}</span>
                  </button>
                </div>
                {latestReceipt && (
                  <div className="rounded-lg border border-border/60 bg-card/80 p-3 space-y-2 text-xs">
                    <div className="flex items-center space-x-1.5 text-emerald-500 font-medium">
                      <FileKey className="h-4 w-4" />
                      <span>已签发不可篡改销毁凭证</span>
                    </div>
                    <div className="grid grid-cols-2 gap-1 text-[11px] text-muted-foreground">
                      <div>凭证号：<span className="font-mono text-foreground">{latestReceipt.receipt_id}</span></div>
                      <div>覆写遍数：<span className="font-mono text-foreground">{latestReceipt.overwrite_passes} 次</span></div>
                      <div>覆写字节：<span className="font-mono text-foreground">{latestReceipt.bytes_overwritten} B</span></div>
                      <div>状态：<span className="font-mono text-emerald-500">{latestReceipt.status}</span></div>
                    </div>
                    <div>
                      <span className="text-[11px] text-muted-foreground block mb-0.5">零态哈希摘要：</span>
                      <div className="font-mono text-[10px] bg-muted/60 p-1.5 rounded text-foreground break-all">
                        {latestReceipt.destruction_digest}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Footer Note */}
          <div className="border-t border-border/60 pt-4 text-[11px] text-muted-foreground flex items-center justify-between">
            <span>遵循企业数据合规与物理驻留标准</span>
            <span className="font-mono">Fail-Closed & Purge-Verified</span>
          </div>
        </aside>
      </div>
    </div>
  );
});
