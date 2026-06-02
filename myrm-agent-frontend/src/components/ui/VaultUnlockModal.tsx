'use client';

import React, { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { apiRequest } from '@/lib/api';
import { toast } from 'sonner';

export function VaultUnlockModal() {
  const t = useTranslations('vault');
  const [isOpen, setIsOpen] = useState(false);
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const handleVaultLocked = () => {
      setIsOpen(true);
    };
    window.addEventListener('vault-locked', handleVaultLocked);
    return () => window.removeEventListener('vault-locked', handleVaultLocked);
  }, []);

  const handleUnlock = async () => {
    if (!password) {
      toast.error(t('emptyPassword'));
      return;
    }

    setIsSubmitting(true);
    try {
      await apiRequest('/security/vault/unlock', {
        method: 'POST',
        body: JSON.stringify({ password }),
      });
      toast.success(t('unlocked'));
      setIsOpen(false);
      setPassword('');

      setTimeout(() => {
        window.location.reload();
      }, 1000);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : t('unlockFailed');
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (isOpen && !open) return;
        setIsOpen(open);
      }}
    >
      <DialogContent
        className="sm:max-w-[425px]"
        onPointerDownOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>{t('title')}</DialogTitle>
          <DialogDescription className="pt-2">{t('description')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <Input
            type="password"
            placeholder={t('placeholder')}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                handleUnlock();
              }
            }}
            disabled={isSubmitting}
            autoFocus
          />
        </div>
        <DialogFooter>
          <Button onClick={handleUnlock} disabled={isSubmitting}>
            {isSubmitting ? t('unlocking') : t('unlock')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
