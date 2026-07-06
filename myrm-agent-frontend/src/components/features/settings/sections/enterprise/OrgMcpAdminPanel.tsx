'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Pencil, Plug, Plus, Trash2 } from 'lucide-react';
import SettingsSection from '../SettingsSection';
import { Button } from '@/components/primitives/button';
import { Label } from '@/components/primitives/label';
import { Badge } from '@/components/primitives/badge';
import { Switch } from '@/components/primitives/switch';
import {
  type OrgMCPServer,
  type UpdateOrgMCPServerInput,
  createOrgMcpServer,
  deleteOrgMcpServer,
  listOrgMcpServers,
  updateOrgMcpServer,
} from '@/services/enterprise-org';
import {
  OrgMcpCreateDialog,
  OrgMcpDeleteDialog,
  OrgMcpEditDialog,
} from './OrgMcpAdminDialogs';
import { showOrgMcpDeliveryToast } from './orgMcpAdminUtils';

interface OrgMcpAdminPanelProps {
  orgId: string;
}

const OrgMcpAdminPanel = memo(({ orgId }: OrgMcpAdminPanelProps) => {
  const t = useTranslations('settings.enterprise');
  const [servers, setServers] = useState<OrgMCPServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editTarget, setEditTarget] = useState<OrgMCPServer | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<OrgMCPServer | null>(null);
  const [saving, setSaving] = useState(false);

  const [name, setName] = useState('');
  const [type, setType] = useState<'sse' | 'streamable_http'>('sse');
  const [url, setUrl] = useState('');
  const [description, setDescription] = useState('');
  const [authHeader, setAuthHeader] = useState('');

  const [editName, setEditName] = useState('');
  const [editType, setEditType] = useState<'sse' | 'streamable_http'>('sse');
  const [editUrl, setEditUrl] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editAuthHeader, setEditAuthHeader] = useState('');

  const loadServers = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listOrgMcpServers(orgId);
      setServers(data);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('mcpLoadFailed'));
    } finally {
      setLoading(false);
    }
  }, [orgId, t]);

  useEffect(() => {
    void loadServers();
  }, [loadServers]);

  const handleCreate = useCallback(async () => {
    if (!name.trim() || !url.trim()) return;
    try {
      setSaving(true);
      const headers = authHeader.trim() ? { Authorization: authHeader.trim() } : undefined;
      const result = await createOrgMcpServer(orgId, {
        name: name.trim(),
        type,
        url: url.trim(),
        description: description.trim(),
        headers,
      });
      showOrgMcpDeliveryToast(t, result.delivery);
      setShowCreate(false);
      setName('');
      setUrl('');
      setDescription('');
      setAuthHeader('');
      await loadServers();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('mcpCreateFailed'));
    } finally {
      setSaving(false);
    }
  }, [orgId, name, type, url, description, authHeader, t, loadServers]);

  const openEditDialog = useCallback((server: OrgMCPServer) => {
    setEditTarget(server);
    setEditName(server.name);
    setEditType(server.type as 'sse' | 'streamable_http');
    setEditUrl(server.url ?? '');
    setEditDescription(server.description ?? '');
    setEditAuthHeader('');
  }, []);

  const handleEdit = useCallback(async () => {
    if (!editTarget || !editName.trim() || !editUrl.trim()) return;
    try {
      setSaving(true);
      const payload: UpdateOrgMCPServerInput = {
        name: editName.trim(),
        type: editType,
        url: editUrl.trim(),
        description: editDescription.trim(),
      };
      if (editAuthHeader.trim()) {
        payload.headers = { Authorization: editAuthHeader.trim() };
      }
      const result = await updateOrgMcpServer(orgId, editTarget.id, payload);
      showOrgMcpDeliveryToast(t, result.delivery);
      setEditTarget(null);
      await loadServers();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('mcpUpdateFailed'));
    } finally {
      setSaving(false);
    }
  }, [orgId, editTarget, editName, editType, editUrl, editDescription, editAuthHeader, t, loadServers]);

  const handleToggle = useCallback(
    async (server: OrgMCPServer) => {
      try {
        const result = await updateOrgMcpServer(orgId, server.id, {
          enabled: !server.enabled,
        });
        showOrgMcpDeliveryToast(t, result.delivery);
        await loadServers();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : t('mcpUpdateFailed'));
      }
    },
    [orgId, t, loadServers],
  );

  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return;
    try {
      const result = await deleteOrgMcpServer(orgId, deleteTarget.id);
      showOrgMcpDeliveryToast(t, result.delivery);
      setDeleteTarget(null);
      await loadServers();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('mcpDeleteFailed'));
    }
  }, [orgId, deleteTarget, t, loadServers]);

  return (
    <SettingsSection
      title={
        <span className="flex items-center gap-2">
          <Plug className="h-5 w-5" />
          {t('mcpTitle')}
        </span>
      }
      description={t('mcpDescription')}
      action={
        <Button size="sm" variant="outline" onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4 mr-1" />
          {t('mcpAdd')}
        </Button>
      }
    >
      {loading ? (
        <div className="animate-pulse space-y-2">
          <div className="h-14 bg-muted rounded-lg" />
          <div className="h-14 bg-muted rounded-lg" />
        </div>
      ) : servers.length === 0 ? (
        <p className="text-sm text-muted-foreground py-4">{t('mcpEmpty')}</p>
      ) : (
        <div className="space-y-2">
          {servers.map((server) => (
            <div
              key={server.id}
              className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 py-3 px-4 rounded-lg border border-border/40 bg-background/50"
            >
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-sm">{server.name}</span>
                  <Badge variant="secondary" className="text-xs uppercase">
                    {server.type.replace('_', ' ')}
                  </Badge>
                  {!server.enabled && (
                    <Badge variant="outline" className="text-xs">
                      {t('mcpDisabled')}
                    </Badge>
                  )}
                  {server.headers_configured && (
                    <Badge variant="outline" className="text-xs">
                      {t('mcpHeadersConfigured')}
                    </Badge>
                  )}
                </div>
                {server.url && <p className="text-xs text-muted-foreground truncate">{server.url}</p>}
                {server.description && <p className="text-xs text-muted-foreground">{server.description}</p>}
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <div className="flex items-center gap-2">
                  <Label htmlFor={`mcp-enabled-${server.id}`} className="text-xs text-muted-foreground">
                    {t('mcpEnabled')}
                  </Label>
                  <Switch
                    id={`mcp-enabled-${server.id}`}
                    checked={server.enabled}
                    onCheckedChange={() => void handleToggle(server)}
                  />
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => openEditDialog(server)}
                  aria-label={t('mcpEdit')}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-destructive hover:text-destructive"
                  onClick={() => setDeleteTarget(server)}
                  aria-label={t('mcpDeleteTitle')}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <OrgMcpCreateDialog
        open={showCreate}
        saving={saving}
        name={name}
        type={type}
        url={url}
        description={description}
        authHeader={authHeader}
        onOpenChange={setShowCreate}
        onNameChange={setName}
        onTypeChange={setType}
        onUrlChange={setUrl}
        onDescriptionChange={setDescription}
        onAuthHeaderChange={setAuthHeader}
        onConfirm={() => void handleCreate()}
        t={t}
      />

      <OrgMcpEditDialog
        editTarget={editTarget}
        saving={saving}
        name={editName}
        type={editType}
        url={editUrl}
        description={editDescription}
        authHeader={editAuthHeader}
        onClose={() => setEditTarget(null)}
        onNameChange={setEditName}
        onTypeChange={setEditType}
        onUrlChange={setEditUrl}
        onDescriptionChange={setEditDescription}
        onAuthHeaderChange={setEditAuthHeader}
        onConfirm={() => void handleEdit()}
        t={t}
      />

      <OrgMcpDeleteDialog
        deleteTarget={deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => void handleDelete()}
        t={t}
      />
    </SettingsSection>
  );
});

OrgMcpAdminPanel.displayName = 'OrgMcpAdminPanel';

export default OrgMcpAdminPanel;
