'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/shared/useToast';
import {
  createVaultCredential,
  deleteCredential,
  deleteVaultCredential,
  listCredentials,
  listVaultCredentials,
  updateVaultCredential,
  type CredentialFile,
  type VaultCredential,
} from '@/services/credentials';
import { getCredentialsErrorMessage } from './credentialsError';

export function useCredentialsStorage() {
  const t = useTranslations('settings.credentials');

  const [credentials, setCredentials] = useState<CredentialFile[]>([]);
  const [vaultCredentials, setVaultCredentials] = useState<VaultCredential[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isVaultLoading, setIsVaultLoading] = useState(true);

  const [vaultModalOpen, setVaultModalOpen] = useState(false);
  const [editingVaultCred, setEditingVaultCred] = useState<VaultCredential | null>(null);
  const [vaultLabel, setVaultLabel] = useState('');
  const [vaultPassword, setVaultPassword] = useState('');
  const [vaultTotp, setVaultTotp] = useState('');
  const [vaultDesc, setVaultDesc] = useState('');
  const [deleteVaultTarget, setDeleteVaultTarget] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const loadCredentials = useCallback(async () => {
    try {
      setIsLoading(true);
      const files = await listCredentials();
      setCredentials(files);
    } catch (error) {
      console.error('Failed to load credentials:', error);
      toast({
        title: t('loadError'),
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  const loadVaultCredentials = useCallback(async () => {
    try {
      setIsVaultLoading(true);
      const creds = await listVaultCredentials();
      setVaultCredentials(creds);
    } catch (error) {
      console.error('Failed to load vault credentials:', error);
    } finally {
      setIsVaultLoading(false);
    }
  }, []);

  const openVaultCreateModal = useCallback(() => {
    setEditingVaultCred(null);
    setVaultLabel('');
    setVaultPassword('');
    setVaultTotp('');
    setVaultDesc('');
    setVaultModalOpen(true);
  }, []);

  const openVaultEditModal = useCallback((cred: VaultCredential) => {
    setEditingVaultCred(cred);
    setVaultLabel(cred.label);
    setVaultPassword('');
    setVaultTotp('');
    setVaultDesc(cred.description || '');
    setVaultModalOpen(true);
  }, []);

  const handleSaveVaultCredential = useCallback(async () => {
    if (!vaultLabel.trim()) {
      toast({ title: t('vaultLabelRequired'), variant: 'destructive' });
      return;
    }
    if (!vaultPassword.trim() && !vaultTotp.trim()) {
      toast({ title: t('vaultSecretRequired'), variant: 'destructive' });
      return;
    }

    try {
      if (editingVaultCred) {
        await updateVaultCredential(editingVaultCred.label, {
          password: vaultPassword || undefined,
          totp_seed: vaultTotp || undefined,
          description: vaultDesc || undefined,
        });
        toast({ title: t('vaultUpdated') });
      } else {
        await createVaultCredential({
          label: vaultLabel.trim(),
          password: vaultPassword || undefined,
          totp_seed: vaultTotp || undefined,
          description: vaultDesc || undefined,
        });
        toast({ title: t('vaultCreated') });
      }
      setVaultModalOpen(false);
      loadVaultCredentials();
    } catch (error) {
      toast({ title: getCredentialsErrorMessage(error, t('vaultSaveFailed')), variant: 'destructive' });
    }
  }, [editingVaultCred, loadVaultCredentials, t, vaultDesc, vaultLabel, vaultPassword, vaultTotp]);

  const handleDeleteVaultConfirm = useCallback(async () => {
    if (!deleteVaultTarget) {
      return;
    }
    try {
      await deleteVaultCredential(deleteVaultTarget);
      toast({ title: t('vaultDeleted') });
      loadVaultCredentials();
    } catch (error) {
      toast({ title: getCredentialsErrorMessage(error, t('vaultDeleteFailed')), variant: 'destructive' });
    } finally {
      setDeleteVaultTarget(null);
    }
  }, [deleteVaultTarget, loadVaultCredentials, t]);

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) {
      return;
    }

    try {
      await deleteCredential(deleteTarget);
      toast({
        title: t('deleteSuccess'),
      });
      await loadCredentials();
    } catch (error) {
      console.error('Failed to delete credential:', error);
      toast({
        title: t('deleteError'),
        variant: 'destructive',
      });
      throw error;
    } finally {
      setDeleteTarget(null);
    }
  }, [deleteTarget, loadCredentials, t]);

  return {
    credentials,
    deleteTarget,
    deleteVaultTarget,
    editingVaultCred,
    handleDeleteConfirm,
    handleDeleteVaultConfirm,
    handleSaveVaultCredential,
    isLoading,
    isVaultLoading,
    loadCredentials,
    loadVaultCredentials,
    openVaultCreateModal,
    openVaultEditModal,
    setDeleteTarget,
    setDeleteVaultTarget,
    setVaultDesc,
    setVaultLabel,
    setVaultModalOpen,
    setVaultPassword,
    setVaultTotp,
    vaultCredentials,
    vaultDesc,
    vaultLabel,
    vaultModalOpen,
    vaultPassword,
    vaultTotp,
  };
}
