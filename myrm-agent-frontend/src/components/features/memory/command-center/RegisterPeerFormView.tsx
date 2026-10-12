/**
 * [INPUT]
 * Props: onRegister, registering
 *
 * [OUTPUT]
 * RegisterPeerFormView: Form component to register a new peer identity entity into social cognition graph.
 *
 * [POS]
 * Sub-component extracted from PeerCognitionStudioCard to maintain <400 line file limit.
 * Strict typing applied: No `any` types allowed. Accessible form with htmlFor bindings. Single file < 120 lines.
 */

import React, { useState } from 'react';
import { UserPlus } from 'lucide-react';
import type { PeerType, RegisterPeerRequest } from '@/services/memory/peerCognition';

export interface RegisterPeerFormViewProps {
  onRegister: (data: RegisterPeerRequest) => Promise<void>;
  registering?: boolean;
}

export const RegisterPeerFormView: React.FC<RegisterPeerFormViewProps> = ({
  onRegister,
  registering = false,
}) => {
  const [newPeerId, setNewPeerId] = useState<string>('');
  const [newPeerName, setNewPeerName] = useState<string>('');
  const [newPeerType, setNewPeerType] = useState<PeerType>('agent_peer');
  const [newPeerRole, setNewPeerRole] = useState<string>('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPeerId.trim() || !newPeerName.trim()) return;

    await onRegister({
      peer_id: newPeerId.trim(),
      peer_type: newPeerType,
      display_name: newPeerName.trim(),
      role_title: newPeerRole.trim(),
    });
    setNewPeerId('');
    setNewPeerName('');
    setNewPeerRole('');
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="p-4 bg-muted/30 rounded-lg border border-border space-y-4"
    >
      <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
        <UserPlus className="w-3.5 h-3.5 text-primary" />
        <span>登记新参与者 Peer 实体 (进入社会认知图谱)</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1">
          <label
            htmlFor="register-peer-id-input"
            className="text-xs font-medium text-foreground block"
          >
            参与者唯一标识 (Peer ID)
          </label>
          <input
            id="register-peer-id-input"
            type="text"
            placeholder="如 user_david, agent_qa, proj_web"
            value={newPeerId}
            onChange={(e) => setNewPeerId(e.target.value)}
            className="w-full px-2.5 py-1.5 text-xs bg-background rounded border border-input focus:outline-none focus:ring-2 focus:ring-primary text-foreground"
          />
        </div>

        <div className="space-y-1">
          <label
            htmlFor="register-peer-type-select"
            className="text-xs font-medium text-foreground block"
          >
            参与者类型 (Peer Type)
          </label>
          <select
            id="register-peer-type-select"
            value={newPeerType}
            onChange={(e) => setNewPeerType(e.target.value as PeerType)}
            className="w-full px-2.5 py-1.5 text-xs bg-background rounded border border-input focus:outline-none focus:ring-2 focus:ring-primary text-foreground"
          >
            <option value="user_peer">user_peer (自然人用户)</option>
            <option value="agent_peer">agent_peer (协作智能体)</option>
            <option value="reviewer_peer">reviewer_peer (安全/业务审查者)</option>
            <option value="project_peer">project_peer (项目/工作区实体)</option>
          </select>
        </div>

        <div className="space-y-1">
          <label
            htmlFor="register-peer-name-input"
            className="text-xs font-medium text-foreground block"
          >
            显示名称 (Display Name)
          </label>
          <input
            id="register-peer-name-input"
            type="text"
            placeholder="如 David Chen 或 QABot"
            value={newPeerName}
            onChange={(e) => setNewPeerName(e.target.value)}
            className="w-full px-2.5 py-1.5 text-xs bg-background rounded border border-input focus:outline-none focus:ring-2 focus:ring-primary text-foreground"
          />
        </div>

        <div className="space-y-1">
          <label
            htmlFor="register-peer-role-input"
            className="text-xs font-medium text-foreground block"
          >
            职能职责 / 角色头衔 (Role Title)
          </label>
          <input
            id="register-peer-role-input"
            type="text"
            placeholder="如 性能测试负责人 / 前端重构助手"
            value={newPeerRole}
            onChange={(e) => setNewPeerRole(e.target.value)}
            className="w-full px-2.5 py-1.5 text-xs bg-background rounded border border-input focus:outline-none focus:ring-2 focus:ring-primary text-foreground"
          />
        </div>
      </div>

      <div className="flex justify-end pt-2">
        <button
          type="submit"
          disabled={registering || !newPeerId.trim() || !newPeerName.trim()}
          className="flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
        >
          <UserPlus className="w-3.5 h-3.5" />
          <span>{registering ? '登记中...' : '确认登记并初始化画像卡'}</span>
        </button>
      </div>
    </form>
  );
};
