import { describe, it, expect, beforeEach } from 'vitest';
import { WorkspaceProjectManager } from '../workspaceProjectManager';

describe('WorkspaceProjectManager', () => {
  beforeEach(() => {
    WorkspaceProjectManager.resetInstance();
  });

  it('creates and manages first-class project workspace containers', () => {
    const manager = WorkspaceProjectManager.getInstance();

    const proj = manager.createProject({
      name: 'E-Commerce Core API',
      rootPath: '/home/user/projects/ecommerce-api',
      customInstructions: 'Follow PEP8 and use PostgreSQL 16.',
      tags: ['backend', 'python'],
    });

    expect(proj.projectId).toMatch(/^proj_/);
    expect(proj.name).toBe('E-Commerce Core API');
    expect(proj.rootPath).toBe('/home/user/projects/ecommerce-api');
    expect(proj.memoryPartitionId).toBe(`mem_part_${proj.projectId}`);
    expect(proj.customInstructions).toBe('Follow PEP8 and use PostgreSQL 16.');
    expect(proj.tags).toEqual(['backend', 'python']);

    const fetched = manager.getProject(proj.projectId);
    expect(fetched).toEqual(proj);

    // Update instructions
    const updated = manager.updateProjectInstructions(proj.projectId, 'Updated instructions.');
    expect(updated).toBe(true);
    expect(manager.getProject(proj.projectId)?.customInstructions).toBe('Updated instructions.');

    // List projects
    expect(manager.listProjects().length).toBe(1);
  });

  it('creates in-project session branches and inherits parent technical conclusions', () => {
    const manager = WorkspaceProjectManager.getInstance();
    const proj = manager.createProject({
      name: 'Auth Service',
      rootPath: '/workspace/auth',
    });

    // 1. Root session in project
    const rootSession = manager.createSessionBranch(proj.projectId, {
      title: 'Architectural Exploration',
    });

    expect(rootSession.projectId).toBe(proj.projectId);
    expect(rootSession.parentSessionId).toBeUndefined();
    expect(rootSession.inheritedConclusions).toEqual([]);

    // 2. Child branch session inheriting conclusions
    const parentConclusions = [
      'Use JWT with RS256 signing',
      'Store refresh token in Redis with 7-day TTL',
    ];

    const childBranch = manager.createSessionBranch(proj.projectId, {
      title: 'Implementation Branch',
      policy: {
        parentSessionId: rootSession.sessionId,
        branchReason: 'Splitting implementation from planning to prevent context pollution',
        inheritTechnicalConclusions: true,
      },
      parentConclusions,
    });

    expect(childBranch.projectId).toBe(proj.projectId);
    expect(childBranch.parentSessionId).toBe(rootSession.sessionId);
    expect(childBranch.branchReason).toBe('Splitting implementation from planning to prevent context pollution');
    expect(childBranch.inheritedConclusions).toEqual(parentConclusions);

    // List project sessions
    const sessions = manager.listProjectSessions(proj.projectId);
    expect(sessions.length).toBe(2);
    expect(sessions.map((s) => s.sessionId)).toContain(rootSession.sessionId);
    expect(sessions.map((s) => s.sessionId)).toContain(childBranch.sessionId);
  });

  it('throws an error when trying to create a session for a non-existent project', () => {
    const manager = WorkspaceProjectManager.getInstance();
    expect(() => {
      manager.createSessionBranch('non_existent_project');
    }).toThrowError(/does not exist/);
  });

  it('derives intent titles accurately across various technical tasks', () => {
    const manager = WorkspaceProjectManager.getInstance();

    // 1. Refactor intent
    const resRefactor = manager.deriveIntentTitle('Please refactor the user authentication service module');
    expect(resRefactor.category).toBe('refactor');
    expect(resRefactor.title).toContain('Refactor:');
    expect(resRefactor.confidence).toBeGreaterThanOrEqual(0.8);

    // 2. Bugfix intent
    const resFix = manager.deriveIntentTitle('Fix database connection timeout error on startup');
    expect(resFix.category).toBe('bugfix');
    expect(resFix.title).toContain('Fix:');

    // 3. Test intent
    const resTest = manager.deriveIntentTitle('Write unit tests for checkout payment calculation');
    expect(resTest.category).toBe('test');
    expect(resTest.title).toContain('Test:');

    // 4. Feature intent
    const resFeature = manager.deriveIntentTitle('Implement OAuth2 Google login integration');
    expect(resFeature.category).toBe('feature');
    expect(resFeature.title).toContain('Feature:');

    // 5. Inquiry / Analysis intent
    const resInquiry = manager.deriveIntentTitle('Analyze why token generation takes 2 seconds');
    expect(resInquiry.category).toBe('inquiry');
    expect(resInquiry.title).toContain('Analysis:');

    // 6. Empty prompt fallback
    const resEmpty = manager.deriveIntentTitle('');
    expect(resEmpty.category).toBe('general');
    expect(resEmpty.title).toBe('Untitled Session');
  });

  it('renames session by intent on first turn successfully', () => {
    const manager = WorkspaceProjectManager.getInstance();
    const proj = manager.createProject({
      name: 'Billing Engine',
      rootPath: '/workspace/billing',
    });

    const session = manager.createSessionBranch(proj.projectId);
    expect(session.isRenamedByIntent).toBe(false);

    const renamed = manager.renameSessionByIntent(
      session.sessionId,
      'Fix Stripe webhook signature verification failure',
    );

    expect(renamed).toBeDefined();
    expect(renamed?.isRenamedByIntent).toBe(true);
    expect(renamed?.title).toContain('Fix:');
    expect(renamed?.title).toContain('Stripe webhook signature');

    // Subsequent retrieval has updated title
    const fetched = manager.getSession(session.sessionId);
    expect(fetched?.title).toBe(renamed?.title);
  });
});
