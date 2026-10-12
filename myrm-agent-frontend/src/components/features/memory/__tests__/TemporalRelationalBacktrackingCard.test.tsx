/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory/relationalBacktrack::listAllTemporalTriplets, queryRelationalBacktrack, recordTemporalTriplet
 * ../command-center/TemporalRelationalBacktrackingCard::TemporalRelationalBacktrackingCard
 *
 * [OUTPUT]
 * Test suite verifying entity-action-temporal triplet anchoring, dialect synonym expansion,
 * and cross-session entity backtracking with verbatim evidence.
 *
 * [POS]
 * Unit test for Item 100 (TemporalRelationalAnchorAndCrossSessionEntityBacktrackingSuite).
 * Strict typing applied: No `any` types allowed. File lines < 350.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TemporalRelationalBacktrackingCard } from '../command-center/TemporalRelationalBacktrackingCard';
import type {
  RelationalBacktrackResponseDTO,
  TemporalRelationTripletDTO,
} from '@/services/memory/relationalBacktrack';

const {
  mockListAllTemporalTriplets,
  mockQueryRelationalBacktrack,
  mockRecordTemporalTriplet,
} = vi.hoisted(() => ({
  mockListAllTemporalTriplets: vi.fn(),
  mockQueryRelationalBacktrack: vi.fn(),
  mockRecordTemporalTriplet: vi.fn(),
}));

vi.mock('@/services/memory/relationalBacktrack', () => ({
  listAllTemporalTriplets: mockListAllTemporalTriplets,
  queryRelationalBacktrack: mockQueryRelationalBacktrack,
  recordTemporalTriplet: mockRecordTemporalTriplet,
}));

describe('TemporalRelationalBacktrackingCard', () => {
  const sampleTriplets: TemporalRelationTripletDTO[] = [
    {
      triplet_id: 'trip-hotpot-01',
      subject: 'user',
      predicate_action: 'eat_hotpot',
      target_entity: '李总',
      target_entity_type: 'client',
      temporal_anchor: '2026-10-02',
      session_id: 'sess-past-hotpot',
      message_id: 'msg-001',
      verbatim_quote: '下周四带客户李总去吃火锅，预订了川味观。',
      action_synonyms: ['吃火锅', '打边炉', '涮火锅'],
      confidence: 1.0,
      created_at: '2026-10-08T04:00:00Z',
    },
    {
      triplet_id: 'trip-meet-02',
      subject: 'user',
      predicate_action: 'online_meeting',
      target_entity: '王工',
      target_entity_type: 'person',
      temporal_anchor: '2026-10-05',
      session_id: 'sess-past-meeting',
      message_id: 'msg-002',
      verbatim_quote: '下午和技术顾问王工开了线上技术评审会。',
      action_synonyms: ['开会', '语音沟通'],
      confidence: 1.0,
      created_at: '2026-10-08T04:01:00Z',
    },
  ];

  const sampleQueryResult: RelationalBacktrackResponseDTO = {
    hits: [
      {
        triplet: sampleTriplets[0],
        matched_cue: '打边炉',
        match_score: 0.95,
      },
    ],
    total_found: 1,
    inferred_answer:
      '根据 2026-10-02 的历史会话记录，关于【打边炉】关联的 client 是【李总】（出处证据：“下周四带客户李总去吃火锅，预订了川味观”）。',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockListAllTemporalTriplets.mockResolvedValue(sampleTriplets);
    mockQueryRelationalBacktrack.mockResolvedValue(sampleQueryResult);
    mockRecordTemporalTriplet.mockResolvedValue({
      is_success: true,
      triplet: {
        triplet_id: 'trip-sign-03',
        subject: 'user',
        predicate_action: 'sign_contract',
        target_entity: 'Acme Corp',
        target_entity_type: 'client',
        temporal_anchor: '2026-10-08',
        session_id: 'sess-past-sign',
        message_id: 'msg-003',
        verbatim_quote: '今天上午和 Acme Corp 顺利完成了战略框架协议签署。',
        action_synonyms: ['签约', '签合同'],
        confidence: 1.0,
        created_at: '2026-10-08T04:02:00Z',
      },
    });
  });

  it('renders card title, subtitle, and HUD 4-dimensional metrics', async () => {
    render(<TemporalRelationalBacktrackingCard />);

    expect(screen.getByText('Temporal Relational Anchor & Cross-Session Backtracking')).toBeInTheDocument();
    expect(screen.getByText(/Item 100 • Causal Inversion/i)).toBeInTheDocument();
    expect(screen.getByText('Indexed Triplets')).toBeInTheDocument();
    expect(screen.getByText('Entity Disambiguation')).toBeInTheDocument();
    expect(screen.getByText('Backtrack Latency')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Definitive Causal Relational Deduction')).toBeInTheDocument();
      expect(screen.getByText(/关于【打边炉】关联的 client 是【李总】/i)).toBeInTheDocument();
    });
  });

  it('allows querying cross-session backtracking for dialect action cue', async () => {
    render(<TemporalRelationalBacktrackingCard />);

    await waitFor(() => {
      expect(screen.getByText('李总')).toBeInTheDocument();
    });

    const cueInput = screen.getByLabelText(/Colloquial Action Cue/i);
    const form = screen.getByRole('form', { name: 'backtrack-query-form' });

    fireEvent.change(cueInput, { target: { value: '吃火锅' } });
    fireEvent.submit(form);

    await waitFor(() => {
      expect(mockQueryRelationalBacktrack).toHaveBeenCalledWith(
        expect.objectContaining({
          action_cue: '吃火锅',
          target_entity_type: 'client',
        })
      );
    });
  });

  it('triggers quick preset to backtrack entity directly', async () => {
    render(<TemporalRelationalBacktrackingCard />);

    await waitFor(() => {
      expect(screen.getByText('#开会 (Person)')).toBeInTheDocument();
    });

    const presetBtn = screen.getByText('#开会 (Person)');
    fireEvent.click(presetBtn);

    await waitFor(() => {
      expect(mockQueryRelationalBacktrack).toHaveBeenCalledWith(
        expect.objectContaining({
          action_cue: '开会',
          target_entity_type: 'person',
        })
      );
    });
  });

  it('switches to Relational Triplet Anchors tab and displays indexed triplets', async () => {
    render(<TemporalRelationalBacktrackingCard />);

    const anchorTabBtn = screen.getByRole('button', { name: /Relational Triplet Anchors/i });
    fireEvent.click(anchorTabBtn);

    await waitFor(() => {
      expect(screen.getByText('Anchor Structured Entity-Action-Temporal Triplet')).toBeInTheDocument();
      expect(screen.getByText('Indexed Relational Triplets (2)')).toBeInTheDocument();
      expect(screen.getByText('Action: eat_hotpot')).toBeInTheDocument();
      expect(screen.getByText('Action: online_meeting')).toBeInTheDocument();
    });
  });

  it('records a new temporal relation triplet via form submission', async () => {
    render(<TemporalRelationalBacktrackingCard />);

    const anchorTabBtn = screen.getByRole('button', { name: /Relational Triplet Anchors/i });
    fireEvent.click(anchorTabBtn);

    await waitFor(() => {
      expect(screen.getByLabelText(/Predicate Action/i)).toBeInTheDocument();
    });

    const entityInput = screen.getByLabelText(/Target Entity Object/i);
    const quoteInput = screen.getByLabelText(/Verbatim Dialogue Quote/i);
    const form = screen.getByRole('form', { name: 'record-triplet-form' });

    fireEvent.change(entityInput, { target: { value: 'Acme Corp' } });
    fireEvent.change(quoteInput, { target: { value: '签署了框架协议' } });
    fireEvent.submit(form);

    await waitFor(() => {
      expect(mockRecordTemporalTriplet).toHaveBeenCalledWith(
        expect.objectContaining({
          target_entity: 'Acme Corp',
          verbatim_quote: '签署了框架协议',
        })
      );
    });
  });

  it('falls back gracefully to offline defaults if service call fails', async () => {
    mockListAllTemporalTriplets.mockRejectedValue(new Error('Network offline'));

    render(<TemporalRelationalBacktrackingCard />);

    // Debug HTML
    // console.log(document.body.innerHTML);
    await waitFor(() => {
      expect(screen.getByText('Indexed Triplets')).toBeInTheDocument();
      expect(screen.getByText('Definitive Causal Relational Deduction')).toBeInTheDocument();
      expect(screen.getAllByText('李总').length).toBeGreaterThan(0);
    });
  });
});
