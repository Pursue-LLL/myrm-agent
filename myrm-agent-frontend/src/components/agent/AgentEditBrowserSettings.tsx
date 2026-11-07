'use client';

/**
 * [INPUT] ./DescribedSelectItem (POS: 带说明行的下拉选项), ./agentEditFormModel::AgentExtraFields (POS: 非 react-hook-form 字段模型)
 * [OUTPUT] AgentEditBrowserSettings: 浏览器来源、弹窗处理与会话录制三个策略下拉（含扩展 / 云浏览器风险提示）
 * [POS] 智能体创建 / 编辑表单的浏览器区段。
 */

import { AlertCircle } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { DescribedSelectItem } from '@/components/agent/DescribedSelectItem';
import type { AgentExtraFields } from '@/components/agent/agentEditFormModel';

interface AgentEditBrowserSettingsProps {
  value: Pick<AgentExtraFields, 'browserSource' | 'dialogPolicy' | 'sessionRecording'>;
  onChange: (patch: Partial<AgentExtraFields>) => void;
}

export function AgentEditBrowserSettings({ value, onChange }: AgentEditBrowserSettingsProps) {
  const t = useTranslations('Agent');
  const { browserSource, dialogPolicy, sessionRecording } = value;

  return (
    <div className="space-y-3 rounded-lg border border-border/60 p-4">
      <div className="space-y-2 pt-2">
        <Label className="text-sm font-medium">{t('form.browserSource')}</Label>
        <Select value={browserSource} onValueChange={(next) => onChange({ browserSource: next })}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <DescribedSelectItem
              value="auto"
              label={t('form.browserSourceAuto')}
              description={t('form.browserSourceAutoDesc')}
            />
            <DescribedSelectItem
              value="extension"
              label={t('form.browserSourceExtension')}
              description={t('form.browserSourceExtensionDesc')}
            />
            <DescribedSelectItem
              value="launch"
              label={t('form.browserSourceLaunch')}
              description={t('form.browserSourceLaunchDesc')}
            />
            <DescribedSelectItem
              value="connect"
              label={t('form.browserSourceConnect')}
              description={t('form.browserSourceConnectDesc')}
            />
            <DescribedSelectItem
              value="remote"
              label={t('form.browserSourceRemote')}
              description={t('form.browserSourceRemoteDesc')}
            />
          </SelectContent>
        </Select>
        {browserSource === 'extension' && (
          <p className="text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1">
            <AlertCircle size={12} />
            {t('form.browserSourceExtensionWarning')}
          </p>
        )}
        {browserSource === 'connect' && (
          <p className="text-xs text-blue-600 dark:text-blue-400 flex items-center gap-1">
            <AlertCircle size={12} />
            {t('form.browserSourceConnectInfo')}
          </p>
        )}
        {browserSource === 'remote' && (
          <p className="text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1">
            <AlertCircle size={12} />
            {t('form.browserSourceRemoteWarning')}
          </p>
        )}
      </div>

      <div className="space-y-2 pt-2">
        <Label className="text-sm font-medium">{t('form.dialogPolicy')}</Label>
        <Select value={dialogPolicy} onValueChange={(next) => onChange({ dialogPolicy: next })}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <DescribedSelectItem
              value="smart"
              label={t('form.dialogPolicySmart')}
              description={t('form.dialogPolicySmartDesc')}
            />
            <DescribedSelectItem
              value="auto_accept"
              label={t('form.dialogPolicyAutoAccept')}
              description={t('form.dialogPolicyAutoAcceptDesc')}
            />
            <DescribedSelectItem
              value="auto_dismiss"
              label={t('form.dialogPolicyAutoDismiss')}
              description={t('form.dialogPolicyAutoDismissDesc')}
            />
            <DescribedSelectItem
              value="wait_for_agent"
              label={t('form.dialogPolicyWaitForAgent')}
              description={t('form.dialogPolicyWaitForAgentDesc')}
            />
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2 pt-2">
        <Label className="text-sm font-medium">{t('form.sessionRecording')}</Label>
        <Select value={sessionRecording} onValueChange={(next) => onChange({ sessionRecording: next })}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <DescribedSelectItem
              value="off"
              label={t('form.sessionRecordingOff')}
              description={t('form.sessionRecordingOffDesc')}
            />
            <DescribedSelectItem
              value="on_failure"
              label={t('form.sessionRecordingOnFailure')}
              description={t('form.sessionRecordingOnFailureDesc')}
            />
            <DescribedSelectItem
              value="always"
              label={t('form.sessionRecordingAlways')}
              description={t('form.sessionRecordingAlwaysDesc')}
            />
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
