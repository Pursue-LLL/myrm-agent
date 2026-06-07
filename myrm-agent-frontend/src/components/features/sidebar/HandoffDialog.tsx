'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ArrowRightLeft, Loader2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import ChannelIcon from '@/components/features/settings/sections/integration/channels/ChannelIcon';
import { listChannelInstances, type ChannelInstance } from '@/services/channels';
import { handoffChat } from '@/services/chat';
import { useToast } from '@/hooks/useToast';
import { cn } from '@/lib/utils/classnameUtils';

interface HandoffDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chatId: string;
  chatTitle: string;
  currentSource?: string;
}

export function HandoffDialog({ open, onOpenChange, chatId, chatTitle, currentSource }: HandoffDialogProps) {
  const t = useTranslations();
  const { toast } = useToast();
  const [channels, setChannels] = useState<ChannelInstance[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);
  const [transferring, setTransferring] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setSelectedChannel(null);
    listChannelInstances()
      .then((list) => {
        const available = list.filter((ch) => ch.status === 'connected' && ch.channelName !== currentSource);
        setChannels(available);
      })
      .catch(() => setChannels([]))
      .finally(() => setLoading(false));
  }, [open, currentSource]);

  const handleTransfer = async () => {
    if (!selectedChannel) return;
    setTransferring(true);
    try {
      await handoffChat(chatId, selectedChannel);
      toast({
        title: t('chat.handoff.success'),
        description: t('chat.handoff.successDesc', {
          target: channels.find((c) => c.channelName === selectedChannel)?.displayName || selectedChannel,
        }),
      });
      onOpenChange(false);
    } catch (err) {
      toast({
        title: t('chat.handoff.failed'),
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
      });
    } finally {
      setTransferring(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ArrowRightLeft className="h-4 w-4" />
            {t('chat.handoff.title')}
          </DialogTitle>
          <DialogDescription>{t('chat.handoff.description', { title: chatTitle.slice(0, 40) })}</DialogDescription>
        </DialogHeader>

        <div className="py-3">
          {loading ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          ) : channels.length === 0 ? (
            <p className="text-center py-8 text-sm text-muted-foreground">{t('chat.handoff.noChannels')}</p>
          ) : (
            <div className="space-y-1.5 max-h-[240px] overflow-y-auto">
              {channels.map((ch) => (
                <button
                  key={ch.channelName}
                  onClick={() => setSelectedChannel(ch.channelName)}
                  className={cn(
                    'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors',
                    'hover:bg-black/5 dark:hover:bg-white/5',
                    selectedChannel === ch.channelName && 'bg-primary/10 ring-1 ring-primary/30',
                  )}
                >
                  <ChannelIcon channelId={ch.channelType} size={20} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{ch.displayName || ch.channelName}</p>
                    <p className="text-xs text-muted-foreground truncate">{ch.channelType}</p>
                  </div>
                  <span
                    className={cn(
                      'w-2 h-2 rounded-full flex-shrink-0',
                      ch.status === 'connected' ? 'bg-emerald-500' : 'bg-muted',
                    )}
                  />
                </button>
              ))}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={transferring}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleTransfer} disabled={!selectedChannel || transferring}>
            {transferring && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
            {t('chat.handoff.transfer')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
