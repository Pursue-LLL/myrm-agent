'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Monitor, Lock, Unlock, Shield, Trash2, Key } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import { useTauri } from '@/hooks/useTauri';

interface LockedUseCardProps {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}

/**
 * Locked Use configuration card for Computer Use screen lock management.
 *
 * Layer 1 (Display Keep-Awake): Always active during CU sessions, zero config.
 * Layer 2 (Screen Unlock): Opt-in, requires password stored in macOS Keychain.
 */
const LockedUseCard = memo<LockedUseCardProps>(({ enabled, onToggle }) => {
  const t = useTranslations('settings.lockedUse');
  const { isTauri, invoke } = useTauri();
  const [hasPassword, setHasPassword] = useState(false);
  const [showPasswordInput, setShowPasswordInput] = useState(false);
  const [password, setPassword] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [platformSupport, setPlatformSupport] = useState<{
    detection: boolean;
    unlock: boolean;
    keychain: boolean;
    platform: string;
  } | null>(null);

  const checkPlatformSupport = useCallback(async () => {
    if (!isTauri || !invoke) return;
    try {
      const support = await invoke<{
        detection: boolean;
        unlock: boolean;
        keychain: boolean;
        platform: string;
      }>('screen_lock_platform_support');
      setPlatformSupport(support);

      const stored = await invoke<boolean>('screen_lock_has_password');
      setHasPassword(stored);
    } catch {
      // Not running in Tauri — expected for WebUI mode
    }
  }, [isTauri, invoke]);

  useEffect(() => {
    void checkPlatformSupport();
  }, [checkPlatformSupport]);

  const handleSavePassword = useCallback(async () => {
    if (!invoke || !password.trim()) return;
    setIsSaving(true);
    try {
      await invoke('screen_lock_store_password', { password });
      setHasPassword(true);
      setPassword('');
      setShowPasswordInput(false);
      toast.success(t('toastSaved'));
    } catch (err) {
      toast.error(t('toastSaveFailed', { error: String(err) }));
    } finally {
      setIsSaving(false);
    }
  }, [invoke, password, t]);

  const handleDeletePassword = useCallback(async () => {
    if (!invoke) return;
    try {
      await invoke('screen_lock_delete_password');
      setHasPassword(false);
      toast.success(t('toastDeleted'));
    } catch (err) {
      toast.error(t('toastDeleteFailed', { error: String(err) }));
    }
  }, [invoke, t]);

  if (!isTauri) return null;

  const supportsUnlock = platformSupport?.unlock ?? false;

  return (
    <section className="space-y-6">
      <div className="flex items-center gap-3 px-2">
        <Monitor className="w-5 h-5 text-muted-foreground" />
        <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">{t('title')}</h2>
      </div>

      <div className="rounded-2xl border border-border/40 bg-card/50 backdrop-blur-sm overflow-hidden divide-y divide-border/20">
        {/* Layer 1: Display Keep-Awake (always on, info only) */}
        <div className="p-5 flex items-center justify-between">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="p-2 rounded-lg bg-emerald-500/10">
              <Shield className="w-4 h-4 text-emerald-500" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground">{t('layer1Title')}</p>
              <p className="text-xs text-muted-foreground">{t('layer1Desc')}</p>
            </div>
          </div>
          <span className="text-xs font-medium text-emerald-500 bg-emerald-500/10 px-2.5 py-1 rounded-full">
            {t('layer1Badge')}
          </span>
        </div>

        {/* Layer 2: Screen Unlock (opt-in) */}
        <div className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 flex-1 min-w-0">
              <div className={cn('p-2 rounded-lg', enabled ? 'bg-indigo-500/10' : 'bg-muted/50')}>
                {enabled ? (
                  <Unlock className="w-4 h-4 text-indigo-500" />
                ) : (
                  <Lock className="w-4 h-4 text-muted-foreground" />
                )}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-foreground">{t('layer2Title')}</p>
                <p className="text-xs text-muted-foreground">
                  {supportsUnlock
                    ? t('layer2DescSupported')
                    : t('layer2DescUnsupported', { platform: platformSupport?.platform ?? 'unknown' })}
                </p>
              </div>
            </div>
            <button
              onClick={() => onToggle(!enabled)}
              disabled={!supportsUnlock}
              className={cn(
                'relative w-12 h-6 rounded-full transition-colors',
                !supportsUnlock && 'opacity-50 cursor-not-allowed',
                enabled ? 'bg-indigo-500' : 'bg-white/10',
              )}
            >
              <div
                className={cn(
                  'absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform',
                  enabled && 'translate-x-6',
                )}
              />
            </button>
          </div>

          {/* Password management (only when enabled and supported) */}
          {enabled && supportsUnlock && (
            <div className="pl-12 space-y-3">
              {hasPassword ? (
                <div className="flex items-center justify-between p-3 rounded-xl bg-muted/30 border border-border/20">
                  <div className="flex items-center gap-2">
                    <Key className="w-4 h-4 text-emerald-500" />
                    <span className="text-xs text-muted-foreground">{t('passwordSaved')}</span>
                  </div>
                  <button
                    onClick={handleDeletePassword}
                    className="p-1.5 rounded-lg hover:bg-destructive/10 transition-colors"
                    title={t('deletePassword')}
                  >
                    <Trash2 className="w-3.5 h-3.5 text-destructive/70" />
                  </button>
                </div>
              ) : showPasswordInput ? (
                <div className="space-y-2">
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') void handleSavePassword();
                    }}
                    placeholder={t('inputPlaceholder')}
                    className="w-full px-3 py-2 text-sm rounded-xl bg-muted/30 border border-border/30 focus:border-indigo-500 focus:outline-none"
                    autoFocus
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => void handleSavePassword()}
                      disabled={isSaving || !password.trim()}
                      className={cn(
                        'flex-1 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors',
                        password.trim()
                          ? 'bg-indigo-500 text-white hover:bg-indigo-600'
                          : 'bg-muted text-muted-foreground cursor-not-allowed',
                      )}
                    >
                      {isSaving ? t('saving') : t('savePassword')}
                    </button>
                    <button
                      onClick={() => {
                        setShowPasswordInput(false);
                        setPassword('');
                      }}
                      className="px-3 py-1.5 text-xs font-medium rounded-lg bg-muted/50 hover:bg-muted transition-colors"
                    >
                      {t('cancel')}
                    </button>
                  </div>
                  <p className="text-[10px] text-muted-foreground/60">{t('securityNote')}</p>
                </div>
              ) : (
                <button
                  onClick={() => setShowPasswordInput(true)}
                  className="flex items-center gap-2 px-3 py-2 text-xs font-medium rounded-xl bg-muted/30 border border-border/20 hover:bg-muted/50 transition-colors"
                >
                  <Key className="w-3.5 h-3.5" />
                  {t('setPassword')}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
});

LockedUseCard.displayName = 'LockedUseCard';

export default LockedUseCard;
