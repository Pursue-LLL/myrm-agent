'use client';

import { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { LogIn, Lock, Eye, EyeOff, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/primitives/button';

export interface LocalLoginFormProps {
  username: string;
  password: string;
  loading: boolean;
  error: string;
  failedAttempts: number;
  onPasswordChange: (value: string) => void;
  onSubmit: (event: React.FormEvent) => void;
}

const LocalLoginForm = memo(
  ({
    username: _username,
    password,
    loading,
    error,
    failedAttempts,
    onPasswordChange,
    onSubmit,
  }: LocalLoginFormProps) => {
    const t = useTranslations('auth');
    const [showPassword, setShowPassword] = useState(false);

    return (
      <div className="w-full h-full flex flex-col justify-center max-w-sm mx-auto animate-in fade-in zoom-in duration-500">
        <div className="text-center mb-10 space-y-5">
          <div className="mx-auto w-20 h-20 bg-gradient-to-tr from-primary/20 to-primary/5 rounded-3xl flex items-center justify-center shadow-lg shadow-primary/10 ring-1 ring-primary/20 backdrop-blur-xl relative">
            <div className="absolute inset-0 bg-primary/10 rounded-3xl blur-md" />
            <ShieldCheck className="w-10 h-10 text-primary relative z-10 drop-shadow-md" />
          </div>
          <div className="space-y-3">
            <h1 className="text-3xl font-bold tracking-tight text-foreground/90 font-sans">
              {t('login.title')}
            </h1>
            <p className="text-sm text-muted-foreground/80 leading-relaxed px-4 font-medium">
              {t('login.descriptionLocal')}
            </p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="space-y-6">
          {error && (
            <div className="p-4 rounded-2xl bg-red-500/10 border border-red-500/20 shadow-sm animate-in fade-in slide-in-from-top-4">
              <p className="text-sm text-red-500 font-semibold flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse shadow-[0_0_8px_rgba(239,68,68,0.8)]" />
                {error}
              </p>
              {failedAttempts >= 3 && (
                <p className="text-xs text-red-500/80 mt-2 ml-3.5">
                  {t('login.tooManyAttempts')}
                </p>
              )}
            </div>
          )}

          <div className="space-y-5">
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase tracking-[0.15em] text-muted-foreground/70 pl-1">
                {t('login.labelPassword')}
              </label>
              <div className="relative group">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none transition-transform group-focus-within:scale-110">
                  <Lock className="w-5 h-5 text-muted-foreground/60 group-focus-within:text-primary transition-colors" />
                </div>
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => onPasswordChange(e.target.value)}
                  className="w-full pl-12 pr-12 py-4 bg-background/50 border border-border/80 hover:border-muted-foreground/40 focus:border-primary/80 focus:bg-background rounded-2xl text-base text-foreground font-medium transition-all shadow-sm focus:shadow-[0_0_0_4px_rgba(var(--primary),0.1)] focus:outline-none"
                  placeholder={t('login.placeholderPassword')}
                  disabled={loading}
                  autoComplete="current-password"
                  autoFocus
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-4 flex items-center text-muted-foreground/60 hover:text-foreground focus:outline-none transition-colors"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                </button>
              </div>
            </div>
          </div>

          <Button
            type="submit"
            size="lg"
            className="w-full rounded-2xl text-base font-bold shadow-lg shadow-primary/25 hover:shadow-primary/40 hover:-translate-y-0.5 transition-all active:translate-y-0 active:scale-[0.98] mt-4 h-14 bg-gradient-to-r from-primary to-primary/90 hover:from-primary hover:to-primary"
            disabled={loading || !password}
          >
            {loading ? (
              <span className="flex items-center gap-3">
                <span className="w-5 h-5 rounded-full border-2 border-primary-foreground border-r-transparent animate-spin" />
                {t('login.buttonLoggingIn')}
              </span>
            ) : (
              <span className="flex items-center gap-3">
                {t('login.buttonLogin')}
                <LogIn className="w-5 h-5 opacity-90" />
              </span>
            )}
          </Button>
        </form>

        <div className="mt-10 pt-6 border-t border-border/40 text-center">
          <p className="text-[11px] text-muted-foreground/50 font-medium tracking-wide uppercase">
            {t('login.footerInfo')}
          </p>
        </div>
      </div>
    );
  },
);

LocalLoginForm.displayName = 'LocalLoginForm';

export default LocalLoginForm;