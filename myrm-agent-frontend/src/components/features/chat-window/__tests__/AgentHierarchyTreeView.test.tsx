'use client';

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  AgentHierarchyNode,
  AgentHierarchyTreeView,
} from '../AgentHierarchyTreeView';

const mockForest: AgentHierarchyNode[] = [
  {
    agentId: 'lead-architect',
    name: 'Atlas Lead Architect',
    description: 'System coordinator',
    agentType: 'team',
    depth: 0,
    provenance: {
      agentId: 'lead-architect',
      creatorType: 'user',
      creatorId: 'admin-alice',
      ancestryPath: [],
    },
    children: [
      {
        agentId: 'backend-engineer',
        name: 'Gilfoyle Coder',
        agentType: 'individual',
        depth: 1,
        provenance: {
          agentId: 'backend-engineer',
          creatorType: 'agent',
          creatorId: 'lead-architect',
          parentAgentId: 'lead-architect',
          ancestryPath: ['lead-architect'],
        },
        children: [
          {
            agentId: 'sql-optimizer',
            name: 'SQL Query Tuning Worker',
            agentType: 'subagent',
            depth: 2,
            provenance: {
              agentId: 'sql-optimizer',
              creatorType: 'agent',
              creatorId: 'backend-engineer',
              parentAgentId: 'backend-engineer',
              ancestryPath: ['lead-architect', 'backend-engineer'],
            },
            children: [],
          },
        ],
      },
      {
        agentId: 'scripted-tester',
        name: 'CI Integration Bot',
        agentType: 'individual',
        depth: 1,
        provenance: {
          agentId: 'scripted-tester',
          creatorType: 'script',
          creatorId: 'ci-pipeline.yml',
          parentAgentId: 'lead-architect',
          ancestryPath: ['lead-architect'],
        },
        children: [],
      },
    ],
  },
  {
    agentId: 'system-guard',
    name: 'Default Security Watchdog',
    agentType: 'individual',
    depth: 0,
    provenance: {
      agentId: 'system-guard',
      creatorType: 'system',
      creatorId: 'system',
      ancestryPath: [],
    },
    children: [],
  },
];

describe('AgentHierarchyTreeView', () => {
  it('renders empty state when no roots provided', () => {
    render(<AgentHierarchyTreeView roots={[]} />);

    expect(screen.getByTestId('empty-hierarchy-state')).toBeInTheDocument();
    expect(screen.getByText('暂无智能体层级数据')).toBeInTheDocument();
    expect(screen.getByText('顶级根节点 0')).toBeInTheDocument();
  });

  it('renders multi-tier hierarchy forest with correct depth and children counts', () => {
    render(<AgentHierarchyTreeView roots={mockForest} totalNodes={5} maxDepth={2} />);

    expect(screen.getByTestId('hierarchy-forest')).toBeInTheDocument();
    expect(screen.getByText('Atlas Lead Architect')).toBeInTheDocument();
    expect(screen.getByText('Gilfoyle Coder')).toBeInTheDocument();
    expect(screen.getByText('SQL Query Tuning Worker')).toBeInTheDocument();
    expect(screen.getByText('CI Integration Bot')).toBeInTheDocument();
    expect(screen.getByText('Default Security Watchdog')).toBeInTheDocument();

    // Headers metrics
    expect(screen.getByText('(5 节点, 最大深度 2)')).toBeInTheDocument();
    expect(screen.getByText('顶级根节点 2')).toBeInTheDocument();

    // Children count badge
    expect(screen.getByText('2 子智能体')).toBeInTheDocument();
    expect(screen.getByText('1 子智能体')).toBeInTheDocument();
  });

  it('renders different creator badges correctly', () => {
    render(<AgentHierarchyTreeView roots={mockForest} />);

    // User creator
    expect(screen.getByText('用户创建')).toBeInTheDocument();

    // Agent creator
    expect(screen.getByText('衍生自 @lead-architect')).toBeInTheDocument();
    expect(screen.getByText('衍生自 @backend-engineer')).toBeInTheDocument();

    // Script creator
    expect(screen.getByText('脚本 ci-pipeline.yml')).toBeInTheDocument();

    // System creator
    expect(screen.getByText('系统预设')).toBeInTheDocument();
  });

  it('renders ancestry path breadcrumb for derived grandchild', () => {
    render(<AgentHierarchyTreeView roots={mockForest} />);

    const ancestryElement = screen.getByTestId('ancestry-path-sql-optimizer');
    expect(ancestryElement).toBeInTheDocument();
    expect(ancestryElement).toHaveTextContent('lead-architect');
    expect(ancestryElement).toHaveTextContent('sql-optimizer');
  });

  it('handles expanding and collapsing nodes', () => {
    render(<AgentHierarchyTreeView roots={mockForest} />);

    // Initial: grandchild is rendered
    expect(screen.getByText('SQL Query Tuning Worker')).toBeInTheDocument();

    // Click toggle on backend-engineer to collapse it
    const toggleBackendBtn = screen.getByTestId('toggle-node-backend-engineer');
    fireEvent.click(toggleBackendBtn);

    // Grandchild should be hidden
    expect(screen.queryByText('SQL Query Tuning Worker')).not.toBeInTheDocument();

    // Click toggle again to expand
    fireEvent.click(toggleBackendBtn);
    expect(screen.getByText('SQL Query Tuning Worker')).toBeInTheDocument();

    // Click collapse all button
    const collapseAllBtn = screen.getByTestId('collapse-all-btn');
    fireEvent.click(collapseAllBtn);
    expect(screen.queryByText('Gilfoyle Coder')).not.toBeInTheDocument();

    // Click expand all button
    const expandAllBtn = screen.getByTestId('expand-all-btn');
    fireEvent.click(expandAllBtn);
    expect(screen.getByText('Gilfoyle Coder')).toBeInTheDocument();
    expect(screen.getByText('SQL Query Tuning Worker')).toBeInTheDocument();
  });

  it('handles search input filtering', () => {
    render(<AgentHierarchyTreeView roots={mockForest} />);

    const searchInput = screen.getByTestId('hierarchy-search-input');
    fireEvent.change(searchInput, { target: { value: 'Gilfoyle' } });

    // The node card for backend-engineer should have highlight ring class
    const nodeCard = screen.getByTestId('tree-node-backend-engineer');
    expect(nodeCard.className).toContain('ring-primary');
  });

  it('triggers onSelectAgent when clicking node', () => {
    const onSelectAgent = vi.fn();
    render(<AgentHierarchyTreeView roots={mockForest} onSelectAgent={onSelectAgent} />);

    const nodeName = screen.getByText('Atlas Lead Architect');
    fireEvent.click(nodeName);
    expect(onSelectAgent).toHaveBeenCalledWith('lead-architect');
  });

  it('triggers onRefresh when clicking refresh button', () => {
    const onRefresh = vi.fn();
    render(<AgentHierarchyTreeView roots={mockForest} onRefresh={onRefresh} />);

    const refreshBtn = screen.getByTestId('refresh-hierarchy-btn');
    fireEvent.click(refreshBtn);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});
