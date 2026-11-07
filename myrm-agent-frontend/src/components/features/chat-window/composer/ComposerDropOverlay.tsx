'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: 文案)
 *
 * [OUTPUT]
 * - ComposerDropOverlay: 拖放进行中盖在输入区上的提示层。
 *
 * [POS]
 * 只展示、不接事件（`pointer-events-none`），拖放仍由表单上的处理器完成。拖的是历史会话还是文件，提示语不同。
 */
import { useTranslations } from 'next-intl';

interface ComposerDropOverlayProps {
  /** The drag carries a prior chat rather than files. */
  session: boolean;
}

export function ComposerDropOverlay({ session }: ComposerDropOverlayProps) {
  const t = useTranslations('chat');

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-primary/10 backdrop-blur-sm border-2 border-dashed border-primary rounded-lg pointer-events-none">
      <div className="text-center">
        <div className="text-2xl font-semibold text-primary mb-2">
          {session ? t('dragDrop.sessionTitle') : t('dragDrop.title')}
        </div>
        <div className="text-sm text-muted-foreground">
          {session ? t('dragDrop.sessionDescription') : t('dragDrop.description')}
        </div>
      </div>
    </div>
  );
}
