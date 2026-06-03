'use client';

import { memo, useState, useRef, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Plus, Trash2, Eye, EyeOff, Check, Pencil, X, Copy, ShieldCheck, RefreshCw, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { ApiKeyConfig } from '@/store/config/providerTypes';
import { toast } from '@/hooks/useToast';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';

type KeyHealthStatus = 'unchecked' | 'checking' | 'valid' | 'invalid';

interface KeyHealthState {
  status: KeyHealthStatus;
  error?: string;
  latencyMs?: number;
}

interface ApiKeyManagerProps {
  apiKeys: ApiKeyConfig[];
  onChange: (apiKeys: ApiKeyConfig[]) => void;
  /** Lightweight probe to verify a single API key. Returns reachability result. */
  onProbeKey?: (apiKey: string) => Promise<{ reachable: boolean; error?: string | null; latency_ms?: number | null }>;
}

const RemarkPopover = memo<{
  remark: string;
  onSave: (remark: string) => void;
  onClose: () => void;
}>(({ remark, onSave, onClose }) => {
  const [value, setValue] = useState(remark);
  const inputRef = useRef<HTMLInputElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      onSave(value);
    } else if (e.key === 'Escape') {
      onClose();
    }
  };

  return (
    <div
      ref={popoverRef}
      className="absolute top-full left-0 mt-1 z-50 p-3 bg-popover border border-border rounded-lg shadow-lg min-w-[200px] animate-in fade-in-0 zoom-in-95 duration-150"
    >
      <div className="flex items-center gap-2">
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          className="flex-1 text-sm bg-background border border-border rounded-full px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
        <button
          onClick={() => onSave(value)}
          className="p-1.5 text-primary hover:bg-primary/10 rounded-full transition-colors"
        >
          <Check className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={onClose}
          className="p-1.5 text-muted-foreground hover:bg-accent rounded-full transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
});

RemarkPopover.displayName = 'RemarkPopover';

const HealthBadge = memo<{ health: KeyHealthState; onRetry?: () => void }>(({ health, onRetry }) => {
  const t = useTranslations('settings.modelService');

  if (health.status === 'unchecked') return null;

  if (health.status === 'checking') {
    return <Loader2 className="w-3.5 h-3.5 animate-spin text-muted-foreground flex-shrink-0" />;
  }

  if (health.status === 'valid') {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400 flex-shrink-0">
            <Check className="w-3 h-3" />
            {health.latencyMs != null && `${health.latencyMs}ms`}
          </span>
        </TooltipTrigger>
        <TooltipContent>{t('keyVerified')}</TooltipContent>
      </Tooltip>
    );
  }

  return (
    <div className="flex items-center gap-1 flex-shrink-0">
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="text-xs text-destructive truncate max-w-[120px]">{health.error || t('keyInvalid')}</span>
        </TooltipTrigger>
        <TooltipContent>{health.error || t('keyInvalid')}</TooltipContent>
      </Tooltip>
      {onRetry && (
        <button
          onClick={onRetry}
          className="p-0.5 text-muted-foreground hover:text-primary transition-colors"
          title={t('retryVerify')}
        >
          <RefreshCw className="w-3 h-3" />
        </button>
      )}
    </div>
  );
});

HealthBadge.displayName = 'HealthBadge';

const ApiKeyManager = memo<ApiKeyManagerProps>(({ apiKeys, onChange, onProbeKey }) => {
  const t = useTranslations('settings.modelService');
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [newKey, setNewKey] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [editingRemarkId, setEditingRemarkId] = useState<string | null>(null);
  const [healthMap, setHealthMap] = useState<Record<string, KeyHealthState>>({});
  const autoProbedKeysRef = useRef<Set<string>>(new Set());

  const probeKeyHealth = useCallback(
    async (keyId: string, keyValue: string) => {
      if (!onProbeKey) return;
      setHealthMap((prev) => ({ ...prev, [keyId]: { status: 'checking' } }));
      try {
        const result = await onProbeKey(keyValue);
        setHealthMap((prev) => ({
          ...prev,
          [keyId]: result.reachable
            ? { status: 'valid', latencyMs: result.latency_ms ?? undefined }
            : { status: 'invalid', error: result.error ?? undefined },
        }));
      } catch {
        setHealthMap((prev) => ({
          ...prev,
          [keyId]: { status: 'invalid', error: 'Probe failed' },
        }));
      }
    },
    [onProbeKey],
  );

  // Automatically probe active API keys when component mounts or when keys list changes
  useEffect(() => {
    if (!onProbeKey || !apiKeys || apiKeys.length === 0) return;

    apiKeys.forEach((apiKey) => {
      if (apiKey.isActive && !autoProbedKeysRef.current.has(apiKey.id)) {
        autoProbedKeysRef.current.add(apiKey.id);
        probeKeyHealth(apiKey.id, apiKey.key);
      }
    });
  }, [apiKeys, onProbeKey, probeKeyHealth]);

  const toggleShowKey = (id: string) => {
    setShowKeys((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const handleStartAdding = useCallback(() => {
    setIsAdding(true);
  }, []);

  const handleAddKey = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!newKey.trim()) return;

    const newApiKey: ApiKeyConfig = {
      id: `key_${Date.now()}`,
      key: newKey.trim(),
      remark: t('defaultKeyRemark'),
      isActive: true,
    };

    onChange([...(apiKeys ?? []), newApiKey]);
    setNewKey('');
    setIsAdding(false);

    if (onProbeKey) {
      probeKeyHealth(newApiKey.id, newApiKey.key);
    }
  };

  const handleRemoveKey = (id: string) => {
    const updated = (apiKeys ?? []).filter((k) => k.id !== id);
    if (updated.length > 0 && !updated.some((k) => k.isActive)) {
      updated[0].isActive = true;
    }
    onChange(updated);
    setHealthMap((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  };

  const handleToggleActive = (id: string) => {
    const target = (apiKeys ?? []).find((k) => k.id === id);
    if (!target) return;

    if (target.isActive) {
      const activeCount = (apiKeys ?? []).filter((k) => k.isActive).length;
      if (activeCount <= 1) return;
    }

    onChange((apiKeys ?? []).map((k) => (k.id === id ? { ...k, isActive: !k.isActive } : k)));
  };

  const handleUpdateRemark = (id: string, remark: string) => {
    onChange((apiKeys ?? []).map((k) => (k.id === id ? { ...k, remark } : k)));
    setEditingRemarkId(null);
  };

  const maskKey = (key: string) => {
    if (key.length <= 8) return '••••••••';
    return '•'.repeat(key.length);
  };

  const handleCopyKey = async (key: string) => {
    try {
      await writeToClipboard(key);
      toast({
        title: t('copySuccess'),
        duration: 3000,
      });
    } catch {
      // silent
    }
  };

  const activeCount = (apiKeys ?? []).filter((k) => k.isActive).length;

  return (
    <div className="space-y-4">
      {/* Pool status indicator */}
      {activeCount > 1 && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary/5 border border-primary/20 text-xs text-primary">
          <div className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
          {t('keyPoolActive', { count: activeCount })}
        </div>
      )}

      {/* Key list */}
      {(apiKeys?.length ?? 0) > 0 && (
        <div className="space-y-3">
          {(apiKeys ?? []).map((apiKey, idx) => (
            <div
              key={apiKey.id || `apikey-${idx}`}
              className={cn(
                'p-4 rounded-xl border transition-all duration-200',
                apiKey.isActive
                  ? 'border-primary/50 bg-primary/5'
                  : 'border-border/50 bg-background/50 hover:border-border opacity-60',
              )}
            >
              {/* Row 1: toggle, remark, health, actions */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  {/* Toggle switch */}
                  <button
                    onClick={() => handleToggleActive(apiKey.id)}
                    className={cn(
                      'relative w-9 h-5 rounded-full transition-all duration-200 flex-shrink-0',
                      apiKey.isActive ? 'bg-accent-warm' : 'bg-border',
                    )}
                    title={apiKey.isActive ? t('keyEnabled') : t('keyDisabled')}
                  >
                    <div
                      className={cn(
                        'absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all duration-200',
                        apiKey.isActive ? 'left-[18px]' : 'left-0.5',
                      )}
                    />
                  </button>

                  {/* Remark */}
                  <div className="relative flex items-center gap-1.5">
                    <span className="text-sm text-muted-foreground">{apiKey.remark || t('defaultKeyRemark')}</span>
                    <button
                      onClick={() => setEditingRemarkId(apiKey.id)}
                      className="p-1 text-muted-foreground hover:text-foreground hover:bg-accent rounded transition-colors"
                      title={t('remarkPlaceholder')}
                    >
                      <Pencil className="w-3 h-3" />
                    </button>
                    {editingRemarkId === apiKey.id && (
                      <RemarkPopover
                        remark={apiKey.remark}
                        onSave={(remark) => handleUpdateRemark(apiKey.id, remark)}
                        onClose={() => setEditingRemarkId(null)}
                      />
                    )}
                  </div>

                  {/* Health badge */}
                  {healthMap[apiKey.id] && (
                    <HealthBadge
                      health={healthMap[apiKey.id]}
                      onRetry={
                        healthMap[apiKey.id].status === 'invalid'
                          ? () => probeKeyHealth(apiKey.id, apiKey.key)
                          : undefined
                      }
                    />
                  )}
                </div>

                <button
                  onClick={() => handleRemoveKey(apiKey.id)}
                  className="p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
                  title={t('removeKey')}
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>

              {/* Row 2: key value */}
              <div className="flex items-center gap-2 sm:gap-3 w-full">
                <code className="flex-1 min-w-0 block text-xs sm:text-sm text-foreground font-mono bg-secondary/50 px-3 py-2 rounded-lg overflow-x-auto whitespace-nowrap">
                  {showKeys[apiKey.id] ? apiKey.key : maskKey(apiKey.key)}
                </code>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="p-2 text-emerald-500 dark:text-emerald-400 cursor-default">
                        <ShieldCheck className="w-4 h-4" />
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>{t('encryptedLocallyDesc')}</TooltipContent>
                  </Tooltip>
                  <button
                    onClick={() => handleCopyKey(apiKey.key)}
                    className="p-2 text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
                    title={t('copyKey')}
                  >
                    <Copy className="w-[18px] h-[18px]" />
                  </button>
                  <button
                    onClick={() => toggleShowKey(apiKey.id)}
                    className="p-2 text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
                  >
                    {showKeys[apiKey.id] ? (
                      <EyeOff className="w-[18px] h-[18px]" />
                    ) : (
                      <Eye className="w-[18px] h-[18px]" />
                    )}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add new key */}
      {isAdding ? (
        <form
          onSubmit={handleAddKey}
          className="p-5 rounded-xl border border-dashed border-primary/50 bg-primary/5 space-y-5"
        >
          <div className="space-y-4">
            <label className="text-sm font-medium text-foreground block">{t('apiKeyPlaceholder')}</label>
            <input
              type="text"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              placeholder="sk-..."
              className="w-full px-4 py-3 text-sm bg-background border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/30"
              autoComplete="new-password"
              autoFocus
            />
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500 dark:text-emerald-400" />
              <span>{t('apiKeySecurityHint')}</span>
            </div>
          </div>
          <div className="flex gap-3">
            <button
              type="submit"
              disabled={!newKey.trim()}
              className={cn(
                'flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-semibold transition-all',
                newKey.trim()
                  ? 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-lg shadow-primary/20'
                  : 'bg-muted text-muted-foreground cursor-not-allowed',
              )}
            >
              <Plus className="w-4 h-4" />
              {t('addKey')}
            </button>
            <button
              type="button"
              onClick={() => {
                setIsAdding(false);
                setNewKey('');
              }}
              className="px-4 py-3 rounded-xl text-sm font-medium text-muted-foreground hover:bg-accent transition-colors"
            >
              {t('cancel')}
            </button>
          </div>
        </form>
      ) : (
        <button
          onClick={handleStartAdding}
          className="w-full flex items-center justify-center gap-2 px-4 py-4 rounded-xl border border-dashed border-border hover:border-primary/50 hover:bg-primary/5 text-muted-foreground hover:text-primary transition-all"
        >
          <Plus className="w-[18px] h-[18px]" />
          <span className="text-sm font-medium">{t('addKey')}</span>
        </button>
      )}
    </div>
  );
});

ApiKeyManager.displayName = 'ApiKeyManager';

export default ApiKeyManager;
