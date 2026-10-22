import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EventCausalityLineageDeck } from '../EventCausalityLineageDeck';
import {
  CausalityLineageRecordItem,
  FileAttributionResultItem,
} from '../eventCausalityLineageTypes';

describe('EventCausalityLineageDeck Component', () => {
  const mockLineages: CausalityLineageRecordItem[] = [
    {
      causality_trace_id: 'trace-gh-404-fix',
      session_id: 'sess-sec-99',
      trigger: {
        event_id: 'gh-evt-1001',
        source_type: 'github_webhook',
        event_name: 'issues.labeled',
        payload_summary: 'Bug label added to issue #404: NullPointerException in auth service',
        received_at_ms: 1700000000000,
      },
      rule: {
        rule_id: 'rule-auto-patch',
        rule_name: 'Auto Issue Triage & Self-Healing',
        matched_condition: "event.label == 'bug' && target.service == 'auth'",
      },
      agent_role: 'Security Lead',
      actions: [
        {
          action_id: 'act-1',
          agent_role: 'Codebase Investigator',
          decision_rationale: 'Analyze stack trace and locate missing null check in auth parser',
          tool_name: 'search_codebase',
          input_summary: "pattern='AuthTokenParser.parse'",
          duration_ms: 420.5,
          tokens_consumed: 1250,
          timestamp_ms: 1700000001000,
        },
      ],
      artifacts: [
        {
          file_path: 'auth/parser.py',
          change_type: 'modified',
          diff_summary: '+ if not raw_token: return None',
          commit_sha: 'a1b2c3d4e5f6',
          timestamp_ms: 1700000002500,
        },
      ],
      total_tokens: 1250,
      total_duration_ms: 420.5,
      created_at_ms: 1700000003000,
    },
    {
      causality_trace_id: 'trace-cron-vacuum',
      session_id: 'sess-ops-10',
      trigger: {
        event_id: 'cron-midnight-1',
        source_type: 'cron',
        event_name: 'schedule.cleanup',
        payload_summary: 'Nightly vacuum db and purge temporary caches',
        received_at_ms: 1700005000000,
      },
      rule: {
        rule_id: 'rule-nightly-maintenance',
        rule_name: 'Scheduled Housekeeping',
        matched_condition: 'cron.hour == 0',
      },
      agent_role: 'DevOps Custodian',
      actions: [],
      artifacts: [],
      total_tokens: 300,
      total_duration_ms: 150.0,
      created_at_ms: 1700005001000,
    },
  ];

  it('renders header, causality breadcrumb, and DAG nodes for selected trace', () => {
    render(<EventCausalityLineageDeck lineages={mockLineages} />);

    expect(screen.getByText('事件驱动因果溯源与动作归因图谱')).toBeInTheDocument();
    expect(screen.getByText('已捕获因果链 (2)')).toBeInTheDocument();

    // Check DAG nodes
    expect(screen.getAllByText('issues.labeled').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Auto Issue Triage & Self-Healing')).toBeInTheDocument();
    expect(screen.getByText('Analyze stack trace and locate missing null check in auth parser')).toBeInTheDocument();
    expect(screen.getByText('auth/parser.py')).toBeInTheDocument();
    expect(screen.getByText('+ if not raw_token: return None')).toBeInTheDocument();
  });

  it('switches trace selection when clicking trace card', async () => {
    const handleSelect = vi.fn();
    render(<EventCausalityLineageDeck lineages={mockLineages} onSelectTrace={handleSelect} />);

    const cronCard = screen.getByText('schedule.cleanup');
    await React.act(async () => {
      fireEvent.click(cronCard);
    });

    expect(handleSelect).toHaveBeenCalledWith('trace-cron-vacuum');
    expect(screen.getByText('Scheduled Housekeeping')).toBeInTheDocument();
  });

  it('handles reverse file attribution lookup and returns results', async () => {
    const mockLookupResults: FileAttributionResultItem[] = [
      {
        file_path: 'auth/parser.py',
        causality_trace_id: 'trace-gh-404-fix',
        trigger_event_id: 'gh-evt-1001',
        source_type: 'github_webhook',
        event_name: 'issues.labeled',
        agent_role: 'Patch Engineer',
        change_record: {
          file_path: 'auth/parser.py',
          change_type: 'modified',
          diff_summary: '+ if not raw_token: return None',
          commit_sha: 'a1b2c3d4e5f6',
          timestamp_ms: 1700000002500,
        },
        rationale: 'Inject safe guard null check before decrypting token payload',
        occurred_at_ms: 1700000002500,
      },
    ];

    const mockReverseLookup = vi.fn().mockResolvedValue(mockLookupResults);

    render(
      <EventCausalityLineageDeck
        lineages={mockLineages}
        onReverseLookupFile={mockReverseLookup}
      />
    );

    const input = screen.getByPlaceholderText('输入文件路径反查因果...');
    fireEvent.change(input, { target: { value: 'auth/parser.py' } });

    const searchBtn = screen.getByRole('button', { name: '反向归因' });
    await React.act(async () => {
      fireEvent.click(searchBtn);
    });

    expect(mockReverseLookup).toHaveBeenCalledWith('auth/parser.py');
    expect(screen.getByText('文件倒排反向归因结果：auth/parser.py')).toBeInTheDocument();
    expect(screen.getByText('命中 1 次由外部事件驱动的变更记录')).toBeInTheDocument();
    expect(screen.getByText('Inject safe guard null check before decrypting token payload')).toBeInTheDocument();

    // Click back to main lineage
    const backBtn = screen.getByRole('button', { name: '返回主链路' });
    await React.act(async () => {
      fireEvent.click(backBtn);
    });

    expect(screen.queryByText('文件倒排反向归因结果：auth/parser.py')).not.toBeInTheDocument();
  });
});
