'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { ChannelLoginDialog } from './ChannelLoginDialog';

interface QrLoginButtonProps {
  channelId: string;
  channelLabel: string;
  loginMethod?: string;
  onSuccess?: () => void;
  className?: string;
}

/**
 * Reusable "Scan to Connect" button + login dialog trigger.
 *
 * Use in any channel card that supports QR code login (WeChat, WhatsApp, etc.).
 */
export function QrLoginButton({
  channelId,
  channelLabel,
  loginMethod = 'qr_code',
  onSuccess,
  className,
}: QrLoginButtonProps) {
  const t = useTranslations('channels');
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setDialogOpen(true)}
        className={
          className ??
          'inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90'
        }
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 3h7v7H3V3zm11 0h7v7h-7V3zM3 14h7v7H3v-7zm14 3h.01M17 17h.01M21 17h.01M14 14h3v3h-3v-3zm0 7h7v-3h-3m-4 0v-4"
          />
        </svg>
        {t('qrLoginConnect')}
      </button>

      <ChannelLoginDialog
        channelId={channelId}
        channelLabel={channelLabel}
        loginMethod={loginMethod}
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onSuccess={onSuccess}
      />
    </>
  );
}
