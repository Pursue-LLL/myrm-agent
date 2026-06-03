'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { Lock, Eye, EyeOff, Shield, CheckCircle2, XCircle, User } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils/classnameUtils';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { getWebuiUrl } from '@/lib/api';

interface PasswordRequirement {
  label: string;
  regex: RegExp;
  met: boolean;
}

export default function SetupPasswordPage() {
  const t = useTranslations('auth');
  const router = useRouter();
  const searchParams = useSearchParams();

  const [adminUsername, setAdminUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [tauriToken, setTauriToken] = useState<string | null>(null);

  const urlToken = searchParams.get('token');
  const tempToken = urlToken || tauriToken;

  // Password requirements
  const requirements: PasswordRequirement[] = [
    {
      label: t('setup.requirementMinLength'),
      regex: /.{8,}/,
      met: password.length >= 8,
    },
    {
      label: t('setup.requirementUppercase'),
      regex: /[A-Z]/,
      met: /[A-Z]/.test(password),
    },
    {
      label: t('setup.requirementLowercase'),
      regex: /[a-z]/,
      met: /[a-z]/.test(password),
    },
    {
      label: t('setup.requirementNumber'),
      regex: /[0-9]/,
      met: /[0-9]/.test(password),
    },
    {
      label: t('setup.requirementSpecial'),
      regex: /[!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?]/,
      met: /[!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?]/.test(password),
    },
  ];

  const allRequirementsMet = requirements.every((req) => req.met);
  const passwordsMatch = password === confirmPassword && confirmPassword.length > 0;

  // Fallback: if URL has no token and we're in Tauri, try IPC
  useEffect(() => {
    if (urlToken || !isTauriRuntime()) {
      if (!urlToken) setError(t('setup.errorNoToken'));
      return;
    }

    (async () => {
      try {
        const { invoke } = await import('@tauri-apps/api/core');
        const token: string | null = await invoke('get_setup_token');
        if (token) {
          setTauriToken(token);
          setError('');
        } else {
          setError(t('setup.errorNoToken'));
        }
      } catch {
        setError(t('setup.errorNoToken'));
      }
    })();
  }, [urlToken, t]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!tempToken) {
      setError(t('setup.errorNoToken'));
      return;
    }

    if (!allRequirementsMet) {
      setError(t('setup.errorRequirementsNotMet'));
      return;
    }

    if (!passwordsMatch) {
      setError(t('setup.errorPasswordMismatch'));
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(getWebuiUrl('/auth/setup'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          temp_token: tempToken,
          username: adminUsername,
          password,
        }),
      });

      if (response.ok) {
        // Password set successfully, redirect to home
        router.push('/');
      } else {
        const data = await response.json();
        setError(data.detail || t('setup.errorGeneric'));
      }
    } catch (err) {
      console.error('Setup error:', err);
      setError(t('setup.errorNetwork'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 via-background to-primary-50 dark:from-gray-900 dark:via-background dark:to-gray-900 p-4">
      <Card className="w-full max-w-md shadow-2xl">
        <CardHeader className="space-y-2 text-center">
          <div className="mx-auto w-12 h-12 bg-primary-100 dark:bg-primary-900/30 rounded-full flex items-center justify-center mb-2">
            <Shield className="w-6 h-6 text-primary-600 dark:text-primary-400" />
          </div>
          <CardTitle className="text-2xl font-bold">{t('setup.title')}</CardTitle>
          <CardDescription>{t('setup.description')}</CardDescription>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">{t('setup.labelUsername')}</label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  type="text"
                  value={adminUsername}
                  onChange={(e) => setAdminUsername(e.target.value)}
                  className="pl-10"
                  placeholder={t('setup.placeholderUsername')}
                  disabled={loading || !tempToken}
                  autoComplete="username"
                  autoFocus
                  minLength={2}
                  maxLength={50}
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">{t('setup.labelPassword')}</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pl-10 pr-10"
                  placeholder={t('setup.placeholderPassword')}
                  disabled={loading || !tempToken}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Password Requirements */}
            {password.length > 0 && (
              <div className="space-y-2 rounded-lg bg-muted/50 p-3">
                <p className="text-sm font-medium text-foreground">{t('setup.requirementsTitle')}</p>
                <div className="space-y-1">
                  {requirements.map((req, index) => (
                    <div key={index} className="flex items-center gap-2 text-sm">
                      {req.met ? (
                        <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />
                      ) : (
                        <XCircle className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                      )}
                      <span
                        className={cn(
                          'text-sm',
                          req.met ? 'text-green-600 dark:text-green-400' : 'text-muted-foreground',
                        )}
                      >
                        {req.label}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Confirm Password Input */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">{t('setup.labelConfirmPassword')}</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  type={showConfirmPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="pl-10 pr-10"
                  placeholder={t('setup.placeholderConfirmPassword')}
                  disabled={loading || !tempToken}
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  tabIndex={-1}
                >
                  {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {confirmPassword.length > 0 && (
                <div className="flex items-center gap-2 text-sm">
                  {passwordsMatch ? (
                    <>
                      <CheckCircle2 className="w-4 h-4 text-green-500" />
                      <span className="text-green-600 dark:text-green-400">{t('setup.passwordsMatch')}</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="w-4 h-4 text-destructive" />
                      <span className="text-destructive">{t('setup.passwordsNoMatch')}</span>
                    </>
                  )}
                </div>
              )}
            </div>

            {/* Error Message */}
            {error && (
              <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-3">
                <p className="text-sm text-destructive">{error}</p>
              </div>
            )}

            {/* Submit Button */}
            <Button
              type="submit"
              className="w-full"
              disabled={loading || !tempToken || !adminUsername.trim() || !allRequirementsMet || !passwordsMatch}
            >
              {loading ? t('setup.buttonSubmitting') : t('setup.buttonSubmit')}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
