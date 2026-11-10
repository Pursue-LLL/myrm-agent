/**
 * [INPUT]
 * - @/store/useApprovalStore::normalizeApprovalPayload (POS: 审批请求载荷规整)
 * - ./messageDeadLetteredToast::showMessageDeadLetteredToast (POS: 消息死信告警)
 *
 * [OUTPUT]
 * - channelApprovalEventHandlers: 渠道配对 / 连接状态 / 群组 / 死信与工具审批事件的处理器表
 *
 * [POS]
 * 全局事件中与外部渠道、人工审批相关的部分：弹出提示并把事件转给订阅它的页面。
 */
import { showMessageDeadLetteredToast } from '@/hooks/globalEvents/messageDeadLetteredToast';
import { normalizeApprovalPayload } from '@/store/useApprovalStore';

import type { GlobalEventHandler } from './eventTypes';

const handlePairingPending: GlobalEventHandler = (payload, { t, router, pushToast }) => {
  const channel = String(payload.data.channel ?? '');
  const senderId = String(payload.data.sender_id ?? '');
  const displayName = payload.data.display_name ? String(payload.data.display_name) : '';
  const sender = displayName || senderId;
  const toastId = `pairing-pending-${channel}-${senderId}`;
  pushToast.info(t('pairingPending', { channel, sender }), {
    id: toastId,
    duration: 30_000,
    dismissible: true,
    action: {
      label: t('goToApproval'),
      onClick: () => {
        pushToast.dismiss(toastId);
        router.push('/settings/channels');
      },
    },
  });
  window.dispatchEvent(new CustomEvent('pairings-updated'));
};

const handleChannelStatusChange: GlobalEventHandler = (payload) => {
  window.dispatchEvent(
    new CustomEvent('channel-status-change', {
      detail: {
        channel: String(payload.data.channel ?? ''),
        status: String(payload.data.status ?? ''),
        type: payload.type,
      },
    }),
  );
};

const handleGroupsUpdated: GlobalEventHandler = (payload) => {
  window.dispatchEvent(
    new CustomEvent('groups-updated', {
      detail: {
        channel: String(payload.data.channel ?? ''),
        count: Number(payload.data.count ?? 0),
      },
    }),
  );
};

const handleMessageDeadLettered: GlobalEventHandler = (payload, { t, notifyIfLeader }) => {
  showMessageDeadLetteredToast(payload.data, { t, notifyIfLeader });
};

const handleApprovalRequired: GlobalEventHandler = (payload, { t, pushToast, notifyIfLeader }) => {
  const actionType = String(payload.data.action_type ?? 'unknown');
  const normalizedApproval = normalizeApprovalPayload(payload.data);
  const openApprovalDialog = () => {
    import('@/store/useApprovalStore').then((mod) => {
      mod.default.getState().openApproval(normalizedApproval);
    });
  };
  pushToast.info(t('approvalRequired', { actionType }), {
    duration: 8_000,
    dismissible: true,
    action: {
      label: t('reviewApproval'),
      onClick: openApprovalDialog,
    },
  });
  notifyIfLeader(t('approvalRequired', { actionType }), actionType, openApprovalDialog);
  window.dispatchEvent(
    new CustomEvent('approval-required', {
      detail: normalizedApproval,
    }),
  );
};

const handleApprovalResolved: GlobalEventHandler = (payload) => {
  const approvalId = String(payload.data.approval_id ?? '');
  if (approvalId) {
    import('@/store/useApprovalStore').then((mod) => {
      mod.default.getState().closeApproval(approvalId);
    });
  }
  window.dispatchEvent(new CustomEvent('approval_resolved', { detail: payload.data }));
};

export const channelApprovalEventHandlers: Record<string, GlobalEventHandler> = {
  pairing_pending: handlePairingPending,
  channel_connected: handleChannelStatusChange,
  channel_disconnected: handleChannelStatusChange,
  groups_updated: handleGroupsUpdated,
  message_dead_lettered: handleMessageDeadLettered,
  approval_required: handleApprovalRequired,
  approval_resolved: handleApprovalResolved,
};
