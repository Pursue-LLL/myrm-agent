// @orphan-ok WorkspaceProjectManager for first-class project workspace container and branching sessions
/**
 * [INPUT]
 * ./projectHierarchyTypes::ProjectContainer, TopicSessionBranch, BranchInheritancePolicy, IntentNamingResult
 *
 * [OUTPUT]
 * WorkspaceProjectManager: First-class project workspace container & branching session manager
 *
 * [POS]
 * myrm-agent-frontend/src/store/projectWorkspace/workspaceProjectManager.ts
 * Manages two-tier project hierarchy, in-project branching sessions, and auto-renaming by intent.
 */

import {
  ProjectContainer,
  TopicSessionBranch,
  BranchInheritancePolicy,
  IntentNamingResult,
} from './projectHierarchyTypes';

export interface CreateProjectParams {
  readonly projectId?: string;
  readonly name: string;
  readonly rootPath: string;
  readonly memoryPartitionId?: string;
  readonly customInstructions?: string;
  readonly tags?: readonly string[];
}

const DEFAULT_INHERITANCE_POLICY: BranchInheritancePolicy = {
  inheritCustomInstructions: true,
  inheritMemoryPartition: true,
  inheritTechnicalConclusions: true,
};

export class WorkspaceProjectManager {
  private static instance: WorkspaceProjectManager | null = null;

  private readonly projects = new Map<string, ProjectContainer>();
  private readonly sessions = new Map<string, TopicSessionBranch>();
  private readonly projectSessionMap = new Map<string, Set<string>>();

  public static getInstance(): WorkspaceProjectManager {
    if (!WorkspaceProjectManager.instance) {
      WorkspaceProjectManager.instance = new WorkspaceProjectManager();
    }
    return WorkspaceProjectManager.instance;
  }

  public static resetInstance(): void {
    if (WorkspaceProjectManager.instance) {
      WorkspaceProjectManager.instance.clear();
      WorkspaceProjectManager.instance = null;
    }
  }

  public createProject(params: CreateProjectParams): ProjectContainer {
    const now = Date.now();
    const projectId = params.projectId?.trim() || `proj_${Math.random().toString(36).substring(2, 10)}_${now}`;
    const partitionId = params.memoryPartitionId?.trim() || `mem_part_${projectId}`;

    const project: ProjectContainer = {
      projectId,
      name: params.name.trim(),
      rootPath: params.rootPath.trim(),
      memoryPartitionId: partitionId,
      customInstructions: params.customInstructions?.trim(),
      tags: params.tags ? [...params.tags] : [],
      createdAt: now,
      updatedAt: now,
    };

    this.projects.set(projectId, project);
    this.projectSessionMap.set(projectId, new Set());
    return project;
  }

  public getProject(projectId: string): ProjectContainer | undefined {
    return this.projects.get(projectId);
  }

  public listProjects(): readonly ProjectContainer[] {
    return Array.from(this.projects.values());
  }

  public updateProjectInstructions(projectId: string, instructions: string): boolean {
    const existing = this.projects.get(projectId);
    if (!existing) {
      return false;
    }
    const updated: ProjectContainer = {
      ...existing,
      customInstructions: instructions.trim(),
      updatedAt: Date.now(),
    };
    this.projects.set(projectId, updated);
    return true;
  }

  public createSessionBranch(
    projectId: string,
    options?: {
      sessionId?: string;
      title?: string;
      policy?: Partial<BranchInheritancePolicy>;
      parentConclusions?: readonly string[];
    },
  ): TopicSessionBranch {
    const project = this.projects.get(projectId);
    if (!project) {
      throw new Error(`[WorkspaceProjectManager] Cannot create session: Project ${projectId} does not exist`);
    }

    const now = Date.now();
    const sessionId = options?.sessionId?.trim() || `sess_${Math.random().toString(36).substring(2, 10)}_${now}`;
    const title = options?.title?.trim() || `New Session (${new Date(now).toLocaleTimeString()})`;

    const policy: BranchInheritancePolicy = {
      ...DEFAULT_INHERITANCE_POLICY,
      ...(options?.policy || {}),
    };

    let inheritedConclusions: readonly string[] = [];
    if (policy.inheritTechnicalConclusions && options?.parentConclusions) {
      inheritedConclusions = [...options.parentConclusions];
    }

    const branch: TopicSessionBranch = {
      sessionId,
      projectId,
      title,
      parentSessionId: policy.parentSessionId,
      branchReason: policy.branchReason,
      inheritedConclusions,
      createdAt: now,
      updatedAt: now,
      isRenamedByIntent: false,
    };

    this.sessions.set(sessionId, branch);
    const sessionSet = this.projectSessionMap.get(projectId);
    if (sessionSet) {
      sessionSet.add(sessionId);
    }

    return branch;
  }

  public getSession(sessionId: string): TopicSessionBranch | undefined {
    return this.sessions.get(sessionId);
  }

  public listProjectSessions(projectId: string): readonly TopicSessionBranch[] {
    const sessionIds = this.projectSessionMap.get(projectId);
    if (!sessionIds) {
      return [];
    }
    const results: TopicSessionBranch[] = [];
    for (const sid of sessionIds) {
      const s = this.sessions.get(sid);
      if (s) {
        results.push(s);
      }
    }
    return results;
  }

  public deriveIntentTitle(firstTurnPrompt: string): IntentNamingResult {
    const prompt = firstTurnPrompt.trim();
    if (!prompt) {
      return {
        title: 'Untitled Session',
        category: 'general',
        confidence: 0.2,
      };
    }

    // Pattern matching rules for intention classification
    const refactorPattern = /(?:refactor|optimize|cleanup|clean up|restructure|rewrite|重构|优化|重写)/i;
    const bugfixPattern = /(?:fix|bug|error|exception|crash|issue|broken|panic|修复|报错|异常|解决)/i;
    const testPattern = /(?:test|spec|e2e|unit test|integration test|vitest|pytest|测试|单测)/i;
    const featurePattern = /(?:implement|add|create|build|support|feature|实现|新增|增加|创建|开发)/i;
    const inquiryPattern = /(?:how|what|why|analyze|explain|inspect|audit|怎么|如何|为什么|解释|分析|审查)/i;

    let category: IntentNamingResult['category'] = 'general';
    let prefix = '';

    if (refactorPattern.test(prompt)) {
      category = 'refactor';
      prefix = 'Refactor';
    } else if (bugfixPattern.test(prompt)) {
      category = 'bugfix';
      prefix = 'Fix';
    } else if (testPattern.test(prompt)) {
      category = 'test';
      prefix = 'Test';
    } else if (featurePattern.test(prompt)) {
      category = 'feature';
      prefix = 'Feature';
    } else if (inquiryPattern.test(prompt)) {
      category = 'inquiry';
      prefix = 'Analysis';
    }

    // Clean and condense prompt snippet
    let cleaned = prompt
      .replace(/^(?:please|can you|could you|help me|请|帮我|麻烦)\s*/i, '')
      .replace(/[?!.,;:，。？！]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();

    // Limit length to around 36 characters
    if (cleaned.length > 36) {
      cleaned = `${cleaned.substring(0, 33)}...`;
    }

    const title = prefix ? `${prefix}: ${cleaned}` : cleaned;

    return {
      title,
      category,
      confidence: prefix ? 0.9 : 0.6,
    };
  }

  public renameSessionByIntent(sessionId: string, firstTurnPrompt: string): TopicSessionBranch | undefined {
    const session = this.sessions.get(sessionId);
    if (!session) {
      return undefined;
    }

    const intent = this.deriveIntentTitle(firstTurnPrompt);
    const updated: TopicSessionBranch = {
      ...session,
      title: intent.title,
      updatedAt: Date.now(),
      isRenamedByIntent: true,
    };

    this.sessions.set(sessionId, updated);
    return updated;
  }

  public clear(): void {
    this.projects.clear();
    this.sessions.clear();
    this.projectSessionMap.clear();
  }
}
