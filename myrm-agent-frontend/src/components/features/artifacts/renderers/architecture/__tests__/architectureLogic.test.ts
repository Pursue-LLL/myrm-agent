import { describe, expect, it } from 'vitest';
import { sanitizeArchitectureIR, computeDagreLayout } from '../layout';
import { computeArchitectureDiff } from '../diff';
import type { ArchitectureIR } from '../types';
import { isArchitectureType } from '../../artifactUtils';

describe('Architecture Layout & Sanitization', () => {
  it('sanitizes dangling edges and normalizes node fields', () => {
    const raw: ArchitectureIR = {
      title: 'Test Topology',
      nodes: [
        { id: 'node-1', label: 'Service A' },
        { id: 'node-2', label: 'Service B' },
        { id: 'node-1', label: 'Duplicate Service A' }, // duplicate id
      ],
      edges: [
        { source: 'node-1', target: 'node-2', label: 'Calls' },
        { source: 'node-1', target: 'nonexistent', label: 'Dangling' },
      ],
    };

    const sanitized = sanitizeArchitectureIR(raw);
    expect(sanitized.nodes.length).toBe(2);
    expect(sanitized.nodes[0].id).toBe('node-1');
    expect(sanitized.nodes[1].id).toBe('node-2');
    expect(sanitized.edges.length).toBe(1);
    expect(sanitized.edges[0].target).toBe('node-2');
    expect(sanitized.edges[0].id).toBeDefined();
  });

  it('computes DAG layout with Dagre positioning nodes and edges', () => {
    const raw: ArchitectureIR = {
      title: 'DAG Test',
      direction: 'TB',
      nodes: [
        { id: 'gateway', label: 'API Gateway', category: 'gateway' },
        { id: 'order', label: 'Order Service', category: 'backend' },
      ],
      edges: [{ id: 'e1', source: 'gateway', target: 'order' }],
    };

    const layouted = computeDagreLayout(raw);
    expect(layouted.nodes.length).toBe(2);
    expect(layouted.edges.length).toBe(1);

    const gatewayNode = layouted.nodes.find((n) => n.id === 'gateway');
    const orderNode = layouted.nodes.find((n) => n.id === 'order');

    expect(gatewayNode).toBeDefined();
    expect(orderNode).toBeDefined();
    if (gatewayNode && orderNode) {
      // In TB (Top to Bottom) layout, gateway should have lower Y coordinate than order
      expect(gatewayNode.position.y).toBeLessThan(orderNode.position.y);
    }
  });
});

describe('Architecture Evolution Diff', () => {
  it('correctly categorizes added, deleted, modified, and unchanged elements', () => {
    const before: ArchitectureIR = {
      title: 'v1',
      nodes: [
        { id: 'frontend', label: 'Web UI', category: 'frontend' },
        { id: 'monolith', label: 'Legacy Monolith', category: 'backend', description: 'v1.0' },
      ],
      edges: [{ id: 'e1', source: 'frontend', target: 'monolith' }],
    };

    const after: ArchitectureIR = {
      title: 'v2',
      nodes: [
        { id: 'frontend', label: 'Web UI', category: 'frontend' }, // unchanged
        { id: 'monolith', label: 'Legacy Monolith', category: 'backend', description: 'v2.0 modified' }, // modified
        { id: 'microservice', label: 'New Service', category: 'backend' }, // added
      ],
      edges: [
        { id: 'e2', source: 'frontend', target: 'microservice' }, // added
      ],
    };

    const diff = computeArchitectureDiff(before, after);

    const frontendNode = diff.nodes.find((n) => n.id === 'frontend');
    const monolithNode = diff.nodes.find((n) => n.id === 'monolith');
    const microserviceNode = diff.nodes.find((n) => n.id === 'microservice');

    expect(frontendNode?.diffState).toBe('unchanged');
    expect(monolithNode?.diffState).toBe('modified');
    expect(microserviceNode?.diffState).toBe('added');

    const addedEdge = diff.edges.find((e) => e.source === 'frontend' && e.target === 'microservice');
    const deletedEdge = diff.edges.find((e) => e.source === 'frontend' && e.target === 'monolith');

    expect(addedEdge?.diffState).toBe('added');
    expect(deletedEdge?.diffState).toBe('deleted');
  });
});

describe('Architecture Artifact Utility Contract', () => {
  it('identifies architecture artifact files correctly', () => {
    function isArch(contentType: string, filename: string): boolean {
      return (
        contentType.includes('application/x-architecture') ||
        filename.endsWith('.arch.json') ||
        filename.endsWith('.architecture.json')
      );
    }
    expect(isArch('application/json', 'system.arch.json')).toBe(true);
    expect(isArch('application/x-architecture', 'diagram.json')).toBe(true);
    expect(isArch('application/json', 'architecture.json')).toBe(false);
    expect(isArch('application/json', 'system.architecture.json')).toBe(true);
    expect(isArch('text/plain', 'readme.txt')).toBe(false);
  });
});
