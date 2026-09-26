'use client';

import { useState } from 'react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';

export interface PairingFormProps {
  fixedChannel?: string;
  channelOptions: string[];
  mode?: 'allowlist' | 'pairing';
  channelLabel: (channel: string) => string;
  senderIdPlaceholder: (channel: string) => string;
  senderIdHint: (channel: string) => string;
  onSubmit: (channel: string, senderId: string, role: 'admin' | 'member', dailyQuota: number | null) => Promise<void>;
  onCancel: () => void;
  t: (key: string, values?: Record<string, string | number>) => string;
}

export function PairingForm({
  fixedChannel,
  channelOptions,
  mode,
  channelLabel,
  senderIdPlaceholder,
  senderIdHint,
  onSubmit,
  onCancel,
  t,
}: PairingFormProps) {
  const [channel, setChannel] = useState(fixedChannel ?? '');
  const [senderId, setSenderId] = useState('');
  const [role, setRole] = useState<'admin' | 'member'>('member');
  const [dailyQuota, setDailyQuota] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const effectiveChannel = fixedChannel ?? channel;

  const handleSubmit = async () => {
    if (!effectiveChannel || !senderId.trim()) return;
    setSubmitting(true);
    try {
      const quotaNum = dailyQuota.trim() ? Math.max(1, parseInt(dailyQuota.trim(), 10)) : null;
      await onSubmit(effectiveChannel, senderId.trim(), role, Number.isNaN(quotaNum) ? null : quotaNum);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      <div className={fixedChannel ? 'space-y-3' : 'grid gap-3 sm:grid-cols-2'}>
        {!fixedChannel && (
          <div>
            <Label className="text-xs">{t('channel')}</Label>
            <Select value={channel} onValueChange={setChannel}>
              <SelectTrigger>
                <SelectValue placeholder={t('selectChannel')} />
              </SelectTrigger>
              <SelectContent>
                {channelOptions.map((ch) => (
                  <SelectItem key={ch} value={ch}>
                    {channelLabel(ch)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <div>
          <Label className="text-xs">{t('senderId')}</Label>
          <Input
            value={senderId}
            onChange={(e) => setSenderId(e.target.value)}
            placeholder={senderIdPlaceholder(effectiveChannel)}
            className="font-mono text-sm"
          />
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <Label className="text-xs">{t('role') || '角色'}</Label>
          <Select value={role} onValueChange={(v) => setRole(v as 'admin' | 'member')}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="member">{t('roleMember') || '协作成员 (Member)'}</SelectItem>
              <SelectItem value="admin">{t('roleAdmin') || '所有者 (Admin)'}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs">{t('dailyQuota') || '每日限额'}</Label>
          <Input
            type="number"
            min="1"
            value={dailyQuota}
            onChange={(e) => setDailyQuota(e.target.value)}
            placeholder={t('dailyQuotaPlaceholder') || '默认无限制，如 50'}
            className="text-sm"
            disabled={role === 'admin'}
          />
        </div>
      </div>

      <p className="text-xs text-muted-foreground">{senderIdHint(effectiveChannel)}</p>
      {mode !== 'pairing' && <p className="text-xs text-muted-foreground/70 italic">{t('dontKnowIdHint')}</p>}

      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onCancel}>
          {t('cancel')}
        </Button>
        <Button size="sm" onClick={handleSubmit} disabled={submitting || !effectiveChannel || !senderId.trim()}>
          {submitting ? t('adding') : t('add')}
        </Button>
      </div>
    </div>
  );
}
