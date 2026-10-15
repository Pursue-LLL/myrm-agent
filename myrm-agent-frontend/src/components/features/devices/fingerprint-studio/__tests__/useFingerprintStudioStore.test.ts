import { describe, it, expect, beforeEach } from 'vitest';
import { useFingerprintStudioStore } from '../useFingerprintStudioStore';
import { HostDevice } from '../fingerprintStudioTypes';

describe('useFingerprintStudioStore', () => {
  beforeEach(() => {
    useFingerprintStudioStore.getState().resetAll();
  });

  it('initializes with default devices and studio agents', () => {
    const state = useFingerprintStudioStore.getState();
    expect(state.devices.length).toBeGreaterThanOrEqual(3);
    expect(state.activeDeviceId).toBe('host_mac_m3');
    expect(state.studioAgents.length).toBeGreaterThanOrEqual(2);
    expect(state.enterpriseMode).toBe(true);
  });

  it('switches active device and registers a new device', () => {
    const store = useFingerprintStudioStore.getState();
    store.setActiveDevice('host_win_rtx');
    expect(useFingerprintStudioStore.getState().activeDeviceId).toBe('host_win_rtx');

    const newDevice: HostDevice = {
      hardware: {
        deviceId: 'host_edge_pi',
        hostName: 'Edge-RaspberryPi',
        platform: 'linux',
        architecture: 'arm64_pod',
        chipModel: 'BCM2711',
        kind: 'local_workstation',
        isCurrentHost: false,
      },
      telemetry: {
        cpuUsagePct: 10,
        memoryUsagePct: 20,
        activeTasksCount: 0,
        lastHeartbeatMs: Date.now(),
        latencyMs: 1,
      },
      status: 'online',
    };

    store.registerDevice(newDevice);
    const updatedDevices = useFingerprintStudioStore.getState().devices;
    expect(updatedDevices.some((d) => d.hardware.deviceId === 'host_edge_pi')).toBe(true);
  });

  it('updates device telemetry and auto-recomputes health status', () => {
    const store = useFingerprintStudioStore.getState();
    store.updateDeviceTelemetry('host_mac_m3', {
      cpuUsagePct: 95,
      memoryUsagePct: 90,
      activeTasksCount: 4,
    });

    const macDevice = useFingerprintStudioStore
      .getState()
      .devices.find((d) => d.hardware.deviceId === 'host_mac_m3');
    expect(macDevice).toBeDefined();
    expect(macDevice?.telemetry.cpuUsagePct).toBe(95);
    expect(macDevice?.status).toBe('busy');
  });

  it('supports unified creation and four-dimensional asset binding for agents', () => {
    const store = useFingerprintStudioStore.getState();
    const newAgentId = store.createStudioAgent('数据清洗专员', 'Data Engineer', '处理离线清洗任务');

    expect(newAgentId).toBeDefined();
    let currentAgent = useFingerprintStudioStore
      .getState()
      .studioAgents.find((a) => a.id === newAgentId);
    expect(currentAgent?.name).toBe('数据清洗专员');
    expect(currentAgent?.boundSkillIds).toEqual([]);

    // 绑定技能
    store.bindSkillToAgent(newAgentId, 'skill_data_cleaner');
    currentAgent = useFingerprintStudioStore
      .getState()
      .studioAgents.find((a) => a.id === newAgentId);
    expect(currentAgent?.boundSkillIds).toContain('skill_data_cleaner');

    // 解绑技能
    store.unbindSkillFromAgent(newAgentId, 'skill_data_cleaner');
    currentAgent = useFingerprintStudioStore
      .getState()
      .studioAgents.find((a) => a.id === newAgentId);
    expect(currentAgent?.boundSkillIds).not.toContain('skill_data_cleaner');

    // 绑定/解绑连接器
    store.bindConnectorToAgent(newAgentId, 'conn_s3_lake');
    currentAgent = useFingerprintStudioStore
      .getState()
      .studioAgents.find((a) => a.id === newAgentId);
    expect(currentAgent?.boundConnectorIds).toContain('conn_s3_lake');

    store.unbindConnectorFromAgent(newAgentId, 'conn_s3_lake');
    currentAgent = useFingerprintStudioStore
      .getState()
      .studioAgents.find((a) => a.id === newAgentId);
    expect(currentAgent?.boundConnectorIds).not.toContain('conn_s3_lake');

    // 绑定/解绑知识库
    store.bindKnowledgeToAgent(newAgentId, 'kb_warehouse_schema');
    currentAgent = useFingerprintStudioStore
      .getState()
      .studioAgents.find((a) => a.id === newAgentId);
    expect(currentAgent?.boundKnowledgeIds).toContain('kb_warehouse_schema');

    store.unbindKnowledgeFromAgent(newAgentId, 'kb_warehouse_schema');
    currentAgent = useFingerprintStudioStore
      .getState()
      .studioAgents.find((a) => a.id === newAgentId);
    expect(currentAgent?.boundKnowledgeIds).not.toContain('kb_warehouse_schema');
  });

  it('handles full-modality call lifecycle with enterprise audit compliance', () => {
    const store = useFingerprintStudioStore.getState();
    expect(store.callSession.state).toBe('idle');

    // 启动通话 (企业模式下自动记录审计)
    store.startCall('agent_fullstack', '全栈架构专家');
    let session = useFingerprintStudioStore.getState().callSession;
    expect(session.state).toBe('active');
    expect(session.agentName).toBe('全栈架构专家');

    let audits = useFingerprintStudioStore.getState().auditTrails;
    expect(audits.length).toBe(1);
    expect(audits[0].event).toBe('call_started');

    // 静音切换
    store.toggleMute();
    expect(useFingerprintStudioStore.getState().callSession.isMuted).toBe(true);

    // 扬声器切换
    store.toggleSpeaker();
    expect(useFingerprintStudioStore.getState().callSession.isSpeakerOn).toBe(false);

    // 屏幕共享切换
    store.toggleScreenShare();
    session = useFingerprintStudioStore.getState().callSession;
    expect(session.isScreenSharing).toBe(true);
    expect(session.state).toBe('screen_sharing');

    audits = useFingerprintStudioStore.getState().auditTrails;
    expect(audits.length).toBe(2);
    expect(audits[0].event).toBe('screen_share_toggled');

    // 挂断通话
    store.endCall();
    session = useFingerprintStudioStore.getState().callSession;
    expect(session.state).toBe('ended');

    audits = useFingerprintStudioStore.getState().auditTrails;
    expect(audits.length).toBe(3);
    expect(audits[0].event).toBe('call_ended');
  });

  it('supports personal mode without creating enterprise audit trail', () => {
    const store = useFingerprintStudioStore.getState();
    store.setEnterpriseMode(false);

    store.startCall('agent_solo', '单机伙伴');
    expect(useFingerprintStudioStore.getState().callSession.state).toBe('active');
    expect(useFingerprintStudioStore.getState().auditTrails.length).toBe(0);

    store.toggleScreenShare();
    expect(useFingerprintStudioStore.getState().auditTrails.length).toBe(0);

    store.endCall();
    expect(useFingerprintStudioStore.getState().callSession.state).toBe('ended');
    expect(useFingerprintStudioStore.getState().auditTrails.length).toBe(0);
  });
});
