/**
 * [INPUT]
 * - ./probe (POS: 探测状态与推荐模式类型)
 * - @/components/primitives/button (POS: 按钮原语)
 *
 * [OUTPUT]
 * - ProbeDiagnostics: 探测失败态的本地化诊断与下一步动作（重试探测 / 切换到本地模式）
 *
 * [POS]
 * 连接对话框的展示层：无状态，仅在不可达或云端不支持时渲染，文案全部来自 i18n。
 */
'use client';

import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import type { ProbeRecommendedMode, ProbeStatus } from './probe';

interface ProbeDiagnosticsProps {
  probeStatus: ProbeStatus;
  probeError: string | null;
  probeRecommendedMode: ProbeRecommendedMode | null;
  actionDisabled: boolean;
  onRecommendedAction: () => void;
}

export function ProbeDiagnostics({
  probeStatus,
  probeError,
  probeRecommendedMode,
  actionDisabled,
  onRecommendedAction,
}: ProbeDiagnosticsProps) {
  const t = useTranslations('settings.integrationCatalog.connectDialog');
  const failed = probeStatus === 'unreachable' || probeStatus === 'cloud_not_supported';

  const recommendedMessage =
    probeRecommendedMode === 'local_or_tauri'
      ? t('probeRecommendedModeLocalOrTauri')
      : probeRecommendedMode === 'start_local_editor_mcp'
        ? t('probeRecommendedModeStartLocalEditorMcp')
        : probeRecommendedMode === 'verify_local_network_and_editor'
          ? t('probeRecommendedModeVerifyLocalNetworkAndEditor')
          : null;

  const recommendedActionLabel =
    probeRecommendedMode === 'local_or_tauri'
      ? t('probeRecommendedActionSwitchMode')
      : t('probeRecommendedActionRetryProbe');

  return (
    <>
      {failed && probeError && (
        <div className="bg-destructive/10 border-destructive/20 rounded-md border p-3">
          <p className="text-destructive text-sm">{probeError}</p>
        </div>
      )}
      {failed && probeRecommendedMode && recommendedMessage && (
        <div className="bg-muted rounded-md border p-3">
          <p className="text-sm font-medium">{t('probeRecommendedActionTitle')}</p>
          <p className="text-muted-foreground mt-1 text-sm">{recommendedMessage}</p>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="mt-3"
            disabled={actionDisabled}
            onClick={onRecommendedAction}
          >
            {recommendedActionLabel}
          </Button>
        </div>
      )}
    </>
  );
}
