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
import type { OrgMCPServer } from '@/services/enterprise-org';
import { type OrgMcpType, OrgMcpServerFormFields } from './OrgMcpServerFormFields';

interface OrgMcpCreateDialogProps {
  open: boolean;
  saving: boolean;
  name: string;
  type: OrgMcpType;
  url: string;
  description: string;
  authHeader: string;
  tunnelId: string;
  tunnels?: { id: string; name: string; status: string }[];
  onOpenChange: (open: boolean) => void;
  onNameChange: (value: string) => void;
  onTypeChange: (value: OrgMcpType) => void;
  onUrlChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onAuthHeaderChange: (value: string) => void;
  onTunnelIdChange: (value: string) => void;
  onConfirm: () => void;
  t: (key: string) => string;
}

export function OrgMcpCreateDialog({
  open,
  saving,
  name,
  type,
  url,
  description,
  authHeader,
  tunnelId,
  tunnels = [],
  onOpenChange,
  onNameChange,
  onTypeChange,
  onUrlChange,
  onDescriptionChange,
  onAuthHeaderChange,
  onTunnelIdChange,
  onConfirm,
  t,
}: OrgMcpCreateDialogProps) {
  const isTunnel = type === 'tunnel';
  const canConfirm = name.trim() && (isTunnel ? tunnelId : url.trim());

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('mcpAdd')}</DialogTitle>
          <DialogDescription>{t('mcpAddDesc')}</DialogDescription>
        </DialogHeader>
        <OrgMcpServerFormFields
          name={name}
          type={type}
          url={url}
          description={description}
          authHeader={authHeader}
          tunnelId={tunnelId}
          tunnels={tunnels}
          onNameChange={onNameChange}
          onTypeChange={onTypeChange}
          onUrlChange={onUrlChange}
          onDescriptionChange={onDescriptionChange}
          onAuthHeaderChange={onAuthHeaderChange}
          onTunnelIdChange={onTunnelIdChange}
          t={t}
          namePlaceholder="company-crm"
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('cancel')}
          </Button>
          <Button onClick={onConfirm} disabled={saving || !canConfirm}>
            {t('confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface OrgMcpEditDialogProps {
  editTarget: OrgMCPServer | null;
  saving: boolean;
  name: string;
  type: OrgMcpType;
  url: string;
  description: string;
  authHeader: string;
  tunnelId: string;
  tunnels?: { id: string; name: string; status: string }[];
  onClose: () => void;
  onNameChange: (value: string) => void;
  onTypeChange: (value: OrgMcpType) => void;
  onUrlChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onAuthHeaderChange: (value: string) => void;
  onTunnelIdChange: (value: string) => void;
  onConfirm: () => void;
  t: (key: string) => string;
}

export function OrgMcpEditDialog({
  editTarget,
  saving,
  name,
  type,
  url,
  description,
  authHeader,
  tunnelId,
  tunnels = [],
  onClose,
  onNameChange,
  onTypeChange,
  onUrlChange,
  onDescriptionChange,
  onAuthHeaderChange,
  onTunnelIdChange,
  onConfirm,
  t,
}: OrgMcpEditDialogProps) {
  const isTunnel = type === 'tunnel';
  const canConfirm = name.trim() && (isTunnel ? tunnelId : url.trim());

  return (
    <Dialog open={editTarget !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('mcpEdit')}</DialogTitle>
          <DialogDescription>{t('mcpEditDesc')}</DialogDescription>
        </DialogHeader>
        <OrgMcpServerFormFields
          name={name}
          type={type}
          url={url}
          description={description}
          authHeader={authHeader}
          tunnelId={tunnelId}
          tunnels={tunnels}
          headersConfigured={editTarget?.headers_configured}
          onNameChange={onNameChange}
          onTypeChange={onTypeChange}
          onUrlChange={onUrlChange}
          onDescriptionChange={onDescriptionChange}
          onAuthHeaderChange={onAuthHeaderChange}
          onTunnelIdChange={onTunnelIdChange}
          t={t}
        />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t('cancel')}
          </Button>
          <Button onClick={onConfirm} disabled={saving || !canConfirm}>
            {t('confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface OrgMcpDeleteDialogProps {
  deleteTarget: OrgMCPServer | null;
  onClose: () => void;
  onConfirm: () => void;
  t: (key: string, values?: Record<string, string | number>) => string;
}

export function OrgMcpDeleteDialog({ deleteTarget, onClose, onConfirm, t }: OrgMcpDeleteDialogProps) {
  return (
    <Dialog open={deleteTarget !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('mcpDeleteTitle')}</DialogTitle>
          <DialogDescription>{t('mcpDeleteDesc', { name: deleteTarget?.name ?? '' })}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t('cancel')}
          </Button>
          <Button variant="destructive" onClick={onConfirm}>
            {t('confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
