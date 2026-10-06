/**
 * [INPUT]
 * Project root path, custom instructions, topic session configurations
 *
 * [OUTPUT]
 * ProjectContainer: First-class project workspace container descriptor
 * TopicSessionBranch: In-project session branch承载独立的对话与探索
 * BranchInheritancePolicy: Context and configuration inheritance rules
 * IntentNamingResult: Structured title derivation from first-turn prompt
 *
 * [POS]
 * myrm-agent-frontend/src/store/projectWorkspace/projectHierarchyTypes.ts
 * Two-tier Workspace-Project hierarchy and in-project topic branching models.
 */

export interface ProjectContainer {
  readonly projectId: string;
  readonly name: string;
  readonly rootPath: string;
  readonly memoryPartitionId: string;
  readonly customInstructions?: string;
  readonly tags: readonly string[];
  readonly createdAt: number;
  readonly updatedAt: number;
}

export interface BranchInheritancePolicy {
  readonly inheritCustomInstructions: boolean;
  readonly inheritMemoryPartition: boolean;
  readonly inheritTechnicalConclusions: boolean;
  readonly parentSessionId?: string;
  readonly branchReason?: string;
}

export interface TopicSessionBranch {
  readonly sessionId: string;
  readonly projectId: string;
  readonly title: string;
  readonly parentSessionId?: string;
  readonly branchReason?: string;
  readonly inheritedConclusions: readonly string[];
  readonly createdAt: number;
  readonly updatedAt: number;
  readonly isRenamedByIntent: boolean;
}

export interface IntentNamingResult {
  readonly title: string;
  readonly category: 'refactor' | 'bugfix' | 'feature' | 'test' | 'inquiry' | 'general';
  readonly confidence: number;
}
