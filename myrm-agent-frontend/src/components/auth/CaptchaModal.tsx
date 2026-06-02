'use client';

import { useState, useEffect, useCallback } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Shield, X, Loader2, AlertCircle } from 'lucide-react';
import { localizeReactNode, selectLocalizedText } from '@/lib/utils/localeText';

interface CaptchaModalProps {
  isOpen: boolean;
  onClose: () => void;
  onVerified: () => void;
  verifyUrl: string;
  siteKey: string;
}

declare global {
  interface Window {
    hcaptcha?: {
      render: (
        container: string | HTMLElement,
        config: {
          sitekey: string;
          callback: (token: string) => void;
          'error-callback'?: () => void;
          'expired-callback'?: () => void;
        },
      ) => string;
      reset: (widgetId: string) => void;
      execute: (widgetId?: string) => void;
    };
  }
}

export default function CaptchaModal({ isOpen, onClose, onVerified, verifyUrl, siteKey }: CaptchaModalProps) {
  const t = useTranslations('auth');
  const locale = useLocale();
  const text = useCallback((value: string) => selectLocalizedText(value, locale), [locale]);
  const [hcaptchaLoaded, setHcaptchaLoaded] = useState(false);
  const [widgetId, setWidgetId] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isOpen) return;

    // Load hCaptcha script
    if (!document.querySelector('script[src*="hcaptcha.com"]')) {
      const script = document.createElement('script');
      script.src = 'https://js.hcaptcha.com/1/api.js';
      script.async = true;
      script.defer = true;
      script.onload = () => setHcaptchaLoaded(true);
      script.onerror = () => setError(text('Failed to load hCaptcha'));
      document.head.appendChild(script);
    } else {
      setHcaptchaLoaded(true);
    }
  }, [isOpen, text]);

  useEffect(() => {
    if (!isOpen || !hcaptchaLoaded || !window.hcaptcha || widgetId) return;

    // Render hCaptcha widget
    const container = document.getElementById('hcaptcha-container');
    if (container) {
      try {
        const id = window.hcaptcha.render(container, {
          sitekey: siteKey,
          callback: handleCaptchaSuccess,
          'error-callback': () => {
            setError(text('hCaptcha error occurred / hCaptcha发生错误'));
          },
          'expired-callback': () => {
            setError(text('hCaptcha expired, please try again / hCaptcha已过期，请重试'));
          },
        });
        setWidgetId(id);
      } catch (err) {
        console.error('Failed to render hCaptcha:', err);
        setError(text('Failed to render hCaptcha / 无法加载hCaptcha'));
      }
    }
  }, [isOpen, hcaptchaLoaded, widgetId, siteKey, text]);

  const handleCaptchaSuccess = async (token: string) => {
    setVerifying(true);
    setError('');

    try {
      const response = await fetch(verifyUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ captcha_token: token }),
      });

      const data = await response.json();

      if (response.ok && data.verified) {
        onVerified();
        onClose();
      } else {
        setError(data.message || text('Verification failed / 验证失败'));
        // Reset hCaptcha widget
        if (widgetId && window.hcaptcha) {
          window.hcaptcha.reset(widgetId);
        }
      }
    } catch (err) {
      console.error('CAPTCHA verification error:', err);
      setError(text('Network error / 网络错误'));
      if (widgetId && window.hcaptcha) {
        window.hcaptcha.reset(widgetId);
      }
    } finally {
      setVerifying(false);
    }
  };

  const handleClose = () => {
    if (!verifying) {
      onClose();
    }
  };

  if (!isOpen) return null;

  return localizeReactNode(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="relative w-full max-w-md mx-4 bg-background rounded-lg shadow-2xl border border-border">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold">
              {t('captcha.title', { default: 'Security Verification / 安全验证' })}
            </h2>
          </div>
          <button
            onClick={handleClose}
            disabled={verifying}
            className="p-1 rounded-full hover:bg-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          <p className="text-sm text-muted-foreground">
            {t('captcha.description', {
              default: 'Please complete the security challenge below to continue. / 请完成下方的安全验证以继续。',
            })}
          </p>

          {error && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20">
              <AlertCircle className="w-4 h-4 text-destructive flex-shrink-0 mt-0.5" />
              <p className="text-sm text-destructive">{error}</p>
            </div>
          )}

          {/* hCaptcha Container */}
          <div className="flex justify-center py-4">
            {!hcaptchaLoaded ? (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="w-5 h-5 animate-spin" />
                <span className="text-sm">
                  {t('captcha.loading', { default: 'Loading CAPTCHA... / 加载验证中...' })}
                </span>
              </div>
            ) : (
              <div id="hcaptcha-container" />
            )}
          </div>

          {verifying && (
            <div className="flex items-center justify-center gap-2 text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">{t('captcha.verifying', { default: 'Verifying... / 验证中...' })}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-border bg-muted/30">
          <p className="text-xs text-center text-muted-foreground">
            {t('captcha.footer', {
              default: 'This verification helps protect your account. / 此验证有助于保护您的账户安全。',
            })}
          </p>
        </div>
      </div>
    </div>,
    locale,
  );
}
