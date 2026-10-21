'use client';

import React, { useState } from 'react';
import {
  X,
  Bot,
  Zap,
  Plug,
  BookOpen,
  Laptop,
  Plus,
  Check,
  Save,
  Trash2,
} from 'lucide-react';
import { useFingerprintStudioStore } from './useFingerprintStudioStore';
import { HostFingerprintBadge } from './HostFingerprintBadge';

const AVAILABLE_SKILLS = [
  { id: 'skill_git_tools', name: 'Git 自动化流', category: 'DevOps' },
  { id: 'skill_code_review', name: '代码质量巡检', category: 'Engineering' },
  { id: 'skill_cuda_profiler', name: 'CUDA 算力调优', category: 'MLOps' },
  { id: 'skill_web_scraper', name: '无头浏览器抓取', category: 'Data' },
];

const AVAILABLE_CONNECTORS = [
  { id: 'conn_github_mcp', name: 'GitHub MCP 连接器', status: 'Connected' },
  { id: 'conn_docker_pty', name: 'Docker PTY 桥接', status: 'Connected' },
  { id: 'conn_cuda_bridge', name: 'NVIDIA Driver 桥接', status: 'Active' },
  { id: 'conn_notion_sync', name: 'Notion 知识同步', status: 'Idle' },
];

const AVAILABLE_KNOWLEDGE = [
  { id: 'kb_arch_standards', name: '企业架构规范库 2026', itemsCount: 42 },
  { id: 'kb_cuda_ops', name: '显卡调度运维知识库', itemsCount: 18 },
  { id: 'kb_api_schemas', name: '全仓 OpenAPI 强契约', itemsCount: 96 },
];

export const UnifiedAgentStudioModal: React.FC = () => {
  const {
    isStudioModalOpen,
    closeStudio,
    studioAgents,
    selectedStudioAgentId,
    selectStudioAgent,
    createStudioAgent,
    updateStudioAgent,
    bindSkillToAgent,
    unbindSkillFromAgent,
    bindConnectorToAgent,
    unbindConnectorFromAgent,
    bindKnowledgeToAgent,
    unbindKnowledgeFromAgent,
    devices,
  } = useFingerprintStudioStore();

  const [activeTab, setActiveTab] = useState<'profile' | 'skills' | 'connectors' | 'knowledge'>('profile');
  const [newAgentName, setNewAgentName] = useState('');
  const [newAgentRole, setNewAgentRole] = useState('');

  if (!isStudioModalOpen) {
    return null;
  }

  const currentAgent = studioAgents.find((a) => a.id === selectedStudioAgentId) || studioAgents[0];

  const handleCreateAgent = () => {
    if (!newAgentName.trim()) {
      return;
    }
    const role = newAgentRole.trim() || 'General Specialist';
    createStudioAgent(newAgentName.trim(), role, '一站式创建的全新智能体');
    setNewAgentName('');
    setNewAgentRole('');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="flex h-[620px] w-full max-w-4xl flex-col rounded-xl border border-slate-700 bg-slate-900 shadow-2xl text-slate-200 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4 bg-slate-900/90">
          <div className="flex items-center gap-2.5">
            <Bot className="h-5 w-5 text-blue-400" />
            <div>
              <h2 className="text-base font-semibold text-slate-100">
                统一智能体工坊 (Unified Agent Studio)
              </h2>
              <p className="text-xs text-slate-400">
                收敛 Agent Profile、专属技能、外部连接器与知识库配置
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeStudio}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left Sidebar: Agent List */}
          <div className="w-64 border-r border-slate-800 bg-slate-950/40 p-3 flex flex-col">
            <div className="mb-2 flex items-center justify-between px-1">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                伙伴清单
              </span>
              <span className="text-xs text-slate-500">{studioAgents.length} 个</span>
            </div>

            <div className="flex-1 space-y-1.5 overflow-y-auto pr-1">
              {studioAgents.map((agent) => {
                const isSelected = agent.id === currentAgent?.id;
                return (
                  <button
                    key={agent.id}
                    type="button"
                    onClick={() => { selectStudioAgent(agent.id); }}
                    className={`w-full text-left p-2.5 rounded-lg border transition-all ${
                      isSelected
                        ? 'border-blue-500/50 bg-blue-500/10 text-slate-100 shadow-sm'
                        : 'border-slate-800/80 bg-slate-900/40 text-slate-300 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-xs truncate">{agent.name}</span>
                      <span className="text-[10px] px-1 py-0.5 rounded bg-slate-800 text-slate-400">
                        {agent.boundSkillIds.length} 技能
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-400 truncate mt-0.5">
                      {agent.role}
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Quick Create Bar */}
            <div className="mt-3 pt-3 border-t border-slate-800">
              <input
                type="text"
                placeholder="智能体名称..."
                value={newAgentName}
                onChange={(e) => { setNewAgentName(e.target.value); }}
                className="w-full text-xs px-2.5 py-1.5 rounded bg-slate-800 border border-slate-700 text-slate-200 placeholder:text-slate-500 mb-2 focus:outline-none focus:border-blue-500"
              />
              <button
                type="button"
                onClick={handleCreateAgent}
                className="w-full flex items-center justify-center gap-1.5 text-xs py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-white font-medium transition-colors"
              >
                <Plus className="h-3.5 w-3.5" />
                新建智能体伙伴
              </button>
            </div>
          </div>

          {/* Right Main Content */}
          {currentAgent ? (
            <div className="flex-1 flex flex-col overflow-hidden bg-slate-900/40">
              {/* Tab Navigation */}
              <div className="flex border-b border-slate-800 px-6 pt-3 gap-6 text-xs font-medium">
                <button
                  type="button"
                  onClick={() => { setActiveTab('profile'); }}
                  className={`pb-2.5 border-b-2 flex items-center gap-1.5 transition-colors ${
                    activeTab === 'profile'
                      ? 'border-blue-500 text-blue-400'
                      : 'border-transparent text-slate-400 hover:text-slate-300'
                  }`}
                >
                  <Bot className="h-4 w-4" /> 设定与宿主机
                </button>
                <button
                  type="button"
                  onClick={() => { setActiveTab('skills'); }}
                  className={`pb-2.5 border-b-2 flex items-center gap-1.5 transition-colors ${
                    activeTab === 'skills'
                      ? 'border-blue-500 text-blue-400'
                      : 'border-transparent text-slate-400 hover:text-slate-300'
                  }`}
                >
                  <Zap className="h-4 w-4" /> 专属技能 ({currentAgent.boundSkillIds.length})
                </button>
                <button
                  type="button"
                  onClick={() => { setActiveTab('connectors'); }}
                  className={`pb-2.5 border-b-2 flex items-center gap-1.5 transition-colors ${
                    activeTab === 'connectors'
                      ? 'border-blue-500 text-blue-400'
                      : 'border-transparent text-slate-400 hover:text-slate-300'
                  }`}
                >
                  <Plug className="h-4 w-4" /> 数据连接器 ({currentAgent.boundConnectorIds.length})
                </button>
                <button
                  type="button"
                  onClick={() => { setActiveTab('knowledge'); }}
                  className={`pb-2.5 border-b-2 flex items-center gap-1.5 transition-colors ${
                    activeTab === 'knowledge'
                      ? 'border-blue-500 text-blue-400'
                      : 'border-transparent text-slate-400 hover:text-slate-300'
                  }`}
                >
                  <BookOpen className="h-4 w-4" /> 专属知识库 ({currentAgent.boundKnowledgeIds.length})
                </button>
              </div>

              {/* Tab Body */}
              <div className="flex-1 overflow-y-auto p-6 space-y-4">
                {activeTab === 'profile' && (
                  <div className="space-y-4 text-xs">
                    <div>
                      <label htmlFor="agent-studio-name-input" className="block text-slate-300 font-medium mb-1.5">
                        智能体名称
                      </label>
                      <input
                        id="agent-studio-name-input"
                        type="text"
                        value={currentAgent.name}
                        onChange={(e) => {
                          updateStudioAgent(currentAgent.id, { name: e.target.value });
                        }}
                        className="w-full text-xs px-3 py-2 rounded bg-slate-800 border border-slate-700 text-slate-200 focus:outline-none focus:border-blue-500"
                      />
                    </div>

                    <div>
                      <label htmlFor="agent-studio-role-input" className="block text-slate-300 font-medium mb-1.5">
                        专业角色 (Role)
                      </label>
                      <input
                        id="agent-studio-role-input"
                        type="text"
                        value={currentAgent.role}
                        onChange={(e) => {
                          updateStudioAgent(currentAgent.id, { role: e.target.value });
                        }}
                        className="w-full text-xs px-3 py-2 rounded bg-slate-800 border border-slate-700 text-slate-200 focus:outline-none focus:border-blue-500"
                      />
                    </div>

                    <div>
                      <span className="block text-slate-300 font-medium mb-1.5">
                        绑定执行宿主机 (Physical Host / Sandbox Pod)
                      </span>
                      <div className="flex flex-wrap gap-2">
                        {devices.map((device) => {
                          const isAssigned = currentAgent.assignedHostDeviceId === device.hardware.deviceId;
                          return (
                            <button
                              key={device.hardware.deviceId}
                              type="button"
                              onClick={() => {
                                updateStudioAgent(currentAgent.id, {
                                  assignedHostDeviceId: device.hardware.deviceId,
                                });
                              }}
                              className={`p-2 rounded-lg border text-left flex items-center gap-2 transition-colors ${
                                isAssigned
                                  ? 'border-blue-500 bg-blue-500/20 text-slate-100'
                                  : 'border-slate-800 bg-slate-800/40 text-slate-400 hover:border-slate-700'
                              }`}
                            >
                              <HostFingerprintBadge device={device} mode="mini" />
                              {isAssigned && <Check className="h-3.5 w-3.5 text-blue-400" />}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                )}

                {activeTab === 'skills' && (
                  <div className="space-y-2.5">
                    {AVAILABLE_SKILLS.map((skill) => {
                      const isBound = currentAgent.boundSkillIds.includes(skill.id);
                      return (
                        <div
                          key={skill.id}
                          className="flex items-center justify-between p-3 rounded-lg border border-slate-800 bg-slate-800/40 text-xs"
                        >
                          <div>
                            <div className="font-medium text-slate-200">{skill.name}</div>
                            <div className="text-[11px] text-slate-400">{skill.category}</div>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              if (isBound) {
                                unbindSkillFromAgent(currentAgent.id, skill.id);
                              } else {
                                bindSkillToAgent(currentAgent.id, skill.id);
                              }
                            }}
                            className={`px-2.5 py-1 rounded font-medium transition-colors ${
                              isBound
                                ? 'bg-red-500/20 text-red-300 border border-red-500/30 hover:bg-red-500/30'
                                : 'bg-blue-600 hover:bg-blue-500 text-white'
                            }`}
                          >
                            {isBound ? '解绑技能' : '挂载技能'}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}

                {activeTab === 'connectors' && (
                  <div className="space-y-2.5">
                    {AVAILABLE_CONNECTORS.map((conn) => {
                      const isBound = currentAgent.boundConnectorIds.includes(conn.id);
                      return (
                        <div
                          key={conn.id}
                          className="flex items-center justify-between p-3 rounded-lg border border-slate-800 bg-slate-800/40 text-xs"
                        >
                          <div>
                            <div className="font-medium text-slate-200">{conn.name}</div>
                            <div className="text-[11px] text-slate-400">状态: {conn.status}</div>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              if (isBound) {
                                unbindConnectorFromAgent(currentAgent.id, conn.id);
                              } else {
                                bindConnectorToAgent(currentAgent.id, conn.id);
                              }
                            }}
                            className={`px-2.5 py-1 rounded font-medium transition-colors ${
                              isBound
                                ? 'bg-red-500/20 text-red-300 border border-red-500/30 hover:bg-red-500/30'
                                : 'bg-blue-600 hover:bg-blue-500 text-white'
                            }`}
                          >
                            {isBound ? '断开连接' : '授权挂载'}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}

                {activeTab === 'knowledge' && (
                  <div className="space-y-2.5">
                    {AVAILABLE_KNOWLEDGE.map((kb) => {
                      const isBound = currentAgent.boundKnowledgeIds.includes(kb.id);
                      return (
                        <div
                          key={kb.id}
                          className="flex items-center justify-between p-3 rounded-lg border border-slate-800 bg-slate-800/40 text-xs"
                        >
                          <div>
                            <div className="font-medium text-slate-200">{kb.name}</div>
                            <div className="text-[11px] text-slate-400">收录 {kb.itemsCount} 条知识实体</div>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              if (isBound) {
                                unbindKnowledgeFromAgent(currentAgent.id, kb.id);
                              } else {
                                bindKnowledgeToAgent(currentAgent.id, kb.id);
                              }
                            }}
                            className={`px-2.5 py-1 rounded font-medium transition-colors ${
                              isBound
                                ? 'bg-red-500/20 text-red-300 border border-red-500/30 hover:bg-red-500/30'
                                : 'bg-blue-600 hover:bg-blue-500 text-white'
                            }`}
                          >
                            {isBound ? '移除挂载' : '关联知识库'}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-xs text-slate-500">
              请选择或创建一个智能体
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
