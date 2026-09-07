'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Network,
  Plus,
  Trash2,
  Edit2,
  Activity,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  ExternalLink,
  ShieldCheck,
  Key,
} from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Input } from '@/components/primitives/input';
import { Textarea } from '@/components/primitives/textarea';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { toast } from '@/hooks/shared/useToast';
import { cn } from '@/lib/utils';
import SettingsSection from '../SettingsSection';
import {
  listA2APeers,
  createA2APeer,
  updateA2APeer,
  deleteA2APeer,
  probeA2APeer,
  type A2APeer,
  type A2APeerProbeResult as A2APeerProbeResponse,
} from '@/services/a2aPeer';

export const A2APeersSection = memo(() => {
  const t = useTranslations('settings.a2aPeers');
  const [peers, setPeers] = useState<A2APeer[]>([]);
  const [loading, setLoading] = useState(true);

  // Dialog State
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingPeer, setEditingPeer] = useState<A2APeer | null>(null);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);

  // Form State
  const [name, setName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [description, setDescription] = useState('');
  const [authType, setAuthType] = useState('bearer');
  const [authToken, setAuthToken] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // Probe State
  const [probingId, setProbingId] = useState<string | null>(null);
  const [probeResult, setProbeResult] = useState<Record<string, A2APeerProbeResponse>>({});

  const fetchPeers = useCallback(async () => {
    try {
      const data = await listA2APeers();
      setPeers(data);
    } catch {
      setPeers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchPeers();
  }, [fetchPeers]);

  const openCreateDialog = () => {
    setEditingPeer(null);
    setName('');
    setBaseUrl('');
    setDescription('');
    setAuthType('bearer');
    setAuthToken('');
    setIsActive(true);
    setIsDialogOpen(true);
  };

  const openEditDialog = (peer: A2APeer) => {
    setEditingPeer(peer);
    setName(peer.name);
    setBaseUrl(peer.base_url);
    setDescription(peer.description || '');
    setAuthType(peer.auth_type);
    setAuthToken('');
    setIsActive(peer.is_active);
    setIsDialogOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !baseUrl.trim()) return;

    setSubmitting(true);
    try {
      if (editingPeer) {
        await updateA2APeer(editingPeer.id, {
          name: name.trim(),
          base_url: baseUrl.trim(),
          description: description.trim() || undefined,
          auth_type: authType,
          auth_token: authToken.trim() || undefined,
          is_active: isActive,
        });
      } else {
        await createA2APeer({
          name: name.trim(),
          base_url: baseUrl.trim(),
          description: description.trim() || undefined,
          auth_type: authType,
          auth_token: authToken.trim() || undefined,
          is_active: isActive,
        });
      }
      setIsDialogOpen(false);
      await fetchPeers();
    } catch {
      toast.error(editingPeer ? t('saveChanges') : t('savePeer'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTargetId) return;
    try {
      await deleteA2APeer(deleteTargetId);
      setDeleteTargetId(null);
      await fetchPeers();
    } catch {
      toast.error(t('deleteConfirm'));
    }
  };

  const handleProbe = async (peer: A2APeer) => {
    setProbingId(peer.id);
    try {
      const res = await probeA2APeer({
        peer_id: peer.id,
      });
      setProbeResult((prev) => ({ ...prev, [peer.id]: res }));
      if (res.success) {
        toast.success(t('probeSuccess', { latency: Math.round(res.latency_ms) }));
      } else if (res.status === 'ssrf_blocked') {
        toast.error(t('ssrfBlocked'));
      } else {
        toast.error(t('probeFailed', { error: res.error || 'Unknown' }));
      }
      await fetchPeers();
    } catch (err: unknown) {
      toast.error(t('probeFailed', { error: String(err) }));
    } finally {
      setProbingId(null);
    }
  };

  return (
    <>
      <SettingsSection
        title={
          <div className="flex items-center gap-2">
            <Network className="h-5 w-5 text-primary" />
            {t('title')}
          </div>
        }
        description={t('registryTitle')}
        action={
          <Button onClick={openCreateDialog} size="sm" className="gap-1.5">
            <Plus className="h-4 w-4" />
            {t('addPeer')}
          </Button>
        }
      >
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : peers.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-8 text-center rounded-xl border border-dashed border-border/70 bg-secondary/10">
            <Network className="h-10 w-10 text-muted-foreground/40 mb-3" />
            <h3 className="font-semibold text-sm mb-1">{t('noPeers')}</h3>
            <p className="text-xs text-muted-foreground max-w-sm mb-4">{t('noPeersDesc')}</p>
            <Button onClick={openCreateDialog} variant="outline" size="sm" className="gap-1.5">
              <Plus className="h-4 w-4" />
              {t('addPeer')}
            </Button>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-1 lg:grid-cols-2">
            {peers.map((peer) => {
              const isProbing = probingId === peer.id;
              const probe = probeResult[peer.id];
              const card = peer.cached_card_json;

              return (
                <div
                  key={peer.id}
                  className={cn(
                    'relative flex flex-col justify-between rounded-xl border p-5 transition-all',
                    peer.is_active
                      ? 'border-border/60 bg-secondary/20 hover:border-border'
                      : 'border-border/30 bg-muted/20 opacity-70',
                  )}
                >
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm text-foreground">{peer.name}</span>
                          <Badge variant={peer.is_active ? 'default' : 'secondary'} className="text-[10px] px-1.5 py-0">
                            {peer.is_active ? t('statusOk') : 'Disabled'}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground font-mono mt-0.5 flex items-center gap-1">
                          {peer.base_url}
                          <a
                            href={peer.base_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="hover:text-foreground"
                          >
                            <ExternalLink className="h-3 w-3 inline" />
                          </a>
                        </p>
                      </div>

                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-muted-foreground hover:text-foreground"
                          onClick={() => openEditDialog(peer)}
                        >
                          <Edit2 className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-muted-foreground hover:text-destructive"
                          onClick={() => setDeleteTargetId(peer.id)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>

                    {peer.description && (
                      <p className="text-xs text-muted-foreground line-clamp-2">{peer.description}</p>
                    )}

                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                      <span className="inline-flex items-center gap-1 bg-secondary/60 px-2 py-0.5 rounded border border-border/40">
                        <Key className="h-3 w-3 text-primary" />
                        {peer.auth_type.toUpperCase()}
                        {peer.masked_token ? ` (${peer.masked_token})` : ''}
                      </span>

                      {peer.last_probe_status && (
                        <span className="inline-flex items-center gap-1 bg-secondary/60 px-2 py-0.5 rounded border border-border/40">
                          {peer.last_probe_status === 'ok' ? (
                            <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                          ) : peer.last_probe_status === 'ssrf_blocked' ? (
                            <ShieldCheck className="h-3 w-3 text-destructive" />
                          ) : peer.last_probe_status === 'error' ? (
                            <AlertTriangle className="h-3 w-3 text-amber-500" />
                          ) : (
                            <XCircle className="h-3 w-3 text-destructive" />
                          )}
                          <span className="capitalize">{peer.last_probe_status}</span>
                        </span>
                      )}
                    </div>

                    {card && typeof card === 'object' && (
                      <div className="rounded-lg bg-background/50 border border-border/40 p-2.5 space-y-1.5 text-xs">
                        <div className="flex items-center justify-between text-[11px] text-muted-foreground font-medium">
                          <span>{t('cardPreview')}</span>
                          {Boolean(card.skills) && (
                            <span className="text-primary">
                              {(card.skills as unknown[]).length} {t('cardSkills')}
                            </span>
                          )}
                        </div>
                        <p className="text-muted-foreground text-[11px] line-clamp-1">
                          {String(card.description || '')}
                        </p>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center justify-between pt-4 mt-2 border-t border-border/40">
                    <span className="text-[10px] text-muted-foreground/60">
                      {probe?.latency_ms ? `${probe.latency_ms}ms` : ''}
                    </span>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs gap-1"
                      disabled={isProbing}
                      onClick={() => handleProbe(peer)}
                    >
                      {isProbing ? (
                        <>
                          <Loader2 className="h-3 w-3 animate-spin" />
                          {t('probing')}
                        </>
                      ) : (
                        <>
                          <Activity className="h-3 w-3 text-emerald-500" />
                          {t('probe')}
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </SettingsSection>

      {/* Add / Edit Peer Dialog */}
      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingPeer ? t('editPeer') : t('newPeer')}</DialogTitle>
            <DialogDescription>{t('description')}</DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4 py-2">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-foreground">{t('peerName')}</label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('peerNamePlaceholder')}
                required
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-foreground">{t('baseUrl')}</label>
              <Input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder={t('baseUrlPlaceholder')}
                required
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-foreground">{t('description')}</label>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t('descriptionPlaceholder')}
                rows={2}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">{t('authType')}</label>
                <select
                  value={authType}
                  onChange={(e) => setAuthType(e.target.value)}
                  className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-xs shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="bearer">{t('authBearer')}</option>
                  <option value="api_key">{t('authApiKey')}</option>
                  <option value="none">{t('authNone')}</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">{t('authToken')}</label>
                <Input
                  type="password"
                  value={authToken}
                  onChange={(e) => setAuthToken(e.target.value)}
                  placeholder={editingPeer ? t('authTokenKeepPlaceholder') : t('authTokenPlaceholder')}
                  disabled={authType === 'none'}
                />
              </div>
            </div>

            <DialogFooter className="pt-2">
              <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>
                {t('cancel')}
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? (
                  <>
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    {t('saving')}
                  </>
                ) : editingPeer ? (
                  t('saveChanges')
                ) : (
                  t('savePeer')
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Alert */}
      <AlertDialog open={deleteTargetId !== null} onOpenChange={(open) => !open && setDeleteTargetId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              {t('deleteConfirm')}
            </AlertDialogTitle>
            <AlertDialogDescription>{t('deleteConfirm')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t('cancel')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
});

A2APeersSection.displayName = 'A2APeersSection';

export default A2APeersSection;
