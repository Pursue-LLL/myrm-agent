'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: 前端国际化)
 * - qrcode.react::QRCodeSVG (POS: 纯 SVG 二维码渲染)
 * - @/components/primitives/* (POS: UI 基础原子组件)
 *
 * [OUTPUT]
 * - PublishShareCard: 工件发布成功态分享卡片（链接展示、密码复制、手机扫码）
 *
 * [POS]
 * 前端 Artifacts 特性组件层。承载工件发布成功后的分享卡片、密码复制与移动端扫码交互。
 */

import React from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { CheckCircle2, Copy, ExternalLink, QrCode, Lock, KeyRound, Share2, Check } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { useTranslations } from 'next-intl';

export interface PublishShareCardProps {
  publishUrl: string;
  artifactTitle: string;
  isProtected: boolean;
  password?: string;
  copiedType: 'none' | 'url' | 'password' | 'all';
  onCopyUrl: () => void;
  onCopyPassword: () => void;
  onCopyShareDetails: () => void;
  onDone: () => void;
}

export const PublishShareCard: React.FC<PublishShareCardProps> = ({
  publishUrl,
  artifactTitle,
  isProtected,
  password,
  copiedType,
  onCopyUrl,
  onCopyPassword,
  onCopyShareDetails,
  onDone,
}) => {
  const t = useTranslations('artifacts.publish');

  return (
    <div className="space-y-4 animate-in fade-in zoom-in-95 duration-500">
      <div className="text-center space-y-1.5">
        <div className="inline-flex p-2.5 bg-green-500/10 dark:bg-green-500/20 rounded-full text-green-500">
          <CheckCircle2 className="w-7 h-7" />
        </div>
        <h3 className="text-lg font-semibold text-foreground">{t('successTitle')}</h3>
        <p className="text-xs text-muted-foreground">{t('successDescription')}</p>
      </div>

      <div className="p-3.5 rounded-2xl border border-border bg-muted/20 space-y-3">
        <div className="flex items-center justify-between gap-2 border-b border-border/50 pb-2.5">
          <span className="text-xs font-semibold text-foreground truncate max-w-[240px]">
            {artifactTitle || t('title')}
          </span>
          {isProtected && password ? (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
              <Lock className="w-3 h-3" />
              {t('protectedBadge')}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-primary/10 text-primary border border-primary/20">
              {t('publicBadge')}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5 p-1 bg-background border border-border rounded-xl">
          <Input
            value={publishUrl}
            readOnly
            className="bg-transparent border-none focus-visible:ring-0 font-mono text-xs text-primary shadow-none h-8 px-2 select-all"
          />
          <div className="flex gap-1 pr-1 shrink-0">
            <Button
              size="icon"
              variant="ghost"
              onClick={onCopyUrl}
              className="h-7 w-7 hover:bg-muted rounded-lg"
              title={t('urlCopied')}
            >
              {copiedType === 'url' ? (
                <Check className="w-3.5 h-3.5 text-green-500" />
              ) : (
                <Copy className="w-3.5 h-3.5 text-muted-foreground" />
              )}
            </Button>
            <Button
              size="icon"
              variant="ghost"
              onClick={() => window.open(publishUrl, '_blank')}
              className="h-7 w-7 hover:bg-muted rounded-lg"
            >
              <ExternalLink className="w-3.5 h-3.5 text-muted-foreground" />
            </Button>
          </div>
        </div>

        {isProtected && password && (
          <div className="flex items-center justify-between p-2 bg-background border border-border rounded-xl text-xs font-mono">
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <KeyRound className="w-3.5 h-3.5 text-amber-500 shrink-0" />
              <span>{t('passwordLabel')}:</span>
              <span className="font-semibold text-foreground select-all">{password}</span>
            </div>
            <Button
              size="sm"
              variant="ghost"
              onClick={onCopyPassword}
              className="h-6 px-2 text-[11px] hover:bg-muted rounded-lg gap-1"
            >
              {copiedType === 'password' ? (
                <Check className="w-3 h-3 text-green-500" />
              ) : (
                <Copy className="w-3 h-3 text-muted-foreground" />
              )}
              <span>{t('copyPassword')}</span>
            </Button>
          </div>
        )}

        <div className="flex flex-col sm:flex-row items-center gap-3 pt-0.5">
          <div className="p-1.5 bg-white rounded-xl shadow-xs border border-border/80 shrink-0">
            <QRCodeSVG value={publishUrl} size={84} level="M" />
          </div>
          <div className="flex flex-col justify-center text-left space-y-1.5 min-w-0 w-full sm:w-auto">
            <div className="flex items-center gap-1 text-xs font-medium text-foreground">
              <QrCode className="w-3.5 h-3.5 text-primary shrink-0" />
              <span>{t('scanQrCode')}</span>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="h-7 rounded-lg text-xs gap-1.5 w-full sm:w-fit"
              onClick={onCopyShareDetails}
            >
              {copiedType === 'all' ? (
                <Check className="w-3.5 h-3.5 text-green-500" />
              ) : (
                <Share2 className="w-3.5 h-3.5 text-muted-foreground" />
              )}
              <span>{t('copyShareInfo')}</span>
            </Button>
          </div>
        </div>
      </div>

      <Button onClick={onDone} variant="outline" className="w-full rounded-xl">
        {t('done')}
      </Button>
    </div>
  );
};
