'use client';

/**
 * [INPUT]
 * - @/hooks/approval/useStagedCredentials::StagedCredentials (POS: 审批卡上已暂存凭据的状态)
 * - @/lib/approval/oneTimeCredentials::BLOCKED_CREDENTIAL_KEYS, OneTimeCredentialError, CredentialToStage (POS: 变量名预检、服务端拒绝的状态、暂存请求形状)
 * - next-intl::useTranslations (POS: toolApproval.maskedCredentials 文案)
 *
 * [OUTPUT]
 * - MaskedCredentialInputCard: 为审批卡所示的那一条命令录入一次性密码/密钥，显示倒计时、可撤回
 *
 * [POS]
 * 审批卡内的凭据录入表单。明文只存在于输入框本地状态，暂存成功后立刻清空；暂存状态与到期销毁由上层 hook 持有。
 */

import { AlertTriangle, CheckCircle2, Clock, Eye, EyeOff, Key, Lock, Plus, ShieldCheck, Trash2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useId, useState } from 'react';

import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import type { StagedCredentials } from '@/hooks/approval/useStagedCredentials';
import {
  BLOCKED_CREDENTIAL_KEYS,
  OneTimeCredentialError,
  type CredentialToStage,
} from '@/lib/approval/oneTimeCredentials';
import { toast } from '@/lib/utils/toast';

interface CredentialDraft {
  id: string;
  key: string;
  secret: string;
  ttlSeconds: number;
  showSecret: boolean;
}

export interface MaskedCredentialInputCardProps {
  staged: StagedCredentials | null;
  /** Rejects when the credentials could not be staged. */
  onStage: (credentials: CredentialToStage[]) => Promise<void>;
  /** Rejects when the staged credentials could not be destroyed. */
  onRevoke: () => Promise<void>;
  disabled?: boolean;
  className?: string;
}

type KeyErrorCode = 'empty' | 'format' | 'blocked';
type KeyValidation = { isValid: true } | { isValid: false; error: KeyErrorCode };

const TTL_OPTIONS = [
  { seconds: 30, labelKey: 'ttl30' },
  { seconds: 60, labelKey: 'ttl60' },
  { seconds: 120, labelKey: 'ttl120' },
  { seconds: 300, labelKey: 'ttl300' },
] as const;

let draftCounter = 0;

function newDraft(): CredentialDraft {
  draftCounter += 1;
  return { id: `credential-draft-${draftCounter}`, key: '', secret: '', ttlSeconds: 60, showSecret: false };
}

function validateKeyName(key: string): KeyValidation {
  const trimmed = key.trim().toUpperCase();
  if (!trimmed) {
    return { isValid: false, error: 'empty' };
  }
  if (!/^[A-Z_][A-Z0-9_]*$/.test(trimmed)) {
    return { isValid: false, error: 'format' };
  }
  if (BLOCKED_CREDENTIAL_KEYS.has(trimmed)) {
    return { isValid: false, error: 'blocked' };
  }
  return { isValid: true };
}

export function MaskedCredentialInputCard({
  staged,
  onStage,
  onRevoke,
  disabled = false,
  className = '',
}: MaskedCredentialInputCardProps) {
  const t = useTranslations('toolApproval.maskedCredentials');
  const firstDraftId = useId();
  const [drafts, setDrafts] = useState<CredentialDraft[]>(() => [{ ...newDraft(), id: firstDraftId }]);
  const [isStaging, setIsStaging] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  const expiresAtMs = staged?.expiresAtMs;

  useEffect(() => {
    if (expiresAtMs === undefined) {
      return;
    }
    const tick = () => setRemainingSeconds(Math.max(0, Math.ceil((expiresAtMs - Date.now()) / 1000)));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [expiresAtMs]);

  const handleAddRow = useCallback(() => setDrafts((prev) => [...prev, newDraft()]), []);

  const handleRemoveRow = useCallback((id: string) => {
    setDrafts((prev) => prev.filter((d) => d.id !== id));
  }, []);

  const handleUpdateDraft = useCallback(
    <K extends keyof CredentialDraft>(id: string, field: K, value: CredentialDraft[K]) => {
      setDrafts((prev) => prev.map((d) => (d.id === id ? { ...d, [field]: value } : d)));
    },
    [],
  );

  const keyErrorMessage = (error: KeyErrorCode, key: string): string => {
    switch (error) {
      case 'empty':
        return t('keyErrorEmpty');
      case 'format':
        return t('keyErrorFormat');
      case 'blocked':
        return t('keyErrorBlocked', { key: key.trim().toUpperCase() });
    }
  };

  // Server and network wording never reaches the user: a refused request means "check the input", anything else "retry".
  const stageFailureReason = (err: unknown): string =>
    err instanceof OneTimeCredentialError && (err.status === 400 || err.status === 422)
      ? t('errorRejected')
      : t('errorUnavailable');

  const handleStageCredentials = async () => {
    const filled = drafts.filter((d) => d.key.trim() && d.secret);
    if (filled.length === 0) {
      toast.warning(t('toastNoCredential'));
      return;
    }
    for (const d of filled) {
      const validation = validateKeyName(d.key);
      if (!validation.isValid) {
        toast.error(keyErrorMessage(validation.error, d.key));
        return;
      }
    }

    setIsStaging(true);
    try {
      await onStage(
        filled.map((d) => ({ key: d.key.trim().toUpperCase(), secret: d.secret, ttlSeconds: d.ttlSeconds })),
      );
      // Plaintext leaves the UI state the moment the server holds it; the form returns empty if the credentials go away.
      setDrafts([newDraft()]);
      toast.success(t('toastStaged'));
    } catch (err: unknown) {
      toast.error(t('toastStageFailed', { message: stageFailureReason(err) }));
    } finally {
      setIsStaging(false);
    }
  };

  const handleRevoke = async () => {
    try {
      await onRevoke();
      toast.info(t('toastCleared'));
    } catch (err: unknown) {
      toast.error(t('toastWipeFailed'));
    }
  };

  return (
    <div className={`rounded-lg border border-warning/30 bg-warning/5 p-4 transition-colors ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-warning/20 pb-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <Key className="h-4 w-4 shrink-0 text-warning" />
          <span className="text-sm font-medium text-foreground">{t('title')}</span>
          <Badge variant="outline" className="flex items-center gap-1 border-warning/40 text-[11px] text-warning">
            <ShieldCheck className="h-3 w-3" />
            {t('badgeNeverSaved')}
          </Badge>
        </div>

        {staged && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleRevoke}
            disabled={disabled}
            className="h-7 text-xs text-muted-foreground hover:text-destructive"
          >
            <Trash2 className="mr-1 h-3.5 w-3.5" />
            {t('revoke')}
          </Button>
        )}
      </div>

      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{t('description')}</p>

      {staged ? (
        <div className="mt-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2.5">
          <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2 text-xs font-medium text-emerald-700 dark:text-emerald-300">
            <span className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              {t('stagedReady')}
            </span>
            <span className="flex items-center gap-1 font-normal tabular-nums">
              <Clock className="h-3 w-3" />
              {t('expiresIn', { seconds: remainingSeconds })}
            </span>
          </div>
          <ul className="space-y-1">
            {staged.items.map((s) => (
              <li key={s.handleId} className="flex items-center justify-between gap-2 font-mono text-[11px]">
                <span className="min-w-0 break-all font-semibold text-foreground">{s.key}</span>
                <Badge variant="secondary" className="h-4 shrink-0 px-1.5 py-0 text-[10px]">
                  {t('singleUseBadge')}
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <>
          <div className="mt-3 space-y-3">
            {drafts.map((draft, idx) => {
              const keyValidation: KeyValidation = draft.key ? validateKeyName(draft.key) : { isValid: true };
              return (
                <div key={draft.id} className="space-y-2 rounded-md border border-border/60 bg-background/80 p-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-medium text-muted-foreground">
                      {t('credentialIndex', { index: idx + 1 })}
                    </span>
                    {drafts.length > 1 && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveRow(draft.id)}
                        aria-label={t('removeCredential')}
                        className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                        disabled={disabled}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    )}
                  </div>

                  <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                    <div>
                      <label
                        htmlFor={`cred-key-${draft.id}`}
                        className="mb-0.5 block text-[11px] text-muted-foreground"
                      >
                        {t('keyLabel')}
                      </label>
                      <Input
                        id={`cred-key-${draft.id}`}
                        type="text"
                        placeholder="API_SECRET_KEY"
                        value={draft.key}
                        onChange={(e) => handleUpdateDraft(draft.id, 'key', e.target.value.toUpperCase())}
                        disabled={disabled || isStaging}
                        className="h-8 font-mono text-xs"
                      />
                      {!keyValidation.isValid && (
                        <p className="mt-1 flex items-center gap-1 text-[10px] text-destructive">
                          <AlertTriangle className="h-3 w-3 shrink-0" />
                          {keyErrorMessage(keyValidation.error, draft.key)}
                        </p>
                      )}
                    </div>

                    <div>
                      <label
                        htmlFor={`cred-secret-${draft.id}`}
                        className="mb-0.5 block text-[11px] text-muted-foreground"
                      >
                        {t('secretLabel')}
                      </label>
                      <div className="relative">
                        <Input
                          id={`cred-secret-${draft.id}`}
                          type={draft.showSecret ? 'text' : 'password'}
                          placeholder="••••••••••••"
                          autoComplete="off"
                          value={draft.secret}
                          onChange={(e) => handleUpdateDraft(draft.id, 'secret', e.target.value)}
                          disabled={disabled || isStaging}
                          className="h-8 pr-8 font-mono text-xs"
                        />
                        <button
                          type="button"
                          onClick={() => handleUpdateDraft(draft.id, 'showSecret', !draft.showSecret)}
                          aria-label={draft.showSecret ? t('hideSecret') : t('showSecret')}
                          className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-muted-foreground hover:text-foreground"
                          tabIndex={-1}
                        >
                          {draft.showSecret ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border/40 pt-1 text-[11px]">
                    <div className="flex items-center gap-1.5 text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      <span>{t('ttlLabel')}</span>
                      <select
                        value={draft.ttlSeconds}
                        onChange={(e) => handleUpdateDraft(draft.id, 'ttlSeconds', Number(e.target.value))}
                        disabled={disabled || isStaging}
                        className="rounded border border-border/60 bg-transparent px-1.5 py-0.5 text-[11px] text-foreground focus:outline-none"
                      >
                        {TTL_OPTIONS.map(({ seconds, labelKey }) => (
                          <option key={seconds} value={seconds}>
                            {t(labelKey)}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="flex items-center gap-1 text-muted-foreground">
                      <Lock className="h-3 w-3 text-warning" />
                      <span>{t('singleUseEnforced')}</span>
                    </div>
                  </div>
                </div>
              );
            })}

            <div className="flex items-center justify-between gap-2 pt-1">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleAddRow}
                disabled={disabled || isStaging}
                className="h-7 text-xs"
              >
                <Plus className="mr-1 h-3.5 w-3.5" />
                {t('addRow')}
              </Button>

              <Button
                type="button"
                size="sm"
                onClick={handleStageCredentials}
                disabled={disabled || isStaging || drafts.every((d) => !d.key.trim() || !d.secret)}
                className="h-7 bg-warning text-xs text-warning-foreground hover:bg-warning/90"
              >
                <ShieldCheck className="mr-1 h-3.5 w-3.5" />
                {isStaging ? t('staging') : t('stage')}
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
