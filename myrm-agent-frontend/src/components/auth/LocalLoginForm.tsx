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
        <div className="text-center mb-8 space-y-4">
          <div className="mx-auto w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center shadow-inner shadow-primary/20 ring-1 ring-primary/20 backdrop-blur-sm">
            <ShieldCheck className="w-8 h-8 text-primary" />
          </div>
          <div className="space-y-2">
            <h1 className="text-3xl font-black tracking-tight text-foreground">
              {t('login.title')}
            </h1>
            <p className="text-sm text-muted-foreground leading-relaxed px-4">
              {t('login.descriptionLocal')}
            </p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="space-y-5">
          {error && (
            <div className="p-4 rounded-xl bg-destructive/10 border border-destructive/20 shadow-sm animate-in slide-in-from-top-2">
              <p className="text-sm text-destructive font-semibold flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-destructive animate-pulse" />
                {error}
              </p>
              {failedAttempts >= 3 && (
                <p className="text-xs text-destructive/80 mt-1.5 ml-3.5">
                  {t('login.tooManyAttempts')}
                </p>
              )}
            </div>
          )}

          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground pl-1">
                {t('login.labelPassword')}
              </label>
              <div className="relative group">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                  <Lock className="w-5 h-5 text-muted-foreground group-focus-within:text-primary transition-colors" />
                </div>
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => onPasswordChange(e.target.value)}
                  className="w-full pl-11 pr-11 py-3.5 bg-background border-2 border-muted hover:border-muted-foreground/30 focus:border-primary rounded-xl text-base text-foreground font-medium transition-all shadow-sm focus:shadow-md focus:outline-none"
                  placeholder={t('login.placeholderPassword')}
                  disabled={loading}
                  autoComplete="current-password"
                  autoFocus
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-muted-foreground hover:text-foreground focus:outline-none transition-colors"
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
            className="w-full rounded-xl text-base font-bold shadow-lg hover:shadow-xl transition-all active:scale-[0.98] mt-2 h-12"
            disabled={loading || !password}
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <span className="w-4 h-4 rounded-full border-2 border-primary-foreground border-r-transparent animate-spin" />
                {t('login.buttonLoggingIn')}
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <LogIn className="w-5 h-5" />
                {t('login.buttonLogin')}
              </span>
            )}
          </Button>
        </form>

        <div className="mt-8 text-center">
          <p className="text-xs text-muted-foreground/60 font-medium tracking-wide">
            {t('login.footerInfo')}
          </p>
        </div>
      </div>
    );
  },
);

LocalLoginForm.displayName = 'LocalLoginForm';

export default LocalLoginForm;