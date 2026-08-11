'use client';

/**
 * Batch directory parallel prompt runner — list + create wizard.
 *
 * [INPUT]
 * - @/services/batch-directory::* (POS: 批量目录 API 服务层)
 * - @/services/kanban::listBoards (POS: 看板 API，用于选择目标 board)
 * - @/services/chat::browseDirectories (POS: 目录浏览 API)
 *
 * [OUTPUT]
 * - BatchDirectoriesPage: 批量项目列表 + 创建向导
 *
 * [POS]
 * BatchDirectory 列表页。展示全部批量项目与聚合进度，并提供创建向导。
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import Link from 'next/link';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Textarea } from '@/components/primitives/textarea';
import { Skeleton } from '@/components/primitives/skeleton';
import { Badge } from '@/components/primitives/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/primitives/table';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/primitives/alert-dialog';
import { Checkbox } from '@/components/primitives/checkbox';
import { Label } from '@/components/primitives/label';
import { Switch } from '@/components/primitives/switch';
import { Progress } from '@/components/primitives/progress';
import {
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  FolderOpen,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  XCircle,
} from 'lucide-react';
import { toast } from '@/hooks/shared/useToast';
import { cn } from '@/lib/utils/classnameUtils';
import {
  cancelBatchProject,
  createBatchProject,
  deleteBatchProject,
  listBatchProjects,
  type BatchProject,
  type CreateBatchProjectInput,
} from '@/services/batch-directory';
import { listBoards, type KanbanBoard } from '@/services/kanban';
import { browseDirectories, type DirectoryEntry } from '@/services/chat';

interface CreateFormState {
  name: string;
  prompt: string;
  board_id: string;
  concurrency: string;
  notify_enabled: boolean;
  require_approval: boolean;
  artifact_patterns: string;
}

const EMPTY_FORM: CreateFormState = {
  name: '',
  prompt: '',
  board_id: '',
  concurrency: '3',
  notify_enabled: true,
  require_approval: false,
  artifact_patterns: '',
};

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString();
}

export default function BatchDirectoriesPage() {
  const t = useTranslations('batchDirectory');
  const router = useRouter();

  const [projects, setProjects] = useState<BatchProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<CreateFormState>(EMPTY_FORM);
  const [boards, setBoards] = useState<KanbanBoard[]>([]);
  const [confirming, setConfirming] = useState<BatchProject | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  // 目录浏览状态
  const [currentDir, setCurrentDir] = useState('~');
  const [dirEntries, setDirEntries] = useState<DirectoryEntry[]>([]);
  const [browsing, setBrowsing] = useState(false);
  const [selectedDirs, setSelectedDirs] = useState<string[]>([]);

  const fetchProjects = useCallback(async () => {
    try {
      const items = await listBatchProjects();
      setProjects(items);
    } catch {
      toast.error(t('listError'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  const fetchBoards = useCallback(async () => {
    try {
      const res = await listBoards();
      setBoards(res.items);
    } catch {
      // 看板列表失败不阻断创建流程（可自动创建 board）
    }
  }, []);

  useEffect(() => {
    void fetchProjects();
    void fetchBoards();
  }, [fetchProjects, fetchBoards]);

  const browseDir = useCallback(async (path: string) => {
    setBrowsing(true);
    try {
      const res = await browseDirectories(path);
      setCurrentDir(res.current);
      setDirEntries(res.entries);
    } catch {
      toast.error(t('browseError'));
    } finally {
      setBrowsing(false);
    }
  }, [t]);

  useEffect(() => {
    if (showCreate) void browseDir('~');
  }, [showCreate, browseDir]);

  const progressOf = useCallback((p: BatchProject) => {
    const total = p.total_tasks || 0;
    if (total === 0) return 0;
    return Math.round(((p.completed_tasks + p.failed_tasks) / total) * 100);
  }, []);

  const statusMeta = useCallback(
    (status: string) => {
      switch (status) {
        case 'running':
          return {
            label: t('statusRunning'),
            icon: <Loader2 className="size-3 mr-1 animate-spin" />,
            className: '',
          };
        case 'completed':
          return {
            label: t('statusCompleted'),
            icon: <CheckCircle2 className="size-3 mr-1 text-emerald-500" />,
            className: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600',
          };
        case 'failed':
          return {
            label: t('statusFailed'),
            icon: <XCircle className="size-3 mr-1" />,
            className: 'border-destructive/30 bg-destructive/10 text-destructive',
          };
        case 'cancelled':
          return {
            label: t('statusCancelled'),
            icon: <XCircle className="size-3 mr-1" />,
            className: 'border-muted bg-muted/50 text-muted-foreground',
          };
        default:
          return {
            label: t('statusDraft'),
            icon: <Clock className="size-3 mr-1" />,
            className: 'border-muted bg-muted/50 text-muted-foreground',
          };
      }
    },
    [t],
  );

  const handleToggleDir = useCallback((path: string) => {
    setSelectedDirs((prev) => (prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path]));
  }, []);

  const handleCreate = useCallback(async () => {
    if (!form.name.trim()) {
      toast.error(t('nameRequired'));
      return;
    }
    if (!form.prompt.trim()) {
      toast.error(t('promptRequired'));
      return;
    }
    if (selectedDirs.length === 0) {
      toast.error(t('dirsRequired'));
      return;
    }

    const input: CreateBatchProjectInput = {
      name: form.name.trim(),
      prompt: form.prompt.trim(),
      directories: [...selectedDirs],
      board_id: form.board_id || null,
      concurrency: Number(form.concurrency) || 3,
      notify_enabled: form.notify_enabled,
      require_approval: form.require_approval,
      artifact_patterns: form.artifact_patterns
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    };

    setCreating(true);
    try {
      const created = await createBatchProject(input);
      toast.success(t('createSuccess', { name: created.name }));
      setShowCreate(false);
      setForm(EMPTY_FORM);
      setSelectedDirs([]);
      setDirEntries([]);
      await fetchProjects();
      router.push(`/batch-directories/${created.project_id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('createError'));
    } finally {
      setCreating(false);
    }
  }, [form, selectedDirs, fetchProjects, router, t]);

  const handleCancel = useCallback(
    async (p: BatchProject) => {
      setCancellingId(p.project_id);
      try {
        await cancelBatchProject(p.project_id);
        toast.success(t('cancelSuccess', { name: p.name }));
        setConfirming(null);
        await fetchProjects();
      } catch {
        toast.error(t('cancelError'));
      } finally {
        setCancellingId(null);
      }
    },
    [fetchProjects, t],
  );

  const handleDelete = useCallback(
    async (p: BatchProject) => {
      try {
        await deleteBatchProject(p.project_id);
        toast.success(t('deleteSuccess', { name: p.name }));
        await fetchProjects();
      } catch {
        toast.error(t('deleteError'));
      }
    },
    [fetchProjects, t],
  );

  const summary = useMemo(() => {
    const total = projects.reduce((acc, p) => acc + p.total_tasks, 0);
    const completed = projects.reduce((acc, p) => acc + p.completed_tasks, 0);
    const failed = projects.reduce((acc, p) => acc + p.failed_tasks, 0);
    const running = projects.filter((p) => p.status === 'running').length;
    return { total, completed, failed, running };
  }, [projects]);

  if (loading) {
    return (
      <div className="container mx-auto max-w-5xl px-4 py-8 space-y-4">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-5xl px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t('pageTitle')}</h1>
          <p className="text-sm text-muted-foreground mt-1">{t('pageDescription')}</p>
        </div>
        <Button onClick={() => setShowCreate((v) => !v)} disabled={creating}>
          <Plus className="size-4 mr-1" />
          {t('createButton')}
        </Button>
      </div>

      {!showCreate && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <Card>
            <CardContent className="pt-4">
              <p className="text-sm text-muted-foreground">{t('statProjects')}</p>
              <p className="text-2xl font-semibold mt-1">{projects.length}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <p className="text-sm text-muted-foreground">{t('statRunning')}</p>
              <p className="text-2xl font-semibold mt-1">{summary.running}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <p className="text-sm text-muted-foreground">{t('statCompleted')}</p>
              <p className="text-2xl font-semibold mt-1">{summary.completed}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <p className="text-sm text-muted-foreground">{t('statFailed')}</p>
              <p className="text-2xl font-semibold mt-1">{summary.failed}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {showCreate && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>{t('createTitle')}</CardTitle>
            <CardDescription>{t('createDescription')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4">
              <div className="grid gap-1.5">
                <Label htmlFor="bd-name">{t('nameLabel')}</Label>
                <Input
                  id="bd-name"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder={t('namePlaceholder')}
                  maxLength={255}
                />
              </div>

              <div className="grid gap-1.5">
                <Label htmlFor="bd-prompt">{t('promptLabel')}</Label>
                <Textarea
                  id="bd-prompt"
                  value={form.prompt}
                  onChange={(e) => setForm((f) => ({ ...f, prompt: e.target.value }))}
                  placeholder={t('promptPlaceholder')}
                  rows={4}
                />
              </div>

              <div className="grid gap-1.5">
                <Label>{t('dirsLabel')}</Label>
                <div className="rounded-md border bg-muted/30 p-2 flex items-center gap-2 text-sm">
                  <FolderOpen className="size-4 text-muted-foreground shrink-0" />
                  <span className="truncate flex-1 font-mono">{currentDir}</span>
                  {currentDir !== '~' && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        const parts = currentDir.split('/').filter(Boolean);
                        parts.pop();
                        void browseDir(parts.length ? `/${parts.join('/')}` : '~');
                      }}
                      disabled={browsing}
                    >
                      <ChevronLeft className="size-4" />
                      {t('browseUp')}
                    </Button>
                  )}
                  <Button variant="ghost" size="sm" onClick={() => void browseDir(currentDir)} disabled={browsing}>
                    <RefreshCw className={cn('size-4', browsing && 'animate-spin')} />
                  </Button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-1 max-h-56 overflow-y-auto rounded-md border p-2">
                  {dirEntries.length === 0 && (
                    <p className="text-sm text-muted-foreground col-span-2 py-4 text-center">{t('browseEmpty')}</p>
                  )}
                  {dirEntries.map((entry) => {
                    const checked = selectedDirs.includes(entry.path);
                    return (
                      <label
                        key={entry.path}
                        onClick={() => handleToggleDir(entry.path)}
                        className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-accent cursor-pointer text-sm"
                      >
                        <Checkbox checked={checked} className="pointer-events-none" />
                        <span className={cn('truncate flex-1', checked && 'font-medium')}>{entry.name}</span>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="size-7"
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            void browseDir(entry.path);
                          }}
                          aria-label={t('browseInto')}
                        >
                          <ChevronRight className="size-3.5" />
                        </Button>
                      </label>
                    );
                  })}
                </div>
                {selectedDirs.length > 0 && (
                  <p className="text-xs text-muted-foreground">
                    {t('dirsSelectedCount', { count: selectedDirs.length })}
                  </p>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="grid gap-1.5">
                  <Label htmlFor="bd-board">{t('boardLabel')}</Label>
                  <select
                    id="bd-board"
                    value={form.board_id}
                    onChange={(e) => setForm((f) => ({ ...f, board_id: e.target.value }))}
                    className="h-9 rounded-md border bg-transparent px-3 text-sm"
                  >
                    <option value="">{t('boardAuto')}</option>
                    {boards.map((b) => (
                      <option key={b.board_id} value={b.board_id}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="bd-concurrency">{t('concurrencyLabel')}</Label>
                  <Input
                    id="bd-concurrency"
                    type="number"
                    min={1}
                    max={50}
                    value={form.concurrency}
                    onChange={(e) => setForm((f) => ({ ...f, concurrency: e.target.value }))}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="bd-artifacts">{t('artifactPatternsLabel')}</Label>
                  <Input
                    id="bd-artifacts"
                    value={form.artifact_patterns}
                    onChange={(e) => setForm((f) => ({ ...f, artifact_patterns: e.target.value }))}
                    placeholder={t('artifactPatternsPlaceholder')}
                  />
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Switch
                  id="bd-notify"
                  checked={form.notify_enabled}
                  onCheckedChange={(v) => setForm((f) => ({ ...f, notify_enabled: v }))}
                />
                <Label htmlFor="bd-notify">{t('notifyLabel')}</Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  id="bd-approval"
                  checked={form.require_approval}
                  onCheckedChange={(v) => setForm((f) => ({ ...f, require_approval: v }))}
                />
                <Label htmlFor="bd-approval">{t('approvalLabel')}</Label>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="ghost" onClick={() => setShowCreate(false)}>
                {t('cancelButton')}
              </Button>
              <Button onClick={handleCreate} disabled={creating}>
                {creating ? <Loader2 className="size-4 mr-1 animate-spin" /> : <Play className="size-4 mr-1" />}
                {t('createButton')}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('tableName')}</TableHead>
                <TableHead>{t('tableStatus')}</TableHead>
                <TableHead>{t('tableProgress')}</TableHead>
                <TableHead>{t('tableDirectories')}</TableHead>
                <TableHead>{t('tableCreated')}</TableHead>
                <TableHead className="text-right">{t('tableActions')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {projects.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-10 text-muted-foreground">
                    {t('emptyState')}
                  </TableCell>
                </TableRow>
              )}
              {projects.map((p) => {
                const meta = statusMeta(p.status);
                const progress = progressOf(p);
                const running = p.status === 'running';
                return (
                  <TableRow key={p.project_id}>
                    <TableCell className="font-medium">
                      <Link href={`/batch-directories/${p.project_id}`} className="hover:underline">
                        {p.name}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Badge className={meta.className}>{meta.icon}{meta.label}</Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2 min-w-36">
                        <Progress value={progress} className="w-24" />
                        <span className="text-xs text-muted-foreground whitespace-nowrap">
                          {p.completed_tasks}/{p.total_tasks}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {t('dirsCount', { count: p.directories.length })}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{formatDateTime(p.created_at)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="sm" asChild>
                          <Link href={`/batch-directories/${p.project_id}`}>
                            <ArrowRight className="size-4" />
                          </Link>
                        </Button>
                        {running && (
                          <AlertDialog>
                            <AlertDialogTrigger asChild>
                              <Button variant="outline" size="sm" disabled={cancellingId === p.project_id}>
                                {cancellingId === p.project_id ? <Loader2 className="size-4 animate-spin" /> : t('cancelAction')}
                              </Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                              <AlertDialogHeader>
                                <AlertDialogTitle>{t('confirmCancelTitle', { name: p.name })}</AlertDialogTitle>
                                <AlertDialogDescription>{t('confirmCancelDescription')}</AlertDialogDescription>
                              </AlertDialogHeader>
                              <AlertDialogFooter>
                                <AlertDialogCancel>{t('cancelButton')}</AlertDialogCancel>
                                <AlertDialogAction onClick={() => void handleCancel(p)}>
                                  {t('confirmCancelAction')}
                                </AlertDialogAction>
                              </AlertDialogFooter>
                            </AlertDialogContent>
                          </AlertDialog>
                        )}
                        {!running && (
                          <AlertDialog open={confirming?.project_id === p.project_id} onOpenChange={(open) => !open && setConfirming(null)}>
                            <AlertDialogTrigger asChild>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-destructive"
                                onClick={() => setConfirming(p)}
                              >
                                <XCircle className="size-4" />
                              </Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                              <AlertDialogHeader>
                                <AlertDialogTitle>{t('confirmDeleteTitle', { name: p.name })}</AlertDialogTitle>
                                <AlertDialogDescription>{t('confirmDeleteDescription')}</AlertDialogDescription>
                              </AlertDialogHeader>
                              <AlertDialogFooter>
                                <AlertDialogCancel>{t('cancelButton')}</AlertDialogCancel>
                                <AlertDialogAction
                                  onClick={() => void handleDelete(p)}
                                  className="bg-destructive text-destructive-foreground"
                                >
                                  {t('confirmDeleteAction')}
                                </AlertDialogAction>
                              </AlertDialogFooter>
                            </AlertDialogContent>
                          </AlertDialog>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
