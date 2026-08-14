'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Switch } from '@/components/primitives/switch';
import { IconEye, IconEyeOff, IconLoader } from '@/components/features/icons/PremiumIcons';
import {
  getChannelCredentials,
  saveChannelCredentials,
  testFeishuConnection,
} from '@/services/channels';

interface FeishuCredentialsEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  channelName: string;
  onSaved?: () => void;
}

interface CredentialForm {
  appId: string;
  appSecret: string;
  useLark: boolean;
}

const EMPTY_FORM: CredentialForm = { appId: '', appSecret: '', useLark: false };

export function FeishuCredentialsEditDialog({
  open,
  onOpenChange,
  channelName,
  onSaved,
}: FeishuCredentialsEditDialogProps) {
  const t = useTranslations('channels');
  const loadSeqRef = useRef(0);
  const [form, setForm] = useState<CredentialForm>(EMPTY_FORM);
  const [showSecret, setShowSecret] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    const requestSeq = ++loadSeqRef.current;
    setForm(EMPTY_FORM);
    setShowSecret(false);
    setSaving(false);
    setTesting(false);
    setLoading(true);
    getChannelCredentials(channelName)
      .then((creds) => {
        // Ignore stale responses when the dialog is re-opened for another
        // instance while a previous request is still in flight.
        if (requestSeq !== loadSeqRef.current) {
          return;
        }
        setForm({
          appId: creds.appId ?? '',
          appSecret: '',
          useLark: creds.useLark === 'true',
        });
      })
      .catch(() => {
        if (requestSeq !== loadSeqRef.current) {
          return;
        }
        setForm(EMPTY_FORM);
      })
      .finally(() => {
        if (requestSeq === loadSeqRef.current) {
          setLoading(false);
        }
      });
  }, [open, channelName]);

  const handleSave = useCallback(async () => {
    const payload: Record<string, string> = {
      appId: form.appId.trim(),
      useLark: String(form.useLark),
    };
    if (form.appSecret.trim()) {
      payload.appSecret = form.appSecret.trim();
    }
    if (!payload.appId) {
      toast.error(t('feishuCredentialsRequired'));
      return;
    }
    setSaving(true);
    try {
      await saveChannelCredentials(channelName, payload);
      toast.success(t('feishuCredentialsSaved'));
      onSaved?.();
      onOpenChange(false);
    } catch {
      toast.error(t('feishuCredentialsSaveError'));
    } finally {
      setSaving(false);
    }
  }, [form, channelName, onOpenChange, onSaved, t]);

  const handleTest = useCallback(async () => {
    if (!form.appId.trim()) {
      toast.error(t('feishuCredentialsRequired'));
      return;
    }
    const secret = form.appSecret.trim();
    if (!secret) {
      toast.error(t('feishuCredentialsSecretHint'));
      return;
    }
    setTesting(true);
    try {
      const result = await testFeishuConnection(form.appId.trim(), secret, form.useLark);
      if (result.ok) {
        toast.success(t('feishuTestSuccess'));
      } else {
        toast.error(result.message || t('feishuTestFailed'));
      }
    } catch {
      toast.error(t('feishuTestFailed'));
    } finally {
      setTesting(false);
    }
  }, [form, t]);

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onOpenChange(false)}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('feishuCredentialsDialogTitle')}</DialogTitle>
        </DialogHeader>
        {loading ? (
          <div className="flex h-32 items-center justify-center">
            <IconLoader className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-4 py-2">
            <p className="text-xs text-muted-foreground">{t('feishuCredentialsDialogHint')}</p>
            <div className="space-y-2">
              <Label htmlFor="feishu-edit-app-id">{t('feishuAppId')}</Label>
              <Input
                id="feishu-edit-app-id"
                placeholder="cli_xxxxx"
                value={form.appId}
                onChange={(e) => setForm((prev) => ({ ...prev, appId: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="feishu-edit-app-secret">{t('feishuAppSecret')}</Label>
              <div className="relative">
                <Input
                  id="feishu-edit-app-secret"
                  type={showSecret ? 'text' : 'password'}
                  placeholder={t('feishuCredentialsSecretPlaceholder')}
                  value={form.appSecret}
                  onChange={(e) => setForm((prev) => ({ ...prev, appSecret: e.target.value }))}
                  className="pr-10"
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-0 flex items-center pr-3 text-muted-foreground hover:text-foreground"
                  onClick={() => setShowSecret((prev) => !prev)}
                >
                  {showSecret ? <IconEyeOff className="h-4 w-4" /> : <IconEye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <div className="flex items-center gap-2 pt-1">
              <Switch
                checked={form.useLark}
                onCheckedChange={(v) => setForm((prev) => ({ ...prev, useLark: v }))}
              />
              <span className="text-sm text-muted-foreground">{t('feishuUseLark')}</span>
            </div>
            <div className="flex items-center gap-3 pt-2">
              <Button onClick={() => void handleSave()} disabled={saving || !form.appId.trim()} size="sm">
                {saving && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
                {t('feishuSave')}
              </Button>
              <Button
                variant="outline"
                onClick={() => void handleTest()}
                disabled={testing || !form.appId.trim() || !form.appSecret.trim()}
                size="sm"
              >
                {testing && <IconLoader className="mr-2 h-3.5 w-3.5 animate-spin" />}
                {t('feishuTestConnection')}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
