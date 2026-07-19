'use client';

import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import AgentConfigCards from '@/components/features/chat-window/agent-config-panel/AgentConfigCards';
import { AgentOpenAPIServicesTab } from './AgentOpenAPIServicesTab';
import { AgentSubagentBinding } from './AgentSubagentBinding';
import { AgentSharedContextBinding } from './AgentSharedContextBinding';
import { AgentNotifyTargets } from './AgentNotifyTargets';
import { AgentBrowserConfigSection } from './AgentBrowserConfigSection';
import {
  ModelBindingSection,
  ModelParamsSection,
  RoutingOverrideSection,
  MaxIterationsSection,
  WorkspacePolicySection,
  ParallelFissionSection,
  AdvancedEngineParamsSection,
  ConsensusSection,
  SessionPolicySection,
  DeliveryAssuranceSection,
} from './AgentCapabilitiesTabSections';
import type { ConfigCardType } from '@/components/features/chat-window/agent-config-panel/AgentConfigCards';
import type {
  AgentModelSelection,
  AgentSessionPolicy,
  OpenAPIServiceConfig,
  NotifyTarget,
  WorkspacePolicy,
} from '@/services/agent';
import type { Skill } from '@/store/skill/types';
import type { MCPServiceConfig } from '@/store/config/types';
import type { BuiltinToolId } from '@/store/chat/types';

export interface AgentCapabilitiesTabProps {
  editor: {
    modelSelection: AgentModelSelection | null;
    setModelSelection: (val: AgentModelSelection) => void;
    maxIterations: number | null;
    setMaxIterations: (val: number | null) => void;
    workspacePolicy: WorkspacePolicy;
    setWorkspacePolicy: (val: WorkspacePolicy) => void;
    engineParams: Record<string, unknown> | null;
    setEngineParams: (val: Record<string, unknown>) => void;
    browserSource?: string;
    setBrowserSource: (val: string | undefined) => void;
    dialogPolicy?: string;
    setDialogPolicy: (val: string | undefined) => void;
    sessionRecording?: string;
    setSessionRecording: (val: string | undefined) => void;
    sessionPolicy: AgentSessionPolicy | null;
    setSessionPolicy: (val: AgentSessionPolicy | null) => void;
    cronPostRunVerify: boolean;
    setCronPostRunVerify: (val: boolean) => void;
    selectedSkillDetails: Skill[];
    selectedMcpDetails: MCPServiceConfig[];
    systemPrompt: string;
    useGlobalInstruction: boolean;
    enabledBuiltinTools: BuiltinToolId[];
    isReadonly: boolean;
    setEditDialogType: (type: ConfigCardType) => void;
    setEditDialogOpen: (open: boolean) => void;
    openapiServices: OpenAPIServiceConfig[];
    setOpenapiServices: (val: OpenAPIServiceConfig[]) => void;
    selectedSubagentIds: string[];
    setSelectedSubagentIds: (val: string[]) => void;
    subagentRebindHint: boolean;
    dismissSubagentRebindHint: () => void;
    notifyTargets: NotifyTarget[];
    setNotifyTargets: (val: NotifyTarget[]) => void;
  };
  agentId: string | null;
  isNew: boolean;
}

export function AgentCapabilitiesTab({ editor, agentId, isNew }: AgentCapabilitiesTabProps) {
  const t = useTranslations();

  return (
    <div
      className={cn(
        'space-y-4',
        'animate-in fade-in-50 duration-300',
        editor.isReadonly && 'pointer-events-none opacity-70',
      )}
    >
      <ModelBindingSection editor={editor} t={t} />
      {editor.modelSelection && <ModelParamsSection editor={editor} t={t} />}
      {editor.modelSelection && <RoutingOverrideSection editor={editor} t={t} />}
      <MaxIterationsSection editor={editor} t={t} />
      <WorkspacePolicySection editor={editor} t={t} />
      <ParallelFissionSection editor={editor} t={t} />
      <AdvancedEngineParamsSection editor={editor} t={t} />
      <ConsensusSection editor={editor} t={t} />

      <AgentBrowserConfigSection
        browserSource={editor.browserSource}
        onBrowserSourceChange={editor.setBrowserSource}
        dialogPolicy={editor.dialogPolicy}
        onDialogPolicyChange={editor.setDialogPolicy}
        sessionRecording={editor.sessionRecording}
        onSessionRecordingChange={editor.setSessionRecording}
      />

      <DeliveryAssuranceSection editor={editor} t={t} />

      <SessionPolicySection editor={editor} t={t} />

      <AgentConfigCards
        selectedSkills={editor.selectedSkillDetails}
        selectedMcps={editor.selectedMcpDetails}
        systemPrompt={editor.systemPrompt}
        useGlobalInstruction={editor.useGlobalInstruction}
        enabledBuiltinTools={editor.enabledBuiltinTools}
        onCardClick={(type) => {
          if (editor.isReadonly) return;
          editor.setEditDialogType(type);
          editor.setEditDialogOpen(true);
        }}
      />

      <AgentOpenAPIServicesTab
        services={editor.openapiServices}
        onChange={editor.setOpenapiServices}
        readonly={editor.isReadonly}
      />

      <AgentSubagentBinding
        selectedIds={editor.selectedSubagentIds}
        currentAgentId={agentId}
        onChange={editor.setSelectedSubagentIds}
        showRebindHint={editor.subagentRebindHint}
        onDismissRebindHint={editor.dismissSubagentRebindHint}
      />

      <AgentSharedContextBinding agentId={agentId} isNew={isNew} />

      <AgentNotifyTargets
        targets={editor.notifyTargets}
        onChange={editor.setNotifyTargets}
        readonly={editor.isReadonly}
      />
    </div>
  );
}

