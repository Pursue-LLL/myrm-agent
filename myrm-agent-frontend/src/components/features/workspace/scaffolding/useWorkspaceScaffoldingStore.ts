import { create } from 'zustand';
import { generateDefaultScaffoldingProposal } from './workspaceScaffoldingEngine';
import {
  GeneratedScaffoldDoc,
  ScaffoldingProposal,
} from './workspaceScaffoldingTypes';

interface WorkspaceScaffoldingState {
  proposals: Record<string, ScaffoldingProposal>;
  activeProposalId: string | null;
  isPreviewModalOpen: boolean;
  previewingDoc: GeneratedScaffoldDoc | null;

  triggerScaffoldAnalysis: (
    workspacePath: string,
    fileList: string[],
    utterance?: string,
  ) => string;
  confirmProposal: (proposalId: string) => boolean;
  cancelProposal: (proposalId: string) => boolean;
  openDocPreview: (doc: GeneratedScaffoldDoc) => void;
  closeDocPreview: () => void;
  reset: () => void;
}

export const useWorkspaceScaffoldingStore =
  create<WorkspaceScaffoldingState>((set, get) => ({
    proposals: {},
    activeProposalId: null,
    isPreviewModalOpen: false,
    previewingDoc: null,

    triggerScaffoldAnalysis: (
      workspacePath: string,
      fileList: string[],
      utterance?: string,
    ): string => {
      const proposal = generateDefaultScaffoldingProposal(
        workspacePath,
        fileList,
        utterance,
      );

      set((state) => ({
        proposals: {
          ...state.proposals,
          [proposal.id]: proposal,
        },
        activeProposalId: proposal.id,
      }));

      return proposal.id;
    },

    confirmProposal: (proposalId: string): boolean => {
      const target = get().proposals[proposalId];
      if (!target || target.status !== 'pending_review') {
        return false;
      }

      set((state) => ({
        proposals: {
          ...state.proposals,
          [proposalId]: {
            ...target,
            status: 'confirmed',
          },
        },
      }));

      return true;
    },

    cancelProposal: (proposalId: string): boolean => {
      const target = get().proposals[proposalId];
      if (!target || target.status !== 'pending_review') {
        return false;
      }

      set((state) => ({
        proposals: {
          ...state.proposals,
          [proposalId]: {
            ...target,
            status: 'cancelled',
          },
        },
      }));

      return true;
    },

    openDocPreview: (doc: GeneratedScaffoldDoc): void => {
      set({
        isPreviewModalOpen: true,
        previewingDoc: doc,
      });
    },

    closeDocPreview: (): void => {
      set({
        isPreviewModalOpen: false,
        previewingDoc: null,
      });
    },

    reset: (): void => {
      set({
        proposals: {},
        activeProposalId: null,
        isPreviewModalOpen: false,
        previewingDoc: null,
      });
    },
  }));
