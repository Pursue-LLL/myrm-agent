'use client';

import React, { useState, useCallback, useId } from 'react';
import {
  Key,
  ShieldCheck,
  Eye,
  EyeOff,
  Plus,
  Trash2,
  Clock,
  AlertTriangle,
  CheckCircle2,
  Lock,
} from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Badge } from '@/components/primitives/badge';
import { toast } from '@/lib/utils/toast';
import { API_BASE_URL } from '@/lib/api';

const BLOCKED_SYSTEM_KEYS = new Set([
  'PATH',
  'LD_PRELOAD',
  'LD_LIBRARY_PATH',
  'PYTHONPATH',
  'NODE_OPTIONS',
  'BASH_ENV',
  'ENV',
  'PROMPT_COMMAND',
  'HOME',
  'SHELL',
  'USER',
  'LOGNAME',
]);

export interface CredentialDraft {
  id: string;
  key: string;
  secret: string;
  ttlSeconds: number;
  singleUse: boolean;
  showSecret: boolean;
}

export interface StagedCredentialSummary {
  handleId: string;
  key: string;
  singleUse: boolean;
  expiresAt: number;
}

export interface MaskedCredentialInputCardProps {
  approvalId: string;
  stagedHandles: string[];
  onStagedChange: (handles: string[]) => void;
  disabled?: boolean;
  className?: string;
}

function validateKeyName(key: string): { isValid: boolean; error?: string } {
  const trimmed = key.trim().toUpperCase();
  if (!trimmed) {
    return { isValid: false, error: 'Key name cannot be empty' };
  }
  if (!/^[A-Z_][A-Z0-9_]*$/.test(trimmed)) {
    return {
      isValid: false,
      error: 'Key must only contain uppercase letters, numbers and underscores',
    };
  }
  if (BLOCKED_SYSTEM_KEYS.has(trimmed)) {
    return {
      isValid: false,
      error: `"${trimmed}" is a protected system environment variable and is blocked`,
    };
  }
  return { isValid: true };
}

export function MaskedCredentialInputCard({
  approvalId,
  stagedHandles,
  onStagedChange,
  disabled = false,
  className = '',
}: MaskedCredentialInputCardProps) {
  const initialId = useId();
  const [drafts, setDrafts] = useState<CredentialDraft[]>([
    {
      id: initialId,
      key: '',
      secret: '',
      ttlSeconds: 60,
      singleUse: true,
      showSecret: false,
    },
  ]);
  const [isStaging, setIsStaging] = useState(false);
  const [stagedSummaries, setStagedSummaries] = useState<StagedCredentialSummary[]>([]);

  const handleAddRow = useCallback(() => {
    setDrafts((prev) => [
      ...prev,
      {
        id: `draft-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        key: '',
        secret: '',
        ttlSeconds: 60,
        singleUse: true,
        showSecret: false,
      },
    ]);
  }, []);

  const handleRemoveRow = useCallback((id: string) => {
    setDrafts((prev) => prev.filter((d) => d.id !== id));
  }, []);

  const handleUpdateDraft = useCallback(
    <K extends keyof CredentialDraft>(id: string, field: K, value: CredentialDraft[K]) => {
      setDrafts((prev) =>
        prev.map((d) => (d.id === id ? { ...d, [field]: value } : d)),
      );
    },
    [],
  );

  const handleStageCredentials = async () => {
    // Validate all drafts
    const validDrafts = drafts.filter((d) => d.key.trim() && d.secret);
    if (validDrafts.length === 0) {
      toast.warning('Please provide at least one credential with key and secret.');
      return;
    }

    for (const d of validDrafts) {
      const val = validateKeyName(d.key);
      if (!val.isValid) {
        toast.error(val.error || 'Invalid credential key name');
        return;
      }
    }

    setIsStaging(true);
    try {
      const payload = {
        credentials: validDrafts.map((d) => ({
          key: d.key.trim().toUpperCase(),
          secret: d.secret,
          ttl_seconds: d.ttlSeconds,
          single_use: d.singleUse,
        })),
      };

      const resp = await fetch(`${API_BASE_URL}/approvals/${approvalId}/credentials`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        const errorData = (await resp.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errorData.detail || `Server responded with ${resp.status}`);
      }

      const resData = (await resp.json()) as {
        staged: Array<{
          handle_id: string;
          key: string;
          single_use: boolean;
          expires_at: number;
        }>;
      };

      const newHandles = resData.staged.map((s) => s.handle_id);
      const newSummaries: StagedCredentialSummary[] = resData.staged.map((s) => ({
        handleId: s.handle_id,
        key: s.key,
        singleUse: s.single_use,
        expiresAt: s.expires_at,
      }));

      // Immediately clear in-memory plaintext secrets from the UI state
      setDrafts([]);
      setStagedSummaries(newSummaries);
      onStagedChange([...stagedHandles, ...newHandles]);
      toast.success('Credentials securely masked and staged for single execution.');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      toast.error(`Failed to stage credentials: ${message}`);
    } finally {
      setIsStaging(false);
    }
  };

  const handleRevokeStaged = () => {
    setStagedSummaries([]);
    onStagedChange([]);
    setDrafts([
      {
        id: `draft-${Date.now()}`,
        key: '',
        secret: '',
        ttlSeconds: 60,
        singleUse: true,
        showSecret: false,
      },
    ]);
    toast.info('Staged credentials cleared.');
  };

  const hasStaged = stagedSummaries.length > 0;

  return (
    <div
      className={`rounded-lg border border-amber-500/30 bg-amber-500/5 dark:bg-amber-950/20 p-4 transition-colors ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 pb-3 border-b border-amber-500/20">
        <div className="flex items-center gap-2">
          <Key className="h-4 w-4 text-amber-600 dark:text-amber-400" />
          <span className="text-sm font-medium text-foreground">
            Ephemeral Credentials & Single-Use Gate
          </span>
          <Badge
            variant="outline"
            className="flex items-center gap-1 border-amber-500/40 text-[11px] text-amber-700 dark:text-amber-300"
          >
            <ShieldCheck className="h-3 w-3" />
            Zero-Disk / Auto-Wipe
          </Badge>
        </div>

        {hasStaged && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleRevokeStaged}
            disabled={disabled}
            className="h-7 text-xs text-muted-foreground hover:text-destructive"
          >
            <Trash2 className="h-3.5 w-3.5 mr-1" />
            Revoke
          </Button>
        )}
      </div>

      <p className="mt-2 text-xs text-muted-foreground leading-relaxed">
        Pass sensitive credentials (e.g. database password, OAuth tokens) directly to the
        sandbox process. Secrets are isolated in ephemeral memory, never written to disk, and
        never exposed to LLM context or chat logs.
      </p>

      {/* Staged summaries view */}
      {hasStaged ? (
        <div className="mt-3 space-y-2">
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 dark:bg-emerald-950/30 p-2.5">
            <div className="flex items-center gap-2 text-xs font-medium text-emerald-700 dark:text-emerald-300 mb-1.5">
              <CheckCircle2 className="h-4 w-4" />
              Credentials Staged Ready for Execution
            </div>
            <ul className="space-y-1">
              {stagedSummaries.map((s) => (
                <li
                  key={s.handleId}
                  className="flex items-center justify-between text-[11px] font-mono text-muted-foreground"
                >
                  <span className="font-semibold text-foreground">{s.key}</span>
                  <span className="truncate max-w-[200px] text-xs text-muted-foreground">
                    {s.handleId.slice(0, 20)}...
                  </span>
                  <Badge variant="secondary" className="text-[10px] py-0 px-1.5 h-4">
                    Single-Use
                  </Badge>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : (
        /* Input drafts form */
        <div className="mt-3 space-y-3">
          {drafts.map((draft, idx) => {
            const keyValidation = draft.key ? validateKeyName(draft.key) : { isValid: true };
            return (
              <div
                key={draft.id}
                className="rounded-md border border-border/60 bg-background/80 p-2.5 space-y-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-medium text-muted-foreground">
                    Credential #{idx + 1}
                  </span>
                  {drafts.length > 1 && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemoveRow(draft.id)}
                      className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                      disabled={disabled}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  )}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {/* Key input */}
                  <div>
                    <label
                      htmlFor={`cred-key-${draft.id}`}
                      className="text-[11px] text-muted-foreground block mb-0.5"
                    >
                      Variable Key (e.g. DB_PASS)
                    </label>
                    <Input
                      id={`cred-key-${draft.id}`}
                      type="text"
                      placeholder="API_SECRET_KEY"
                      value={draft.key}
                      onChange={(e) =>
                        handleUpdateDraft(draft.id, 'key', e.target.value.toUpperCase())
                      }
                      disabled={disabled || isStaging}
                      className="h-8 text-xs font-mono"
                    />
                    {!keyValidation.isValid && (
                      <p className="mt-1 text-[10px] text-destructive flex items-center gap-1">
                        <AlertTriangle className="h-3 w-3 shrink-0" />
                        {keyValidation.error}
                      </p>
                    )}
                  </div>

                  {/* Secret input */}
                  <div>
                    <label
                      htmlFor={`cred-secret-${draft.id}`}
                      className="text-[11px] text-muted-foreground block mb-0.5"
                    >
                      Secret Value (Masked)
                    </label>
                    <div className="relative">
                      <Input
                        id={`cred-secret-${draft.id}`}
                        type={draft.showSecret ? 'text' : 'password'}
                        placeholder="••••••••••••"
                        value={draft.secret}
                        onChange={(e) =>
                          handleUpdateDraft(draft.id, 'secret', e.target.value)
                        }
                        disabled={disabled || isStaging}
                        className="h-8 text-xs pr-8 font-mono"
                      />
                      <button
                        type="button"
                        onClick={() =>
                          handleUpdateDraft(draft.id, 'showSecret', !draft.showSecret)
                        }
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground p-0.5"
                        tabIndex={-1}
                      >
                        {draft.showSecret ? (
                          <EyeOff className="h-3.5 w-3.5" />
                        ) : (
                          <Eye className="h-3.5 w-3.5" />
                        )}
                      </button>
                    </div>
                  </div>
                </div>

                {/* TTL & Policy info */}
                <div className="flex items-center justify-between text-[11px] pt-1 border-t border-border/40">
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <Clock className="h-3 w-3" />
                    <span>TTL:</span>
                    <select
                      value={draft.ttlSeconds}
                      onChange={(e) =>
                        handleUpdateDraft(draft.id, 'ttlSeconds', Number(e.target.value))
                      }
                      disabled={disabled || isStaging}
                      className="bg-transparent border border-border/60 rounded px-1.5 py-0.5 text-[11px] text-foreground focus:outline-none"
                    >
                      <option value={30}>30s</option>
                      <option value={60}>60s (Default)</option>
                      <option value={120}>2 mins</option>
                      <option value={300}>5 mins</option>
                    </select>
                  </div>

                  <div className="flex items-center gap-1 text-muted-foreground">
                    <Lock className="h-3 w-3 text-amber-500" />
                    <span>Single-use ticket enforced</span>
                  </div>
                </div>
              </div>
            );
          })}

          {/* Action buttons */}
          <div className="flex items-center justify-between gap-2 pt-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleAddRow}
              disabled={disabled || isStaging}
              className="h-7 text-xs"
            >
              <Plus className="h-3.5 w-3.5 mr-1" />
              Add Another Key
            </Button>

            <Button
              type="button"
              size="sm"
              onClick={handleStageCredentials}
              disabled={
                disabled ||
                isStaging ||
                drafts.every((d) => !d.key.trim() || !d.secret)
              }
              className="h-7 text-xs bg-amber-600 hover:bg-amber-700 text-white"
            >
              <ShieldCheck className="h-3.5 w-3.5 mr-1" />
              {isStaging ? 'Securing...' : 'Stage Masked Credentials'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
