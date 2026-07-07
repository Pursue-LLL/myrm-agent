import { toast } from '@/lib/utils/toast';

export type MessageDeadLetteredTranslator = (
  key: string,
  values?: Record<string, string | number>,
) => string;

export interface MessageDeadLetteredToastDeps {
  t: MessageDeadLetteredTranslator;
  notifyIfLeader: (title: string, body?: string, onClick?: () => void) => void;
  dispatchEvent?: (eventName: string) => void;
}

export function showMessageDeadLetteredToast(
  data: Record<string, unknown>,
  deps: MessageDeadLetteredToastDeps,
): void {
  const channel = String(data.channel ?? 'unknown');
  const reason = String(data.error_reason ?? 'Unknown error');
  const message = deps.t('messageDeadLettered', { channel, reason });

  toast.error(message, {
    duration: 10_000,
    dismissible: true,
  });
  deps.notifyIfLeader(message, reason);

  const dispatch =
    deps.dispatchEvent ??
    ((eventName: string) => {
      window.dispatchEvent(new CustomEvent(eventName));
    });
  dispatch('message_dead_lettered');
}
