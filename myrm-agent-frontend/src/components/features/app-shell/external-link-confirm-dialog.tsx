/**
 * [INPUT]
 * - @/store/useExternalLinkConfirmStore (POS: 外链确认弹窗的单槽状态，含单飞与拒绝后静默)
 * - @/lib/desktop-bridge::desktopBridge (POS: 桌面桥接单例，外链经系统浏览器打开)
 * - @/components/primitives/alert-dialog (POS: 模态确认原语，默认聚焦取消、点击遮罩不关闭)
 *
 * [OUTPUT]
 * - ExternalLinkConfirmDialog: 不可信内嵌内容请求打开外链时的确认弹窗，完整展示将要打开的地址
 *
 * [POS]
 * 根布局级模态，与 ExternalLinkInitializer 同级 eager 挂载；只会被桌面端触发（见 @/lib/untrusted-link）。
 * 地址放在只读文本框里：长地址可滚动、可键盘浏览、可复制核对，而不会把弹窗撑出屏幕。
 */
'use client';

import { useTranslations } from 'next-intl';

import { IconExternalLink } from '@/components/features/icons/PremiumIcons';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { Textarea } from '@/components/primitives/textarea';
import { desktopBridge } from '@/lib/desktop-bridge';
import { useExternalLinkConfirmStore } from '@/store/useExternalLinkConfirmStore';

export default function ExternalLinkConfirmDialog() {
  const t = useTranslations('externalLinkConfirm');
  const { open, link, approve, decline } = useExternalLinkConfirmStore();

  if (!link) {
    return null;
  }

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      decline();
    }
  };

  const handleOpen = () => {
    void desktopBridge.shell.openExternalUrl(link.url);
    approve();
  };

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary sm:mx-0">
            <IconExternalLink className="h-5 w-5" />
          </div>
          <AlertDialogTitle>{t('title')}</AlertDialogTitle>
          <AlertDialogDescription>
            {link.source ? t('descriptionNamed', { source: link.source }) : t('descriptionAnonymous')}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <Textarea
          readOnly
          rows={4}
          value={link.url}
          aria-label={t('urlLabel')}
          className="resize-none bg-muted/50 font-mono text-xs md:text-xs"
        />
        <AlertDialogFooter>
          <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction onClick={handleOpen}>{t('open')}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
