import { create } from 'zustand';
import {
  HostDevice,
  StudioAgentAsset,
  ModalityCallSession,
  EnterpriseAuditTrail,
  HostTelemetry,
} from './fingerprintStudioTypes';
import {
  computeDeviceHealth,
  createEnterpriseAuditRecord,
} from './deviceFingerprintEngine';

export interface FingerprintStudioState {
  devices: HostDevice[];
  activeDeviceId: string;
  studioAgents: StudioAgentAsset[];
  selectedStudioAgentId: string | null;
  isStudioModalOpen: boolean;
  callSession: ModalityCallSession;
  enterpriseMode: boolean;
  auditTrails: EnterpriseAuditTrail[];

  // Actions
  setActiveDevice: (deviceId: string) => void;
  updateDeviceTelemetry: (deviceId: string, patch: Partial<HostTelemetry>) => void;
  registerDevice: (device: HostDevice) => void;
  openStudio: (agentId?: string) => void;
  closeStudio: () => void;
  selectStudioAgent: (agentId: string | null) => void;
  createStudioAgent: (name: string, role: string, description: string) => string;
  updateStudioAgent: (id: string, patch: Partial<StudioAgentAsset>) => void;
  bindSkillToAgent: (agentId: string, skillId: string) => void;
  unbindSkillFromAgent: (agentId: string, skillId: string) => void;
  bindConnectorToAgent: (agentId: string, connectorId: string) => void;
  unbindConnectorFromAgent: (agentId: string, connectorId: string) => void;
  bindKnowledgeToAgent: (agentId: string, knowledgeId: string) => void;
  unbindKnowledgeFromAgent: (agentId: string, knowledgeId: string) => void;
  startCall: (agentId: string, agentName: string) => void;
  toggleMute: () => void;
  toggleSpeaker: () => void;
  toggleScreenShare: () => void;
  endCall: () => void;
  setEnterpriseMode: (enabled: boolean) => void;
  resetAll: () => void;
}

const DEFAULT_DEVICES: HostDevice[] = [
  {
    hardware: {
      deviceId: 'host_mac_m3',
      hostName: 'MacBook Pro 16"',
      platform: 'macos',
      architecture: 'apple_silicon',
      chipModel: 'Apple M3 Max (16C/40G)',
      kind: 'local_laptop',
      isCurrentHost: true,
    },
    telemetry: {
      cpuUsagePct: 24,
      memoryUsagePct: 42,
      gpuUsagePct: 15,
      activeTasksCount: 1,
      lastHeartbeatMs: Date.now(),
      latencyMs: 2,
    },
    status: 'busy',
  },
  {
    hardware: {
      deviceId: 'host_win_rtx',
      hostName: 'Workstation Rig',
      platform: 'windows',
      architecture: 'amd_x64',
      chipModel: 'Ryzen 9 7950X',
      gpuModel: 'NVIDIA RTX 4090 24GB',
      kind: 'local_workstation',
      isCurrentHost: false,
    },
    telemetry: {
      cpuUsagePct: 12,
      memoryUsagePct: 35,
      gpuUsagePct: 8,
      activeTasksCount: 0,
      lastHeartbeatMs: Date.now(),
      latencyMs: 14,
    },
    status: 'online',
  },
  {
    hardware: {
      deviceId: 'host_cloud_pod_04',
      hostName: 'Sandbox-Pod-04',
      platform: 'linux',
      architecture: 'arm64_pod',
      chipModel: 'K8s Isolated Node',
      kind: 'cloud_pod',
      isCurrentHost: false,
    },
    telemetry: {
      cpuUsagePct: 5,
      memoryUsagePct: 18,
      gpuUsagePct: 0,
      activeTasksCount: 0,
      lastHeartbeatMs: Date.now(),
      latencyMs: 38,
    },
    status: 'idle',
  },
];

const DEFAULT_AGENTS: StudioAgentAsset[] = [
  {
    id: 'agent_fullstack',
    name: '全栈架构专家',
    role: 'Staff Architect',
    description: '负责复杂系统设计、多模块协同与代码审查',
    systemPrompt: '你是一名世界顶级的软件架构师...',
    boundSkillIds: ['skill_git_tools', 'skill_code_review'],
    boundConnectorIds: ['conn_github_mcp', 'conn_docker_pty'],
    boundKnowledgeIds: ['kb_arch_standards'],
    assignedHostDeviceId: 'host_mac_m3',
    updatedAtMs: Date.now(),
  },
  {
    id: 'agent_ml_engineer',
    name: '重训调度助手',
    role: 'ML Ops Engine',
    description: '负责大模型微调、权重转换与高负载矩阵计算',
    systemPrompt: '你是高负载深度学习与任务调度专家...',
    boundSkillIds: ['skill_cuda_profiler'],
    boundConnectorIds: ['conn_cuda_bridge'],
    boundKnowledgeIds: ['kb_cuda_ops'],
    assignedHostDeviceId: 'host_win_rtx',
    updatedAtMs: Date.now(),
  },
];

const INITIAL_CALL_SESSION: ModalityCallSession = {
  sessionId: '',
  agentId: '',
  agentName: '',
  state: 'idle',
  isMuted: false,
  isSpeakerOn: true,
  isScreenSharing: false,
  durationSeconds: 0,
  enterpriseAuditEnabled: true,
  orgId: 'org-enterprise-corp',
};

export const useFingerprintStudioStore = create<FingerprintStudioState>((set, get) => ({
  devices: DEFAULT_DEVICES,
  activeDeviceId: 'host_mac_m3',
  studioAgents: DEFAULT_AGENTS,
  selectedStudioAgentId: 'agent_fullstack',
  isStudioModalOpen: false,
  callSession: INITIAL_CALL_SESSION,
  enterpriseMode: true,
  auditTrails: [],

  setActiveDevice: (deviceId: string) => {
    set({ activeDeviceId: deviceId });
  },

  updateDeviceTelemetry: (deviceId: string, patch: Partial<HostTelemetry>) => {
    set((state) => {
      const updatedDevices = state.devices.map((dev) => {
        if (dev.hardware.deviceId !== deviceId) {
          return dev;
        }
        const newTelemetry: HostTelemetry = { ...dev.telemetry, ...patch, lastHeartbeatMs: Date.now() };
        const health = computeDeviceHealth(newTelemetry);
        return {
          ...dev,
          telemetry: newTelemetry,
          status: health.status,
        };
      });
      return { devices: updatedDevices };
    });
  },

  registerDevice: (device: HostDevice) => {
    set((state) => {
      const exists = state.devices.some((d) => d.hardware.deviceId === device.hardware.deviceId);
      if (exists) {
        return {
          devices: state.devices.map((d) =>
            d.hardware.deviceId === device.hardware.deviceId ? device : d
          ),
        };
      }
      return { devices: [...state.devices, device] };
    });
  },

  openStudio: (agentId?: string) => {
    set((state) => ({
      isStudioModalOpen: true,
      selectedStudioAgentId: agentId || state.selectedStudioAgentId || state.studioAgents[0]?.id || null,
    }));
  },

  closeStudio: () => {
    set({ isStudioModalOpen: false });
  },

  selectStudioAgent: (agentId: string | null) => {
    set({ selectedStudioAgentId: agentId });
  },

  createStudioAgent: (name: string, role: string, description: string) => {
    const id = `agent_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
    const newAgent: StudioAgentAsset = {
      id,
      name,
      role,
      description,
      systemPrompt: '你是全能智能体伙伴...',
      boundSkillIds: [],
      boundConnectorIds: [],
      boundKnowledgeIds: [],
      assignedHostDeviceId: get().activeDeviceId,
      updatedAtMs: Date.now(),
    };
    set((state) => ({
      studioAgents: [newAgent, ...state.studioAgents],
      selectedStudioAgentId: id,
    }));
    return id;
  },

  updateStudioAgent: (id: string, patch: Partial<StudioAgentAsset>) => {
    set((state) => ({
      studioAgents: state.studioAgents.map((agent) => {
        if (agent.id !== id) {
          return agent;
        }
        return { ...agent, ...patch, updatedAtMs: Date.now() };
      }),
    }));
  },

  bindSkillToAgent: (agentId: string, skillId: string) => {
    set((state) => ({
      studioAgents: state.studioAgents.map((agent) => {
        if (agent.id !== agentId || agent.boundSkillIds.includes(skillId)) {
          return agent;
        }
        return {
          ...agent,
          boundSkillIds: [...agent.boundSkillIds, skillId],
          updatedAtMs: Date.now(),
        };
      }),
    }));
  },

  unbindSkillFromAgent: (agentId: string, skillId: string) => {
    set((state) => ({
      studioAgents: state.studioAgents.map((agent) => {
        if (agent.id !== agentId) {
          return agent;
        }
        return {
          ...agent,
          boundSkillIds: agent.boundSkillIds.filter((id) => id !== skillId),
          updatedAtMs: Date.now(),
        };
      }),
    }));
  },

  bindConnectorToAgent: (agentId: string, connectorId: string) => {
    set((state) => ({
      studioAgents: state.studioAgents.map((agent) => {
        if (agent.id !== agentId || agent.boundConnectorIds.includes(connectorId)) {
          return agent;
        }
        return {
          ...agent,
          boundConnectorIds: [...agent.boundConnectorIds, connectorId],
          updatedAtMs: Date.now(),
        };
      }),
    }));
  },

  unbindConnectorFromAgent: (agentId: string, connectorId: string) => {
    set((state) => ({
      studioAgents: state.studioAgents.map((agent) => {
        if (agent.id !== agentId) {
          return agent;
        }
        return {
          ...agent,
          boundConnectorIds: agent.boundConnectorIds.filter((id) => id !== connectorId),
          updatedAtMs: Date.now(),
        };
      }),
    }));
  },

  bindKnowledgeToAgent: (agentId: string, knowledgeId: string) => {
    set((state) => ({
      studioAgents: state.studioAgents.map((agent) => {
        if (agent.id !== agentId || agent.boundKnowledgeIds.includes(knowledgeId)) {
          return agent;
        }
        return {
          ...agent,
          boundKnowledgeIds: [...agent.boundKnowledgeIds, knowledgeId],
          updatedAtMs: Date.now(),
        };
      }),
    }));
  },

  unbindKnowledgeFromAgent: (agentId: string, knowledgeId: string) => {
    set((state) => ({
      studioAgents: state.studioAgents.map((agent) => {
        if (agent.id !== agentId) {
          return agent;
        }
        return {
          ...agent,
          boundKnowledgeIds: agent.boundKnowledgeIds.filter((id) => id !== knowledgeId),
          updatedAtMs: Date.now(),
        };
      }),
    }));
  },

  startCall: (agentId: string, agentName: string) => {
    const sessionId = `call_${Date.now()}`;
    const newSession: ModalityCallSession = {
      sessionId,
      agentId,
      agentName,
      state: 'active',
      isMuted: false,
      isSpeakerOn: true,
      isScreenSharing: false,
      durationSeconds: 0,
      enterpriseAuditEnabled: get().enterpriseMode,
      orgId: get().enterpriseMode ? 'org-enterprise-corp' : undefined,
    };

    let newAudits = get().auditTrails;
    if (get().enterpriseMode) {
      const audit = createEnterpriseAuditRecord(newSession, 'call_started');
      newAudits = [audit, ...newAudits];
    }

    set({ callSession: newSession, auditTrails: newAudits });
  },

  toggleMute: () => {
    set((state) => ({
      callSession: {
        ...state.callSession,
        isMuted: !state.callSession.isMuted,
      },
    }));
  },

  toggleSpeaker: () => {
    set((state) => ({
      callSession: {
        ...state.callSession,
        isSpeakerOn: !state.callSession.isSpeakerOn,
      },
    }));
  },

  toggleScreenShare: () => {
    const current = get().callSession;
    const nextSharing = !current.isScreenSharing;
    const nextState = nextSharing ? 'screen_sharing' : 'active';
    const updatedSession: ModalityCallSession = {
      ...current,
      isScreenSharing: nextSharing,
      state: nextState,
    };

    let newAudits = get().auditTrails;
    if (get().enterpriseMode) {
      const audit = createEnterpriseAuditRecord(updatedSession, 'screen_share_toggled');
      newAudits = [audit, ...newAudits];
    }

    set({ callSession: updatedSession, auditTrails: newAudits });
  },

  endCall: () => {
    const current = get().callSession;
    let newAudits = get().auditTrails;
    if (get().enterpriseMode && current.sessionId) {
      const audit = createEnterpriseAuditRecord(current, 'call_ended');
      newAudits = [audit, ...newAudits];
    }

    set({
      callSession: { ...INITIAL_CALL_SESSION, state: 'ended' },
      auditTrails: newAudits,
    });
  },

  setEnterpriseMode: (enabled: boolean) => {
    set({ enterpriseMode: enabled });
  },

  resetAll: () => {
    set({
      devices: DEFAULT_DEVICES,
      activeDeviceId: 'host_mac_m3',
      studioAgents: DEFAULT_AGENTS,
      selectedStudioAgentId: 'agent_fullstack',
      isStudioModalOpen: false,
      callSession: INITIAL_CALL_SESSION,
      enterpriseMode: true,
      auditTrails: [],
    });
  },
}));
