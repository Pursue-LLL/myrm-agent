import React, { useState } from 'react';
import {
  CollaboratorItem,
  DocumentBlockItem,
  DeltaEntryItem,
  StagingProposalItem,
  ArbitrationStrategy,
  ArbitrationVerdictItem,
  DEFAULT_COLLABORATORS,
  DEFAULT_DOC_BLOCKS,
  DEFAULT_PROPOSALS,
} from './coauthoring-ledger/types';
import { CoAuthoringHeader } from './coauthoring-ledger/CoAuthoringHeader';
import { DocumentBlocksView } from './coauthoring-ledger/DocumentBlocksView';
import { RosterView } from './coauthoring-ledger/RosterView';
import { ProposalsView } from './coauthoring-ledger/ProposalsView';
import { IntentLedgerView } from './coauthoring-ledger/IntentLedgerView';

export interface LiveDocumentCoAuthoringCardProps {
  chatId: string;
  documentId?: string;
  initialCollaborators?: CollaboratorItem[];
  initialBlocks?: DocumentBlockItem[];
  initialProposals?: StagingProposalItem[];
  onAcquireLease?: (blockId: string, authorId: string) => Promise<boolean>;
  onReleaseLease?: (blockId: string, authorId: string) => Promise<boolean>;
  onCommitDelta?: (delta: Omit<DeltaEntryItem, 'deltaId' | 'timestamp' | 'applied'>) => Promise<boolean>;
  onArbitrate?: (blockId: string, strategy: ArbitrationStrategy) => Promise<ArbitrationVerdictItem>;
  onAcceptProposal?: (proposalId: string) => Promise<boolean>;
  onRejectProposal?: (proposalId: string) => Promise<boolean>;
}

export const LiveDocumentCoAuthoringCard: React.FC<LiveDocumentCoAuthoringCardProps> = ({
  chatId,
  documentId = 'doc-spec-001',
  initialCollaborators = DEFAULT_COLLABORATORS,
  initialBlocks = DEFAULT_DOC_BLOCKS,
  initialProposals = DEFAULT_PROPOSALS,
  onAcquireLease,
  onReleaseLease,
  onCommitDelta,
  onArbitrate,
  onAcceptProposal,
  onRejectProposal,
}) => {
  const [collaborators] = useState<CollaboratorItem[]>(initialCollaborators);
  const [blocks, setBlocks] = useState<DocumentBlockItem[]>(initialBlocks);
  const [proposals, setProposals] = useState<StagingProposalItem[]>(initialProposals);
  const [deltas, setDeltas] = useState<DeltaEntryItem[]>([
    {
      deltaId: 'delta-init-01',
      documentId,
      blockId: 'block-02-exec-summary',
      operation: 'update_block',
      authorId: 'agent-alice-bot',
      authorType: 'agent',
      principalHumanId: 'user-alice',
      prevContent: 'Draft summary.',
      newContent: 'This specification defines the tripartite live document co-authoring state machine.',
      intentReason: 'Refined architecture specification overview',
      timestamp: Date.now() - 1800000,
      applied: true,
    },
  ]);

  const [activeTab, setActiveTab] = useState<'document' | 'roster' | 'proposals' | 'ledger'>('document');
  const [selectedCollaboratorId, setSelectedCollaboratorId] = useState<string>('user-alice');
  const [selectedBlockId, setSelectedBlockId] = useState<string>('block-02-exec-summary');
  const [editDraft, setEditDraft] = useState<string>('');
  const [intentInput, setIntentInput] = useState<string>('');
  const [strategy, setStrategy] = useState<ArbitrationStrategy>('human_priority');
  const [verdict, setVerdict] = useState<ArbitrationVerdictItem | null>(null);
  const [statusMessage, setStatusMessage] = useState<string>('System initialized and ready.');
  const [isProcessing, setIsProcessing] = useState<boolean>(false);

  const currentCollaborator = collaborators.find((c) => c.collaboratorId === selectedCollaboratorId) || collaborators[0];
  const currentBlock = blocks.find((b) => b.blockId === selectedBlockId) || blocks[0];

  const handleAcquireLease = async (blockId: string) => {
    setIsProcessing(true);
    setStatusMessage(`Requesting write lease lock for block ${blockId}...`);
    try {
      if (onAcquireLease) {
        await onAcquireLease(blockId, selectedCollaboratorId);
      }
      setBlocks((prev) =>
        prev.map((b) =>
          b.blockId === blockId
            ? { ...b, leaseHolderId: selectedCollaboratorId, leaseExpiresAt: Date.now() + 30000 }
            : b
        )
      );
      setStatusMessage(`Lease acquired on ${blockId} by ${currentCollaborator.name}.`);
    } catch {
      setStatusMessage(`Failed to acquire lease on ${blockId}.`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleReleaseLease = async (blockId: string) => {
    setIsProcessing(true);
    try {
      if (onReleaseLease) {
        await onReleaseLease(blockId, selectedCollaboratorId);
      }
      setBlocks((prev) =>
        prev.map((b) =>
          b.blockId === blockId ? { ...b, leaseHolderId: undefined, leaseExpiresAt: undefined } : b
        )
      );
      setStatusMessage(`Lease released for block ${blockId}.`);
    } catch {
      setStatusMessage(`Failed to release lease on ${blockId}.`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCommitEdit = async () => {
    if (!editDraft.trim() || !intentInput.trim()) {
      setStatusMessage('Both edit content and intent reason are required.');
      return;
    }
    setIsProcessing(true);
    try {
      if (onCommitDelta) {
        await onCommitDelta({
          documentId,
          blockId: selectedBlockId,
          operation: 'update_block',
          authorId: selectedCollaboratorId,
          authorType: currentCollaborator.collaboratorType,
          principalHumanId: currentCollaborator.principalHumanId,
          prevContent: currentBlock.content,
          newContent: editDraft,
          intentReason: intentInput,
        });
      }
      const newDelta: DeltaEntryItem = {
        deltaId: `delta-${Date.now()}`,
        documentId,
        blockId: selectedBlockId,
        operation: 'update_block',
        authorId: selectedCollaboratorId,
        authorType: currentCollaborator.collaboratorType,
        principalHumanId: currentCollaborator.principalHumanId,
        prevContent: currentBlock.content,
        newContent: editDraft,
        intentReason: intentInput,
        timestamp: Date.now(),
        applied: true,
      };
      setDeltas((prev) => [newDelta, ...prev]);
      setBlocks((prev) =>
        prev.map((b) =>
          b.blockId === selectedBlockId
            ? {
                ...b,
                content: editDraft,
                version: b.version + 1,
                lastAuthorId: selectedCollaboratorId,
                lastUpdatedAt: Date.now(),
                leaseHolderId: undefined,
                leaseExpiresAt: undefined,
              }
            : b
        )
      );
      setStatusMessage(`Block ${selectedBlockId} updated to v${currentBlock.version + 1} by ${currentCollaborator.name}.`);
      setEditDraft('');
      setIntentInput('');
    } catch {
      setStatusMessage('Failed to commit delta edit.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleAcceptProposal = async (propId: string) => {
    setIsProcessing(true);
    const target = proposals.find((p) => p.proposalId === propId);
    if (!target) {
      return;
    }
    try {
      if (onAcceptProposal) {
        await onAcceptProposal(propId);
      }
      setProposals((prev) => prev.map((p) => (p.proposalId === propId ? { ...p, status: 'accepted' } : p)));
      setBlocks((prev) =>
        prev.map((b) =>
          b.blockId === target.blockId
            ? { ...b, content: target.content, version: b.version + 1, lastAuthorId: target.authorId, lastUpdatedAt: Date.now() }
            : b
        )
      );
      setStatusMessage(`Staging proposal ${propId} accepted and merged into live document.`);
    } catch {
      setStatusMessage(`Failed to accept proposal ${propId}.`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleRejectProposal = async (propId: string) => {
    setIsProcessing(true);
    try {
      if (onRejectProposal) {
        await onRejectProposal(propId);
      }
      setProposals((prev) => prev.map((p) => (p.proposalId === propId ? { ...p, status: 'rejected' } : p)));
      setStatusMessage(`Staging proposal ${propId} rejected.`);
    } catch {
      setStatusMessage(`Failed to reject proposal ${propId}.`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleArbitrate = async () => {
    setIsProcessing(true);
    setStatusMessage(`Running conflict arbitration on ${selectedBlockId} with strategy ${strategy}...`);
    try {
      if (onArbitrate) {
        const res = await onArbitrate(selectedBlockId, strategy);
        setVerdict(res);
      } else {
        const simulated: ArbitrationVerdictItem = {
          resolved: true,
          winningContent: currentBlock.content,
          strategy,
          summary: `Arbitration resolved using ${strategy}. Winning block preserved with staging backup.`,
          stagingProposals: [],
          timestamp: Date.now(),
        };
        setVerdict(simulated);
      }
      setStatusMessage(`Arbitration concluded successfully.`);
    } catch {
      setStatusMessage('Arbitration failed.');
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <section
      aria-label="Live Document Co-Authoring Ledger"
      className="rounded-xl border border-border bg-card p-4 shadow-sm text-card-foreground my-3"
      data-testid="live-document-coauthoring-card"
    >
      <CoAuthoringHeader
        chatId={chatId}
        documentId={documentId}
        collaborators={collaborators}
        selectedCollaboratorId={selectedCollaboratorId}
        onSelectCollaborator={setSelectedCollaboratorId}
      />

      {/* Tab Navigation */}
      <nav className="flex space-x-1 border-b border-border mb-3" aria-label="Co-Authoring Card Tabs">
        {(['document', 'roster', 'proposals', 'ledger'] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-1.5 text-xs font-medium rounded-t-md transition-colors ${
              activeTab === tab
                ? 'border-b-2 border-primary text-primary bg-muted/40 font-semibold'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/20'
            }`}
          >
            {tab === 'document' && 'Live Document'}
            {tab === 'roster' && `Roster (${collaborators.length})`}
            {tab === 'proposals' && `Staging Proposals (${proposals.length})`}
            {tab === 'ledger' && `Intent Ledger (${deltas.length})`}
          </button>
        ))}
      </nav>

      {/* Tab Contents */}
      {activeTab === 'document' && (
        <DocumentBlocksView
          blocks={blocks}
          collaborators={collaborators}
          selectedBlockId={selectedBlockId}
          onSelectBlockId={(id) => {
            setSelectedBlockId(id);
            const found = blocks.find((b) => b.blockId === id);
            if (found) {
              setEditDraft(found.content);
            }
          }}
          editDraft={editDraft}
          onChangeEditDraft={setEditDraft}
          intentInput={intentInput}
          onChangeIntentInput={setIntentInput}
          isProcessing={isProcessing}
          onAcquireLease={handleAcquireLease}
          onReleaseLease={handleReleaseLease}
          onCommitEdit={handleCommitEdit}
        />
      )}

      {activeTab === 'roster' && <RosterView collaborators={collaborators} />}

      {activeTab === 'proposals' && (
        <ProposalsView
          proposals={proposals}
          strategy={strategy}
          onChangeStrategy={setStrategy}
          verdict={verdict}
          isProcessing={isProcessing}
          onArbitrate={handleArbitrate}
          onAcceptProposal={handleAcceptProposal}
          onRejectProposal={handleRejectProposal}
        />
      )}

      {activeTab === 'ledger' && <IntentLedgerView deltas={deltas} />}

      <footer className="mt-3 pt-2 border-t border-border flex items-center justify-between text-[11px] text-muted-foreground">
        <span>Blocks: {blocks.length} | Deltas: {deltas.length}</span>
        <output aria-live="polite" className="font-mono text-primary text-[10px]">
          {statusMessage}
        </output>
      </footer>
    </section>
  );
};
export default LiveDocumentCoAuthoringCard;
