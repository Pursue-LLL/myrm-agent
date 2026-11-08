'use client';

/**
 * [INPUT] ./useWikiPurpose::WikiPurposeController (POS: 目的文本的状态与保存动作), @/components/primitives (POS: 卡片、按钮与文本域)
 * [OUTPUT] WikiPurposeCard: “目的 / 方向”卡: 加载中显示占位, 否则显示可编辑的草稿; 草稿与已保存值不同时才出现“重置”并允许保存
 * [POS] 总览页的目的卡, 只负责展示与转发输入, 状态在 useWikiPurpose。
 */

import { useTranslations } from 'next-intl';
import { IconExplore } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Textarea } from '@/components/primitives/textarea';
import type { WikiPurposeController } from './useWikiPurpose';

export function WikiPurposeCard({
  purpose,
  purposeDraft,
  setPurposeDraft,
  isLoadingPurpose,
  isSavingPurpose,
  handleSavePurpose,
}: WikiPurposeController) {
  const t = useTranslations('settings.wiki');

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconExplore className="w-5 h-5" />
          {t('purpose.title')}
        </CardTitle>
        <CardDescription>{t('purpose.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoadingPurpose ? (
          <div className="text-center py-4 text-muted-foreground">{t('loading')}</div>
        ) : (
          <>
            <Textarea
              placeholder={t('purpose.placeholder')}
              value={purposeDraft}
              onChange={(e) => setPurposeDraft(e.target.value)}
              rows={3}
              className="resize-none"
            />
            <div className="flex justify-end gap-2">
              {purposeDraft !== purpose && (
                <Button variant="ghost" size="sm" onClick={() => setPurposeDraft(purpose)}>
                  {t('purpose.reset')}
                </Button>
              )}
              <Button size="sm" onClick={handleSavePurpose} disabled={isSavingPurpose || purposeDraft === purpose}>
                {isSavingPurpose ? t('purpose.saving') : t('purpose.save')}
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
