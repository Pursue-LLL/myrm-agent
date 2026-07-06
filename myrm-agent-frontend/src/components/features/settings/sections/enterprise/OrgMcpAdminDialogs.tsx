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
import { OrgMcpServerFormFields } from './OrgMcpServerFormFields';

interface OrgMcpCreateDialogProps {
  open: boolean;
  saving: boolean;
  name: string;
  type: 'sse' | 'streamable_http';
  url: string;
  description: string;
  authHeader: string;
  onOpenChange: (open: boolean) => void;
  onNameChange: (value: string) => void;
  onTypeChange: (value: 'sse' | 'streamable_http') => void;
  onUrlChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onAuthHeaderChange: (value: string) => void;
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
  onOpenChange,
  onNameChange,
  onTypeChange,
  onUrlChange,
  onDescriptionChange,
  onAuthHeaderChange,
  onConfirm,
  t,
}: OrgMcpCreateDialogProps) {
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
          onNameChange={onNameChange}
          onTypeChange={onTypeChange}
          onUrlChange={onUrlChange}
          onDescriptionChange={onDescriptionChange}
          onAuthHeaderChange={onAuthHeaderChange}
          t={t}
          namePlaceholder="company-crm"
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('cancel')}
          </Button>
          <Button onClick={onConfirm} disabled={saving || !name.trim() || !url.trim()}>
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
  type: 'sse' | 'streamable_http';
  url: string;
  description: string;
  authHeader: string;
  onClose: () => void;
  onNameChange: (value: string) => void;
  onTypeChange: (value: 'sse' | 'streamable_http') => void;
  onUrlChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onAuthHeaderChange: (value: string) => void;
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
  onClose,
  onNameChange,
  onTypeChange,
  onUrlChange,
  onDescriptionChange,
  onAuthHeaderChange,
  onConfirm,
  t,
}: OrgMcpEditDialogProps) {
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
          headersConfigured={editTarget?.headers_configured}
          onNameChange={onNameChange}
          onTypeChange={onTypeChange}
          onUrlChange={onUrlChange}
          onDescriptionChange={onDescriptionChange}
          onAuthHeaderChange={onAuthHeaderChange}
          t={t}
        />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t('cancel')}
          </Button>
          <Button onClick={onConfirm} disabled={saving || !name.trim() || !url.trim()}>
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
