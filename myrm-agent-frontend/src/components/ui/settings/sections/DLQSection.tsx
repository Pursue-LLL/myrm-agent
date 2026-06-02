'use client';

import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import {
  IconRotateCcw,
  IconHelpCircle,
  IconRefresh,
  IconTrash,
  IconAlertCircle,
} from '@/components/ui/icons/PremiumIcons';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDistanceToNow } from 'date-fns';
import { zhCN, enUS } from 'date-fns/locale';
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
} from '@/components/ui/alert-dialog';

interface QueuedDelivery {
  id: string;
  channel: string;
  recipient: string;
  content: any;
  enqueued_at: number;
  priority: number;
  retry_count: number;
  last_attempt_at?: number;
  last_error?: string;
  failed_at?: number;
}

export default function DLQSection() {
  const t = useTranslations('settings.dlq');
  const [messages, setMessages] = useState<QueuedDelivery[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchMessages = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/v1/channels/dlq');
      const json = await res.json();
      if (json.code === 0) {
        setMessages(json.data);
      } else {
        toast.error(json.message || t('fetchFailed'));
      }
    } catch {
      toast.error(t('fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMessages();
  }, []);

  const handleRetry = async (id: string) => {
    try {
      setActionLoading(`retry-${id}`);
      const res = await fetch(`/api/v1/channels/dlq/${id}/retry`, {
        method: 'POST',
      });
      const json = await res.json();
      if (json.code === 0) {
        toast.success(t('retrySuccess'));
        fetchMessages();
      } else {
        toast.error(json.message || t('retryFailed'));
      }
    } catch {
      toast.error(t('retryFailed'));
    } finally {
      setActionLoading(null);
    }
  };

  const handleRetryAll = async () => {
    try {
      setActionLoading('retry-all');
      const res = await fetch(`/api/v1/channels/dlq/retry-all`, {
        method: 'POST',
      });
      const json = await res.json();
      if (json.code === 0) {
        toast.success(json.message || t('retrySuccess'));
        fetchMessages();
      } else {
        toast.error(json.message || t('retryFailed'));
      }
    } catch {
      toast.error(t('retryFailed'));
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      setActionLoading(`delete-${id}`);
      const res = await fetch(`/api/v1/channels/dlq/${id}`, {
        method: 'DELETE',
      });
      const json = await res.json();
      if (json.code === 0) {
        toast.success(t('deleteSuccess'));
        fetchMessages();
      } else {
        toast.error(json.message || t('deleteFailed'));
      }
    } catch {
      toast.error(t('deleteFailed'));
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeleteAll = async () => {
    try {
      setActionLoading('delete-all');
      const res = await fetch(`/api/v1/channels/dlq/all`, {
        method: 'DELETE',
      });
      const json = await res.json();
      if (json.code === 0) {
        toast.success(json.message || t('deleteSuccess'));
        fetchMessages();
      } else {
        toast.error(json.message || t('deleteFailed'));
      }
    } catch {
      toast.error(t('deleteFailed'));
    } finally {
      setActionLoading(null);
    }
  };

  const getLocale = () => {
    if (typeof window !== 'undefined') {
      return document.documentElement.lang === 'zh' ? zhCN : enUS;
    }
    return enUS;
  };

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">{t('title')}</h2>
          <p className="text-sm text-muted-foreground mt-1">{t('description')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={fetchMessages} disabled={loading || actionLoading !== null}>
            <IconRefresh className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            {t('refresh')}
          </Button>

          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="default" disabled={loading || actionLoading !== null || messages.length === 0}>
                <IconRotateCcw className={`w-4 h-4 mr-2 ${actionLoading === 'retry-all' ? 'animate-spin' : ''}`} />
                {t('retryAll')}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>{t('retryAllConfirmTitle')}</AlertDialogTitle>
                <AlertDialogDescription>{t('retryAllConfirmDesc')}</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
                <AlertDialogAction onClick={handleRetryAll}>{t('confirm')}</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" disabled={loading || actionLoading !== null || messages.length === 0}>
                <IconTrash className={`w-4 h-4 mr-2 ${actionLoading === 'delete-all' ? 'animate-spin' : ''}`} />
                {t('deleteAll')}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>{t('deleteAllConfirmTitle')}</AlertDialogTitle>
                <AlertDialogDescription>{t('deleteAllConfirmDesc')}</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
                <AlertDialogAction
                  onClick={handleDeleteAll}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  {t('confirm')}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      <div className="border rounded-lg overflow-hidden bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('channel')}</TableHead>
              <TableHead>{t('recipient')}</TableHead>
              <TableHead className="max-w-[200px]">{t('content')}</TableHead>
              <TableHead>{t('error')}</TableHead>
              <TableHead>{t('time')}</TableHead>
              <TableHead className="text-right">{t('actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <TableRow key={i}>
                  <TableCell>
                    <Skeleton className="h-4 w-20" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-4 w-24" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-4 w-40" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-4 w-32" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-4 w-24" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-8 w-20 ml-auto" />
                  </TableCell>
                </TableRow>
              ))
            ) : messages.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="h-32 text-center text-muted-foreground">
                  <div className="flex flex-col items-center justify-center">
                    <IconAlertCircle className="w-8 h-8 mb-2 text-muted-foreground/50" />
                    {t('empty')}
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              messages.map((msg) => (
                <TableRow key={msg.id}>
                  <TableCell>
                    <Badge variant="outline">{msg.channel}</Badge>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{msg.recipient}</TableCell>
                  <TableCell className="max-w-[200px] truncate" title={msg.content?.content}>
                    {msg.content?.content || <span className="text-muted-foreground italic">[{t('noText')}]</span>}
                  </TableCell>
                  <TableCell>
                    {msg.last_error ? (
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <div className="flex items-center gap-1 max-w-[150px] cursor-help text-destructive">
                              <IconHelpCircle className="w-3 h-3 shrink-0" />
                              <span className="truncate text-xs">{msg.last_error}</span>
                            </div>
                          </TooltipTrigger>
                          <TooltipContent className="max-w-[400px] break-words">
                            <p className="text-sm font-mono">{msg.last_error}</p>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
                    {msg.failed_at
                      ? formatDistanceToNow(new Date(msg.failed_at * 1000), {
                          addSuffix: true,
                          locale: getLocale(),
                        })
                      : '-'}
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleRetry(msg.id)}
                        disabled={actionLoading !== null}
                      >
                        <IconRefresh
                          className={`w-3 h-3 mr-1 ${actionLoading === `retry-${msg.id}` ? 'animate-spin' : ''}`}
                        />
                        {t('retry')}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive hover:bg-destructive/10"
                        onClick={() => handleDelete(msg.id)}
                        disabled={actionLoading !== null}
                      >
                        <IconTrash
                          className={`w-3 h-3 ${actionLoading === `delete-${msg.id}` ? 'animate-spin' : ''}`}
                        />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
