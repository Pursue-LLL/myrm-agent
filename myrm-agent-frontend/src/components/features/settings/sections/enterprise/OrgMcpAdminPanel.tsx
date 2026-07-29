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
  type Tunnel,
  type UpdateOrgMCPServerInput,
  createOrgMcpServer,
  deleteOrgMcpServer,
  listOrgMcpServers,
  listTunnels,
  updateOrgMcpServer,
} from '@/services/enterprise-org';
import type { OrgMcpType } from './OrgMcpServerFormFields';
import {
  OrgMcpCreateDialog,
  OrgMcpDeleteDialog,
  OrgMcpEditDialog,
} from './OrgMcpAdminDialogs';
import { showOrgMcpDeliveryToast } from './orgMcpAdminUtils';

interface OrgMcpAdminPanelProps {
  orgId: string;
}

function typeLabel(type: string): string {
  if (type === 'tunnel') return 'Tunnel';
  return type.replace('_', ' ').toUpperCase();
}

const OrgMcpAdminPanel = memo(({ orgId }: OrgMcpAdminPanelProps) => {
  const t = useTranslations('settings.enterprise');
  const [servers, setServers] = useState<OrgMCPServer[]>([]);
  const [tunnels, setTunnels] = useState<Tunnel[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editTarget, setEditTarget] = useState<OrgMCPServer | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<OrgMCPServer | null>(null);
  const [saving, setSaving] = useState(false);

  const [name, setName] = useState('');
  const [type, setType] = useState<OrgMcpType>('sse');
  const [url, setUrl] = useState('');
  const [description, setDescription] = useState('');
  const [authHeader, setAuthHeader] = useState('');
  const [tunnelId, setTunnelId] = useState('');

  const [editName, setEditName] = useState('');
  const [editType, setEditType] = useState<OrgMcpType>('sse');
  const [editUrl, setEditUrl] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editAuthHeader, setEditAuthHeader] = useState('');
  const [editTunnelId, setEditTunnelId] = useState('');

  const tunnelOptions = tunnels.map((tun) => ({
    id: tun.id,
    name: tun.name,
    status: tun.status,
  }));

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [serversData, tunnelsData] = await Promise.all([
        listOrgMcpServers(orgId),
        listTunnels(orgId).catch(() => [] as Tunnel[]),
      ]);
      setServers(serversData);
      setTunnels(tunnelsData);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('mcpLoadFailed'));
    } finally {
      setLoading(false);
    }
  }, [orgId, t]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleCreate = useCallback(async () => {
    if (!name.trim()) return;
    const isTunnel = type === 'tunnel';
    if (isTunnel && !tunnelId) return;
    if (!isTunnel && !url.trim()) return;

    try {
      setSaving(true);
      const headers = authHeader.trim() ? { Authorization: authHeader.trim() } : undefined;
      const result = await createOrgMcpServer(orgId, {
        name: name.trim(),
        type,
        url: isTunnel ? undefined : url.trim(),
        description: description.trim(),
        headers: isTunnel ? undefined : headers,
        tunnel_id: isTunnel ? tunnelId : undefined,
      });
      showOrgMcpDeliveryToast(t, result.delivery);
      setShowCreate(false);
      setName('');
      setUrl('');
      setDescription('');
      setAuthHeader('');
      setTunnelId('');
      await loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('mcpCreateFailed'));
    } finally {
      setSaving(false);
    }
  }, [orgId, name, type, url, description, authHeader, tunnelId, t, loadData]);

  const openEditDialog = useCallback((server: OrgMCPServer) => {
    setEditTarget(server);
    setEditName(server.name);
    setEditType(server.type as OrgMcpType);
    setEditUrl(server.url ?? '');
    setEditDescription(server.description ?? '');
    setEditAuthHeader('');
    setEditTunnelId(server.type === 'tunnel' ? (server.url ?? '') : '');
  }, []);

  const handleEdit = useCallback(async () => {
    if (!editTarget || !editName.trim()) return;
    const isTunnel = editType === 'tunnel';
    if (isTunnel && !editTunnelId) return;
    if (!isTunnel && !editUrl.trim()) return;

    try {
      setSaving(true);
      const payload: UpdateOrgMCPServerInput = {
        name: editName.trim(),
        type: editType,
        url: isTunnel ? undefined : editUrl.trim(),
        description: editDescription.trim(),
        tunnel_id: isTunnel ? editTunnelId : undefined,
      };
      if (editAuthHeader.trim()) {
        payload.headers = { Authorization: editAuthHeader.trim() };
      }
      const result = await updateOrgMcpServer(orgId, editTarget.id, payload);
      showOrgMcpDeliveryToast(t, result.delivery);
      setEditTarget(null);
      await loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('mcpUpdateFailed'));
    } finally {
      setSaving(false);
    }
  }, [orgId, editTarget, editName, editType, editUrl, editDescription, editAuthHeader, editTunnelId, t, loadData]);

  const handleToggle = useCallback(
    async (server: OrgMCPServer) => {
      try {
        const result = await updateOrgMcpServer(orgId, server.id, {
          enabled: !server.enabled,
        });
        showOrgMcpDeliveryToast(t, result.delivery);
        await loadData();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : t('mcpUpdateFailed'));
      }
    },
    [orgId, t, loadData],
  );

  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return;
    try {
      const result = await deleteOrgMcpServer(orgId, deleteTarget.id);
      showOrgMcpDeliveryToast(t, result.delivery);
      setDeleteTarget(null);
      await loadData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('mcpDeleteFailed'));
    }
  }, [orgId, deleteTarget, t, loadData]);

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
                    {typeLabel(server.type)}
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
                {server.url && server.type !== 'tunnel' && (
                  <p className="text-xs text-muted-foreground truncate">{server.url}</p>
                )}
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
        tunnelId={tunnelId}
        tunnels={tunnelOptions}
        onOpenChange={setShowCreate}
        onNameChange={setName}
        onTypeChange={setType}
        onUrlChange={setUrl}
        onDescriptionChange={setDescription}
        onAuthHeaderChange={setAuthHeader}
        onTunnelIdChange={setTunnelId}
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
        tunnelId={editTunnelId}
        tunnels={tunnelOptions}
        onClose={() => setEditTarget(null)}
        onNameChange={setEditName}
        onTypeChange={setEditType}
        onUrlChange={setEditUrl}
        onDescriptionChange={setEditDescription}
        onAuthHeaderChange={setEditAuthHeader}
        onTunnelIdChange={setEditTunnelId}
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
