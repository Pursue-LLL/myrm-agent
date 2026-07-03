/**
 * [INPUT]
 * hooks/useAgentEditor (POS: Agent editor state & lifecycle)
 * primitives/select (POS: Shadcn select component)
 *
 * [OUTPUT]
 * AgentBrowserConfigSection: Per-agent browser configuration card
 *
 * [POS]
 * Browser config section for capabilities tab.
 * Manages browser_source, dialog_policy, session_recording (engine auto-routed by harness).
 */

'use client';

import { useTranslations } from 'next-intl';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives/select';

interface AgentBrowserConfigSectionProps {
  browserSource: string | undefined;
  onBrowserSourceChange: (value: string | undefined) => void;
  dialogPolicy: string | undefined;
  onDialogPolicyChange: (value: string | undefined) => void;
  sessionRecording: string | undefined;
  onSessionRecordingChange: (value: string | undefined) => void;
}

export function AgentBrowserConfigSection({
  browserSource,
  onBrowserSourceChange,
  dialogPolicy,
  onDialogPolicyChange,
  sessionRecording,
  onSessionRecordingChange,
}: AgentBrowserConfigSectionProps) {
  const t = useTranslations('agent');
  const tEditor = useTranslations('agent.configEditor');

  return (
    <div className="rounded-xl bg-card/60 border border-border/50 p-4 space-y-4">
      <div>
        <h4 className="text-sm font-medium text-foreground">{t('browserConfig')}</h4>
        <p className="text-xs text-muted-foreground mt-0.5">{t('browserConfigDesc')}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Browser Source */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">
            {tEditor('browserSource.label')}
          </label>
          <Select
            value={browserSource || 'auto'}
            onValueChange={(v) => onBrowserSourceChange(v === 'auto' ? undefined : v)}
          >
            <SelectTrigger className="w-full bg-background">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">
                <div className="flex flex-col py-0.5">
                  <span className="font-medium text-xs">{tEditor('browserSource.options.auto')}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {tEditor('browserSource.options.autoDesc')}
                  </span>
                </div>
              </SelectItem>
              <SelectItem value="extension">
                <div className="flex flex-col py-0.5">
                  <span className="font-medium text-xs">{tEditor('browserSource.options.extension')}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {tEditor('browserSource.options.extensionDesc')}
                  </span>
                </div>
              </SelectItem>
              <SelectItem value="launch">
                <div className="flex flex-col py-0.5">
                  <span className="font-medium text-xs">{tEditor('browserSource.options.launch')}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {tEditor('browserSource.options.launchDesc')}
                  </span>
                </div>
              </SelectItem>
              <SelectItem value="connect">
                <div className="flex flex-col py-0.5">
                  <span className="font-medium text-xs">{tEditor('browserSource.options.connect')}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {tEditor('browserSource.options.connectDesc')}
                  </span>
                </div>
              </SelectItem>
              <SelectItem value="remote">
                <div className="flex flex-col py-0.5">
                  <span className="font-medium text-xs">{tEditor('browserSource.options.remote')}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {tEditor('browserSource.options.remoteDesc')}
                  </span>
                </div>
              </SelectItem>
            </SelectContent>
          </Select>
          {browserSource === 'extension' && (
            <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-1">
              {tEditor('browserSource.extensionWarning')}
            </p>
          )}
          {browserSource === 'connect' && (
            <p className="text-[11px] text-blue-600 dark:text-blue-400 mt-1">
              {tEditor('browserSource.connectInfo')}
            </p>
          )}
          {browserSource === 'remote' && (
            <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-1">
              {tEditor('browserSource.remoteWarning')}
            </p>
          )}
        </div>

        {/* Dialog Policy */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">
            {t('dialogPolicy.label')}
          </label>
          <Select
            value={dialogPolicy || 'smart'}
            onValueChange={(v) => onDialogPolicyChange(v === 'smart' ? undefined : v)}
          >
            <SelectTrigger className="w-full bg-background">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="smart">
                <div className="flex flex-col py-0.5">
                  <span className="font-medium text-xs">{tEditor('dialogPolicy.options.smart')}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {tEditor('dialogPolicy.options.smartDesc')}
                  </span>
                </div>
              </SelectItem>
              <SelectItem value="auto_accept">
                <div className="flex flex-col py-0.5">
                  <span className="font-medium text-xs">{tEditor('dialogPolicy.options.autoAccept')}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {tEditor('dialogPolicy.options.autoAcceptDesc')}
                  </span>
                </div>
              </SelectItem>
              <SelectItem value="auto_dismiss">
                <div className="flex flex-col py-0.5">
                  <span className="font-medium text-xs">{tEditor('dialogPolicy.options.autoDismiss')}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {tEditor('dialogPolicy.options.autoDismissDesc')}
                  </span>
                </div>
              </SelectItem>
              <SelectItem value="wait_for_agent">
                <div className="flex flex-col py-0.5">
                  <span className="font-medium text-xs">{tEditor('dialogPolicy.options.waitForAgent')}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {tEditor('dialogPolicy.options.waitForAgentDesc')}
                  </span>
                </div>
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Session Recording */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">
            {t('sessionRecording.label')}
          </label>
          <Select
            value={sessionRecording || 'off'}
            onValueChange={(v) => onSessionRecordingChange(v === 'off' ? undefined : v)}
          >
            <SelectTrigger className="w-full bg-background">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="off">
                <div className="flex flex-col py-0.5">
                  <span className="font-medium text-xs">{tEditor('sessionRecording.options.off')}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {tEditor('sessionRecording.options.offDesc')}
                  </span>
                </div>
              </SelectItem>
              <SelectItem value="on_failure">
                <div className="flex flex-col py-0.5">
                  <span className="font-medium text-xs">{tEditor('sessionRecording.options.onFailure')}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {tEditor('sessionRecording.options.onFailureDesc')}
                  </span>
                </div>
              </SelectItem>
              <SelectItem value="always">
                <div className="flex flex-col py-0.5">
                  <span className="font-medium text-xs">{tEditor('sessionRecording.options.always')}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {tEditor('sessionRecording.options.alwaysDesc')}
                  </span>
                </div>
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  );
}
