'use client';

/**
 * [INPUT] ./useBatchProjectCreate::BatchProjectCreate (POS: 表单 / 看板 / 目录选择 / 提交状态), ./BatchDirectoryPicker (POS: 目录选择器)
 * [OUTPUT] BatchProjectCreateCard: 创建向导卡片（名称、提示词、目录、看板、并发、产物匹配、通知与审批开关、取消 / 创建按钮）
 * [POS] 列表页的创建向导视图；状态全部来自 useBatchProjectCreate，本组件只负责渲染与回调。
 */

import { useTranslations } from 'next-intl';
import { Loader2, Play } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Switch } from '@/components/primitives/switch';
import { Textarea } from '@/components/primitives/textarea';
import { BatchDirectoryPicker } from './BatchDirectoryPicker';
import type { BatchProjectCreate } from './useBatchProjectCreate';

interface BatchProjectCreateCardProps {
  create: BatchProjectCreate;
  onCancel: () => void;
}

export function BatchProjectCreateCard({ create, onCancel }: BatchProjectCreateCardProps) {
  const t = useTranslations('batchDirectory');
  const { form, updateForm, boards, creating, dirs, submit } = create;

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle>{t('createTitle')}</CardTitle>
        <CardDescription>{t('createDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor="bd-name">{t('nameLabel')}</Label>
            <Input
              id="bd-name"
              value={form.name}
              onChange={(e) => updateForm({ name: e.target.value })}
              placeholder={t('namePlaceholder')}
              maxLength={255}
            />
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="bd-prompt">{t('promptLabel')}</Label>
            <Textarea
              id="bd-prompt"
              value={form.prompt}
              onChange={(e) => updateForm({ prompt: e.target.value })}
              placeholder={t('promptPlaceholder')}
              rows={4}
            />
          </div>

          <BatchDirectoryPicker dirs={dirs} />

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="bd-board">{t('boardLabel')}</Label>
              <select
                id="bd-board"
                value={form.board_id}
                onChange={(e) => updateForm({ board_id: e.target.value })}
                className="h-9 rounded-md border bg-transparent px-3 text-sm"
              >
                <option value="">{t('boardAuto')}</option>
                {boards.map((b) => (
                  <option key={b.board_id} value={b.board_id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="bd-concurrency">{t('concurrencyLabel')}</Label>
              <Input
                id="bd-concurrency"
                type="number"
                min={1}
                max={50}
                value={form.concurrency}
                onChange={(e) => updateForm({ concurrency: e.target.value })}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="bd-artifacts">{t('artifactPatternsLabel')}</Label>
              <Input
                id="bd-artifacts"
                value={form.artifact_patterns}
                onChange={(e) => updateForm({ artifact_patterns: e.target.value })}
                placeholder={t('artifactPatternsPlaceholder')}
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Switch
              id="bd-notify"
              checked={form.notify_enabled}
              onCheckedChange={(v) => updateForm({ notify_enabled: v })}
            />
            <Label htmlFor="bd-notify">{t('notifyLabel')}</Label>
          </div>
          <div className="flex items-center gap-2">
            <Switch
              id="bd-approval"
              checked={form.require_approval}
              onCheckedChange={(v) => updateForm({ require_approval: v })}
            />
            <Label htmlFor="bd-approval">{t('approvalLabel')}</Label>
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onCancel}>
            {t('cancelButton')}
          </Button>
          <Button onClick={() => void submit()} disabled={creating}>
            {creating ? <Loader2 className="size-4 mr-1 animate-spin" /> : <Play className="size-4 mr-1" />}
            {t('createButton')}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
