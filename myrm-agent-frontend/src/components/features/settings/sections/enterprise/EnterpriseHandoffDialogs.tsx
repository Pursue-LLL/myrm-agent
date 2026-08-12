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
import { Label } from '@/components/primitives/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives/select';
import type { OrgMember } from '@/services/enterprise-org';

function memberLabel(m: OrgMember): string {
  return m.email ?? m.user_id;
}

interface OffboardDialogProps {
  open: boolean;
  offboardableMembers: OrgMember[];
  offboardUserId: string;
  onOpenChange: (open: boolean) => void;
  onOffboardUserIdChange: (value: string) => void;
  onConfirm: () => void;
  t: (key: string) => string;
}

export function OffboardDialog({
  open,
  offboardableMembers,
  offboardUserId,
  onOpenChange,
  onOffboardUserIdChange,
  onConfirm,
  t,
}: OffboardDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('offboardUser')}</DialogTitle>
          <DialogDescription>{t('offboardUserDesc')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label>{t('memberToOffboard')}</Label>
            <Select value={offboardUserId} onValueChange={onOffboardUserIdChange}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t('selectMember')} />
              </SelectTrigger>
              <SelectContent>
                {offboardableMembers.map((m) => (
                  <SelectItem key={m.user_id} value={m.user_id}>
                    {memberLabel(m)}
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
          <Button variant="destructive" onClick={onConfirm} disabled={!offboardUserId}>
            {t('confirmOffboard')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface TransferDialogProps {
  open: boolean;
  sourceCandidates: OrgMember[];
  targetCandidates: OrgMember[];
  transferSourceId: string;
  transferTargetId: string;
  onOpenChange: (open: boolean) => void;
  onTransferSourceIdChange: (value: string) => void;
  onTransferTargetIdChange: (value: string) => void;
  onConfirm: () => void;
  t: (key: string) => string;
}

export function TransferDialog({
  open,
  sourceCandidates,
  targetCandidates,
  transferSourceId,
  transferTargetId,
  onOpenChange,
  onTransferSourceIdChange,
  onTransferTargetIdChange,
  onConfirm,
  t,
}: TransferDialogProps) {
  const canConfirm =
    transferSourceId.trim().length > 0 &&
    transferTargetId.trim().length > 0 &&
    transferSourceId !== transferTargetId;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('transferVolume')}</DialogTitle>
          <DialogDescription>{t('transferVolumeDesc')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label>{t('sourceMember')}</Label>
            <Select value={transferSourceId} onValueChange={onTransferSourceIdChange}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t('selectMember')} />
              </SelectTrigger>
              <SelectContent>
                {sourceCandidates.length === 0 && (
                  <p className="px-2 py-1.5 text-sm text-muted-foreground">
                    {t('noTransferableSources')}
                  </p>
                )}
                {sourceCandidates.map((m) => (
                  <SelectItem key={m.user_id} value={m.user_id}>
                    {memberLabel(m)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>{t('targetMember')}</Label>
            <Select value={transferTargetId} onValueChange={onTransferTargetIdChange}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t('selectMember')} />
              </SelectTrigger>
              <SelectContent>
                {targetCandidates.map((m) => (
                  <SelectItem key={m.user_id} value={m.user_id}>
                    {memberLabel(m)}
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
          <Button onClick={onConfirm} disabled={!canConfirm}>
            {t('confirmTransfer')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
