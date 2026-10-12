/**
 * [INPUT]
 * Props: peers, onAddEdge, onCancel
 *
 * [OUTPUT]
 * AddRelationEdgeForm: Drawer/Inline form to insert a new directed relationship edge into the social cognition graph.
 *
 * [POS]
 * Sub-component extracted from PeerEntityGraphExplorerView to maintain <400 line file limit.
 * Strict typing applied: No `any` types allowed. Accessible form with htmlFor bindings. Single file < 150 lines.
 */

import React, { useState } from 'react';
import { GitFork } from 'lucide-react';
import type {
  AddRelationEdgeRequest,
  PeerIdentityDTO,
  PeerRelationKind,
} from '@/services/memory/peerCognition';

export interface AddRelationEdgeFormProps {
  peers: PeerIdentityDTO[];
  onAddEdge: (request: AddRelationEdgeRequest) => Promise<void>;
  onCancel: () => void;
}

export const AddRelationEdgeForm: React.FC<AddRelationEdgeFormProps> = ({
  peers,
  onAddEdge,
  onCancel,
}) => {
  const [sourcePeerId, setSourcePeerId] = useState<string>(peers[0]?.peer_id || 'user_alice');
  const [relationKind, setRelationKind] = useState<PeerRelationKind>('asserts');
  const [targetEntityId, setTargetEntityId] = useState<string>('fact_use_fastapi_pydantic');
  const [targetIsPeer, setTargetIsPeer] = useState<boolean>(false);
  const [contextNote, setContextNote] = useState<string>('明确全栈架构与强类型规范约束');
  const [submitting, setSubmitting] = useState<boolean>(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sourcePeerId || !targetEntityId.trim()) return;

    setSubmitting(true);
    try {
      await onAddEdge({
        edge_id: `edge_${Date.now()}`,
        source_peer_id: sourcePeerId,
        target_entity_id: targetEntityId.trim(),
        target_is_peer: targetIsPeer,
        relation_kind: relationKind,
        context_note: contextNote.trim(),
        weight: 1.0,
      });
      onCancel();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="p-4 bg-muted/30 rounded-lg border border-border space-y-3"
    >
      <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
        <GitFork className="w-3.5 h-3.5 text-primary" />
        <span>建立社会认知语义关系边 (打破无主体孤立记忆)</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="space-y-1">
          <label
            htmlFor="edge-source-peer-select"
            className="text-xs font-medium text-muted-foreground block"
          >
            主体参与者 (Source Peer)
          </label>
          <select
            id="edge-source-peer-select"
            value={sourcePeerId}
            onChange={(e) => setSourcePeerId(e.target.value)}
            className="w-full px-2.5 py-1.5 text-xs bg-background rounded border border-input focus:outline-none focus:ring-2 focus:ring-primary text-foreground"
          >
            {peers.map((p) => (
              <option key={p.peer_id} value={p.peer_id}>
                {p.display_name} ({p.peer_id})
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1">
          <label
            htmlFor="edge-relation-kind-select"
            className="text-xs font-medium text-muted-foreground block"
          >
            语义关系动词 (Relation Kind)
          </label>
          <select
            id="edge-relation-kind-select"
            value={relationKind}
            onChange={(e) => setRelationKind(e.target.value as PeerRelationKind)}
            className="w-full px-2.5 py-1.5 text-xs bg-background rounded border border-input focus:outline-none focus:ring-2 focus:ring-primary text-foreground"
          >
            <option value="asserts">asserts (主张/提出结论)</option>
            <option value="approves">approves (审查/合规批准)</option>
            <option value="collaborates_with">collaborates_with (结对协作)</option>
            <option value="governs">governs (规则管辖与约束)</option>
            <option value="depends_on">depends_on (强依赖实体)</option>
          </select>
        </div>

        <div className="space-y-1">
          <label
            htmlFor="edge-target-entity-input"
            className="text-xs font-medium text-muted-foreground block"
          >
            客体实体/结论 (Target Entity ID)
          </label>
          <input
            id="edge-target-entity-input"
            type="text"
            value={targetEntityId}
            onChange={(e) => setTargetEntityId(e.target.value)}
            placeholder="如 fact_xxx 或 peer_xxx"
            className="w-full px-2.5 py-1.5 text-xs bg-background rounded border border-input focus:outline-none focus:ring-2 focus:ring-primary text-foreground"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <div className="md:col-span-3 space-y-1">
          <label
            htmlFor="edge-context-note-input"
            className="text-xs font-medium text-muted-foreground block"
          >
            情境说明 / 决策原由 (Context Rationale)
          </label>
          <input
            id="edge-context-note-input"
            type="text"
            value={contextNote}
            onChange={(e) => setContextNote(e.target.value)}
            placeholder="记录为何断言、审查依据或协作约定..."
            className="w-full px-2.5 py-1.5 text-xs bg-background rounded border border-input focus:outline-none focus:ring-2 focus:ring-primary text-foreground"
          />
        </div>

        <div className="flex items-end">
          <label
            htmlFor="edge-target-is-peer-checkbox"
            className="flex items-center gap-2 text-xs font-medium text-muted-foreground cursor-pointer pb-2"
          >
            <input
              id="edge-target-is-peer-checkbox"
              type="checkbox"
              checked={targetIsPeer}
              onChange={(e) => setTargetIsPeer(e.target.checked)}
              className="rounded border-input text-primary focus:ring-primary"
            />
            <span>客体也是 Peer 实体</span>
          </label>
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-1">
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 rounded-md text-xs font-medium bg-muted hover:bg-muted/80 text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
        >
          取消
        </button>
        <button
          type="submit"
          disabled={submitting || !targetEntityId.trim()}
          className="px-4 py-1.5 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
        >
          {submitting ? '保存中...' : '提交图谱关系边'}
        </button>
      </div>
    </form>
  );
};
