'use client';

import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';

const ROLE_OPTIONS = ['member', 'admin'] as const;

interface AddMemberDialogProps {
  open: boolean;
  email: string;
  role: string;
  onOpenChange: (open: boolean) => void;
  onEmailChange: (value: string) => void;
  onRoleChange: (value: string) => void;
  onConfirm: () => void;
  t: (key: string) => string;
}

export function AddMemberDialog({
  open,
  email,
  role,
  onOpenChange,
  onEmailChange,
  onRoleChange,
  onConfirm,
  t,
}: AddMemberDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('addMember')}</DialogTitle>
          <DialogDescription>{t('addMemberDesc')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label>{t('userId')}</Label>
            <Input value={email} onChange={(e) => onEmailChange(e.target.value)} placeholder={t('userIdPlaceholder')} />
          </div>
          <div className="space-y-2">
            <Label>{t('role')}</Label>
            <Select value={role} onValueChange={onRoleChange}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLE_OPTIONS.map((r) => (
                  <SelectItem key={r} value={r}>
                    {t(`role${r[0].toUpperCase()}${r.slice(1)}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('cancel')}
          </Button>
          <Button onClick={onConfirm}>{t('confirm')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface UnlinkOauthDialogProps {
  open: boolean;
  memberLabel: string;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  t: (key: string) => string;
}

export function UnlinkOauthDialog({ open, memberLabel, onOpenChange, onConfirm, t }: UnlinkOauthDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('unlinkOauth')}</DialogTitle>
          <DialogDescription>
            {t('unlinkOauthDesc')} <code className="text-xs bg-muted px-1 py-0.5 rounded">{memberLabel}</code>
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('cancel')}
          </Button>
          <Button variant="destructive" onClick={onConfirm}>
            {t('unlinkOauthConfirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface RemoveMemberDialogProps {
  open: boolean;
  memberLabel: string;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  t: (key: string) => string;
}

export function RemoveMemberDialog({ open, memberLabel, onOpenChange, onConfirm, t }: RemoveMemberDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('removeMember')}</DialogTitle>
          <DialogDescription>
            {t('removeMemberDesc')} <code className="text-xs bg-muted px-1 py-0.5 rounded">{memberLabel}</code>
          </DialogDescription>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">{t('removeMemberRevokeNote')}</p>
        <p className="text-xs text-muted-foreground">{t('removeMemberIdpNote')}</p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('cancel')}
          </Button>
          <Button variant="destructive" onClick={onConfirm}>
            {t('confirmRemove')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
