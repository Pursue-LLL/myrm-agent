'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Switch } from '@/components/primitives/switch';
import { Skeleton } from '@/components/primitives/skeleton';
import { Input } from '@/components/primitives/input';
import { Textarea } from '@/components/primitives/textarea';
import {
  Globe,
  Plus,
  Trash2,
  RefreshCw,
  Send,
  CheckCircle2,
  AlertCircle,
  Shield,
  Pencil,
  FileCode,
  X,
  ShieldAlert,
} from 'lucide-react';
import {
  listA2APeers,
  createA2APeer,
  updateA2APeer,
  deleteA2APeer,
  probeA2APeer,
  type A2APeer,
  type A2APeerCreateInput,
  type A2APeerUpdateInput,
  type A2APeerProbeResult,
} from '@/services/a2aPeer';

interface PeerFormValues {
  name: string;
  baseUrl: string;
  description: string;
  authType: string;
  authToken: string;
  isActive: boolean;
}

const emptyFormValues = (): PeerFormValues => ({
  name: '',
  baseUrl: '',
  description: '',
  authType: 'bearer',
  authToken: '',
  isActive: true,
});

export const A2APeerRegistrySection = memo(() => {
  const t = useTranslations('settings.a2aPeers');
  const [peers, setPeers] = useState<A2APeer[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingPeer, setEditingPeer] = useState<A2APeer | null>(null);
  const [formValues, setFormValues] = useState<PeerFormValues>(emptyFormValues());
  const [submitting, setSubmitting] = useState(false);
  const [probingId, setProbingId] = useState<string | null>(null);
  const [previewCardPeer, setPreviewCardPeer] = useState<A2APeer | null>(null);
  const [probeResult, setProbeResult] = useState<{ id: string; result: A2APeerProbeResult } | null>(null);
  const [modalProbeLoading, setModalProbeLoading] = useState(false);
  const [modalProbeResult, setModalProbeResult] = useState<A2APeerProbeResult | null>(null);

  const fetchPeers = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listA2APeers();
      setPeers(Array.isArray(data) ? data : []);
    } catch {
      setPeers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPeers();
  }, [fetchPeers]);

  const handleOpenCreate = () => {
    setEditingPeer(null);
    setFormValues(emptyFormValues());
    setModalProbeResult(null);
    setShowModal(true);
  };

  const handleOpenEdit = (peer: A2APeer) => {
    setEditingPeer(peer);
    setFormValues({
      name: peer.name,
      baseUrl: peer.base_url,
      description: peer.description || '',
      authType: peer.auth_type,
      authToken: '',
      isActive: peer.is_active,
    });
    setModalProbeResult(null);
    setShowModal(true);
  };

  const handleToggleActive = async (peer: A2APeer, checked: boolean) => {
    try {
      await updateA2APeer(peer.id, { is_active: checked });
      setPeers((prev) => prev.map((p) => (p.id === peer.id ? { ...p, is_active: checked } : p)));
    } catch {
      // Revert if failed
    }
  };

  const handleDelete = async (peerId: string) => {
    if (!window.confirm(t('deleteConfirm'))) return;
    try {
      await deleteA2APeer(peerId);
      setPeers((prev) => prev.filter((p) => p.id !== peerId));
    } catch {
      // Handle error
    }
  };

  const handleProbeSaved = async (peer: A2APeer) => {
    try {
      setProbingId(peer.id);
      const res = await probeA2APeer({ peer_id: peer.id });
      setProbeResult({ id: peer.id, result: res });
      await fetchPeers();
    } catch (err) {
      setProbeResult({
        id: peer.id,
        result: {
          success: false,
          status: 'error',
          latency_ms: 0,
          error: String(err),
        },
      });
    } finally {
      setProbingId(null);
    }
  };

  const handleModalProbe = async () => {
    if (!formValues.baseUrl.trim()) return;
    try {
      setModalProbeLoading(true);
      const res = await probeA2APeer({
        url: formValues.baseUrl.trim(),
        auth_token: formValues.authToken.trim() || undefined,
        peer_id: editingPeer?.id,
      });
      setModalProbeResult(res);
    } catch (err) {
      setModalProbeResult({
        success: false,
        status: 'error',
        latency_ms: 0,
        error: String(err),
      });
    } finally {
      setModalProbeLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formValues.name.trim() || !formValues.baseUrl.trim()) return;

    try {
      setSubmitting(true);
      if (editingPeer) {
        const updatePayload: A2APeerUpdateInput = {
          name: formValues.name.trim(),
          base_url: formValues.baseUrl.trim(),
          description: formValues.description.trim() || undefined,
          auth_type: formValues.authType,
          auth_token: formValues.authToken.trim() || undefined,
          is_active: formValues.isActive,
        };
        await updateA2APeer(editingPeer.id, updatePayload);
      } else {
        const createPayload: A2APeerCreateInput = {
          name: formValues.name.trim(),
          base_url: formValues.baseUrl.trim(),
          description: formValues.description.trim() || undefined,
          auth_type: formValues.authType,
          auth_token: formValues.authToken.trim() || undefined,
          is_active: formValues.isActive,
        };
        await createA2APeer(createPayload);
      }
      setShowModal(false);
      await fetchPeers();
    } finally {
      setSubmitting(false);
    }
  };

  const renderStatusBadge = (peer: A2APeer) => {
    if (peer.last_probe_status === 'ok') {
      return (
        <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 gap-1 text-[11px]">
          <CheckCircle2 className="w-3 h-3" />
          {t('statusOk')}
        </Badge>
      );
    }
    if (peer.last_probe_status === 'ssrf_blocked') {
      return (
        <Badge variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400 gap-1 text-[11px]">
          <ShieldAlert className="w-3 h-3" />
          {t('statusSsrf')}
        </Badge>
      );
    }
    if (peer.last_probe_status === 'error') {
      return (
        <Badge variant="outline" className="border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400 gap-1 text-[11px]">
          <AlertCircle className="w-3 h-3" />
          {t('statusError')}
        </Badge>
      );
    }
    return (
      <Badge variant="outline" className="text-muted-foreground border-border text-[11px]">
        {peer.auth_type.toUpperCase()}
      </Badge>
    );
  };

  return (
    <div className="mt-8 border-t border-border pt-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Globe className="w-5 h-5 text-indigo-500" />
            {t('title')}
          </h3>
          <p className="text-xs text-muted-foreground mt-1 max-w-2xl">{t('description')}</p>
        </div>
        <Button size="sm" onClick={handleOpenCreate} className="gap-1.5 shrink-0 self-start sm:self-auto">
          <Plus className="w-4 h-4" />
          {t('addPeer')}
        </Button>
      </div>

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-20 w-full rounded-xl" />
        </div>
      ) : peers.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-card/50 p-8 text-center">
          <Globe className="w-8 h-8 text-muted-foreground mx-auto mb-2 opacity-50" />
          <p className="text-sm font-medium text-foreground">{t('noPeers')}</p>
          <p className="text-xs text-muted-foreground mt-1 max-w-md mx-auto">{t('noPeersDesc')}</p>
          <Button variant="outline" size="sm" onClick={handleOpenCreate} className="mt-4 gap-1.5">
            <Plus className="w-3.5 h-3.5" />
            {t('addPeer')}
          </Button>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-1">
          {peers.map((peer) => {
            const isProbing = probingId === peer.id;
            const currentProbe = probeResult?.id === peer.id ? probeResult.result : null;

            return (
              <div
                key={peer.id}
                className={cn(
                  'rounded-xl border border-border bg-card p-4 transition-all hover:border-primary/20',
                  !peer.is_active && 'opacity-60',
                )}
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h4 className="text-sm font-medium text-foreground truncate">{peer.name}</h4>
                      {renderStatusBadge(peer)}
                      {peer.has_token && (
                        <span className="text-[11px] text-muted-foreground font-mono flex items-center gap-1 bg-muted/60 px-1.5 py-0.5 rounded">
                          <Shield className="w-3 h-3 text-emerald-500" />
                          {peer.masked_token || t('hasToken')}
                        </span>
                      )}
                    </div>
                    <p className="text-xs font-mono text-muted-foreground mt-1 truncate">{peer.base_url}</p>
                    {peer.description && (
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-1">{peer.description}</p>
                    )}
                  </div>

                  <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
                    {peer.cached_card_json && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-8 px-2 text-xs gap-1"
                        onClick={() => setPreviewCardPeer(peer)}
                      >
                        <FileCode className="w-3.5 h-3.5" />
                        {t('cardPreview')}
                      </Button>
                    )}

                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 px-2.5 text-xs gap-1"
                      disabled={isProbing}
                      onClick={() => handleProbeSaved(peer)}
                    >
                      <RefreshCw className={cn('w-3.5 h-3.5', isProbing && 'animate-spin')} />
                      {t('probe')}
                    </Button>

                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-8 w-8 p-0"
                      onClick={() => handleOpenEdit(peer)}
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </Button>

                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-8 w-8 p-0 text-red-500 hover:text-red-600 hover:bg-red-500/10"
                      onClick={() => handleDelete(peer.id)}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>

                    <Switch
                      checked={peer.is_active}
                      onCheckedChange={(checked) => handleToggleActive(peer, checked)}
                    />
                  </div>
                </div>

                {currentProbe && (
                  <div
                    className={cn(
                      'mt-2.5 rounded-lg px-3 py-1.5 text-xs flex items-center gap-2 border',
                      currentProbe.success
                        ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-700 dark:text-emerald-300'
                        : 'border-red-500/20 bg-red-500/5 text-red-700 dark:text-red-300',
                    )}
                  >
                    {currentProbe.success ? (
                      <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                    ) : (
                      <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                    )}
                    <span>
                      {currentProbe.success
                        ? t('probeSuccess', { latency: currentProbe.latency_ms })
                        : t('probeFailed', { error: currentProbe.error || '' })}
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Add / Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in-50">
          <div className="bg-card border border-border w-full max-w-lg rounded-2xl shadow-xl overflow-hidden">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                <Globe className="w-4 h-4 text-indigo-500" />
                {editingPeer ? t('editPeer') : t('newPeer')}
              </h3>
              <Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={() => setShowModal(false)}>
                <X className="w-4 h-4" />
              </Button>
            </div>

            <form onSubmit={handleSubmit} className="p-5 space-y-4">
              <div>
                <label className="text-xs font-medium text-foreground block mb-1.5">{t('peerName')} *</label>
                <Input
                  value={formValues.name}
                  onChange={(e) => setFormValues((v) => ({ ...v, name: e.target.value }))}
                  placeholder={t('peerNamePlaceholder')}
                  required
                />
              </div>

              <div>
                <label className="text-xs font-medium text-foreground block mb-1.5">{t('baseUrl')} *</label>
                <Input
                  value={formValues.baseUrl}
                  onChange={(e) => setFormValues((v) => ({ ...v, baseUrl: e.target.value }))}
                  placeholder={t('baseUrlPlaceholder')}
                  required
                />
              </div>

              <div>
                <label className="text-xs font-medium text-foreground block mb-1.5">{t('description')}</label>
                <Textarea
                  value={formValues.description}
                  onChange={(e) => setFormValues((v) => ({ ...v, description: e.target.value }))}
                  placeholder={t('descriptionPlaceholder')}
                  rows={2}
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-medium text-foreground block mb-1.5">{t('authType')}</label>
                  <select
                    className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                    value={formValues.authType}
                    onChange={(e) => setFormValues((v) => ({ ...v, authType: e.target.value }))}
                  >
                    <option value="bearer">{t('authBearer')}</option>
                    <option value="api_key">{t('authApiKey')}</option>
                    <option value="none">{t('authNone')}</option>
                  </select>
                </div>

                {formValues.authType !== 'none' && (
                  <div>
                    <label className="text-xs font-medium text-foreground block mb-1.5">{t('authToken')}</label>
                    <Input
                      type="password"
                      value={formValues.authToken}
                      onChange={(e) => setFormValues((v) => ({ ...v, authToken: e.target.value }))}
                      placeholder={editingPeer ? t('authTokenKeepPlaceholder') : t('authTokenPlaceholder')}
                    />
                  </div>
                )}
              </div>

              {/* Probe check inside modal */}
              <div className="pt-2 border-t border-border flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">{t('probe')}</span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs gap-1"
                    disabled={modalProbeLoading || !formValues.baseUrl.trim()}
                    onClick={handleModalProbe}
                  >
                    <Send className={cn('w-3 h-3', modalProbeLoading && 'animate-spin')} />
                    {modalProbeLoading ? t('probing') : t('probe')}
                  </Button>
                </div>

                {modalProbeResult && (
                  <div
                    className={cn(
                      'rounded-md px-2.5 py-1.5 text-xs flex items-center gap-1.5 border',
                      modalProbeResult.success
                        ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-700 dark:text-emerald-300'
                        : 'border-red-500/20 bg-red-500/5 text-red-700 dark:text-red-300',
                    )}
                  >
                    {modalProbeResult.success ? (
                      <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                    ) : (
                      <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                    )}
                    <span className="truncate">
                      {modalProbeResult.success
                        ? t('probeSuccess', { latency: modalProbeResult.latency_ms })
                        : t('probeFailed', { error: modalProbeResult.error || '' })}
                    </span>
                  </div>
                )}
              </div>

              <div className="flex items-center justify-end gap-2.5 pt-4 border-t border-border">
                <Button type="button" variant="ghost" size="sm" onClick={() => setShowModal(false)}>
                  {t('cancel')}
                </Button>
                <Button type="submit" size="sm" disabled={submitting}>
                  {submitting ? t('saving') : editingPeer ? t('saveChanges') : t('savePeer')}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* AgentCard Preview Modal */}
      {previewCardPeer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in-50">
          <div className="bg-card border border-border w-full max-w-xl rounded-2xl shadow-xl overflow-hidden flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <div className="flex items-center gap-2">
                <FileCode className="w-4 h-4 text-indigo-500" />
                <h3 className="text-base font-semibold text-foreground">{previewCardPeer.name} - AgentCard</h3>
              </div>
              <Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={() => setPreviewCardPeer(null)}>
                <X className="w-4 h-4" />
              </Button>
            </div>
            <div className="p-5 overflow-y-auto">
              <pre className="rounded-xl bg-muted/60 p-4 text-xs font-mono overflow-x-auto text-foreground border border-border">
                {JSON.stringify(previewCardPeer.cached_card_json, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
});

A2APeerRegistrySection.displayName = 'A2APeerRegistrySection';
