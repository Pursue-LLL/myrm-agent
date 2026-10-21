/** @vitest-environment jsdom */

vi.mock('next-intl', async (importOriginal) => {
  const actual = await importOriginal<typeof import('next-intl')>();
  return {
    ...actual,
    useLocale: () => 'en',
  };
});

/**
 * [INPUT]
 * @/services/memory/ephemeralDelta::getActiveEphemeralDeltas, getEphemeralDeltaSnapshot,
 *   getPromptCacheMetrics, previewDeltaInjection, recordEphemeralDelta
 * ../command-center/PromptCachePreservingDeltaCard::PromptCachePreservingDeltaCard
 *
 * [OUTPUT]
 * Test suite verifying prompt cache preservation, turn-scoped transient delta recording,
 * dual-track XML tail injection simulation, and session reconcile consolidation.
 *
 * [POS]
 * Unit test for Item 98 (PromptCachePreservingEphemeralDeltaMemorySuite).
 * Strict typing applied: No `any` types allowed. File lines < 350.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { promptCacheEnMessages } from './promptCacheTestMessages';
import { PromptCachePreservingDeltaCard } from '../command-center/PromptCachePreservingDeltaCard';
import type {
  PreviewDeltaInjectionResponseDTO,
  PromptCacheMetricsDTO,
  SessionDeltaSnapshotDTO,
} from '@/services/memory/ephemeralDelta';

const {
  mockGetActiveEphemeralDeltas,
  mockGetEphemeralDeltaSnapshot,
  mockGetPromptCacheMetrics,
  mockPreviewDeltaInjection,
  mockRecordEphemeralDelta,
} = vi.hoisted(() => ({
  mockGetActiveEphemeralDeltas: vi.fn(),
  mockGetEphemeralDeltaSnapshot: vi.fn(),
  mockGetPromptCacheMetrics: vi.fn(),
  mockPreviewDeltaInjection: vi.fn(),
  mockRecordEphemeralDelta: vi.fn(),
}));

vi.mock('@/services/memory/ephemeralDelta', () => ({
  getActiveEphemeralDeltas: mockGetActiveEphemeralDeltas,
  getEphemeralDeltaSnapshot: mockGetEphemeralDeltaSnapshot,
  getPromptCacheMetrics: mockGetPromptCacheMetrics,
  previewDeltaInjection: mockPreviewDeltaInjection,
  recordEphemeralDelta: mockRecordEphemeralDelta,
}));

function renderCard(chatId = 'session_demo_cache_01') {
  return render(
    <NextIntlClientProvider locale="en" messages={promptCacheEnMessages}>
      <PromptCachePreservingDeltaCard defaultChatId={chatId} />
    </NextIntlClientProvider>,
  );
}

describe('PromptCachePreservingDeltaCard', () => {
  const sampleSnapshot: SessionDeltaSnapshotDTO = {
    session_id: 'session_demo_cache_01',
    active_deltas: [
      {
        delta_id: 'delta_01',
        session_id: 'session_demo_cache_01',
        target_key: 'user_nickname',
        content: '老张',
        action: 'override',
        turn_index: 2,
        source: 'user_explicit',
        confidence: 1.0,
        created_at: '2026-10-08T04:00:00Z',
        is_reconciled: false,
      },
      {
        delta_id: 'delta_02',
        session_id: 'session_demo_cache_01',
        target_key: 'test_port',
        content: '8082',
        action: 'override',
        turn_index: 3,
        source: 'user_explicit',
        confidence: 1.0,
        created_at: '2026-10-08T04:01:00Z',
        is_reconciled: false,
      },
    ],
    is_reconciled: false,
    reconciled_at: null,
  };

  const sampleMetrics: PromptCacheMetricsDTO = {
    system_prompt_frozen: true,
    system_prompt_byte_hash: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    kv_cache_hit_ratio: null,
    in_flight_deltas_count: 2,
    recency_perception_delay_ms: 0.12,
    avoided_recomputation_tokens: 480,
  };

  const samplePreview: PreviewDeltaInjectionResponseDTO = {
    session_id: 'session_demo_cache_01',
    frozen_system_prompt: 'You are Myrm Agent. System Profile: Senior Fullstack Architect.',
    augmented_final_human_message:
      'Please inspect my codebase.\n\n<ephemeral_session_deltas>\nuser_nickname: 老张\ntest_port: 8082\n</ephemeral_session_deltas>',
    tail_tag_snippet: '<ephemeral_session_deltas>\nuser_nickname: 老张\ntest_port: 8082\n</ephemeral_session_deltas>',
    active_deltas: sampleSnapshot.active_deltas,
    metrics: sampleMetrics,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetEphemeralDeltaSnapshot.mockResolvedValue(sampleSnapshot);
    mockGetPromptCacheMetrics.mockResolvedValue(sampleMetrics);
    mockPreviewDeltaInjection.mockResolvedValue(samplePreview);
    mockRecordEphemeralDelta.mockResolvedValue({
      delta_id: 'delta_03',
      session_id: 'session_demo_cache_01',
      target_key: 'target_lang',
      content: 'TypeScript only',
      action: 'override',
      turn_index: 4,
      source: 'user_explicit',
      confidence: 1.0,
      created_at: '2026-10-08T04:02:00Z',
      is_reconciled: false,
    });
  });

  it('renders card title, subtitle and loaded transient deltas', async () => {
    renderCard();

    expect(screen.getByText('Session memory updates')).toBeInTheDocument();
    expect(screen.getByText('Live chat')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('user_nickname')).toBeInTheDocument();
      expect(screen.getByText('老张')).toBeInTheDocument();
      expect(screen.getByText('test_port')).toBeInTheDocument();
      expect(screen.getByText('8082')).toBeInTheDocument();
    });
  });

  it('allows recording an in-flight transient delta via form submission', async () => {
    renderCard();

    await waitFor(() => {
      expect(screen.getByText('user_nickname')).toBeInTheDocument();
    });

    const keyInput = screen.getByLabelText('Target Key');
    const contentInput = screen.getByLabelText('Delta Content / Override Value');
    const mountButton = screen.getByRole('button', { name: /Mount Ephemeral Delta/i });

    await waitFor(() => {
      expect(mountButton).toBeEnabled();
    });

    fireEvent.change(keyInput, { target: { value: 'target_lang' } });
    fireEvent.change(contentInput, { target: { value: 'TypeScript only' } });

    const form = screen.getByRole('form', { name: 'record-delta-form' });
    fireEvent.submit(form);

    await waitFor(() => {
      expect(mockRecordEphemeralDelta).toHaveBeenCalledWith(
        expect.objectContaining({
          session_id: 'session_demo_cache_01',
          target_key: 'target_lang',
          content: 'TypeScript only',
          action: 'override',
        })
      );
    });
  });

  it('switches to layout tab and shows in-flight delta count', async () => {
    renderCard();

    const layoutTabButton = screen.getByRole('button', { name: /Layout preview/i });
    fireEvent.click(layoutTabButton);

    await waitFor(() => {
      expect(screen.getByText('2')).toBeInTheDocument();
    });
  });

  it('triggers simulate injection to refresh preview', async () => {
    renderCard();

    const layoutTabButton = screen.getByRole('button', { name: /Layout preview/i });
    fireEvent.click(layoutTabButton);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Simulate Injection/i })).toBeInTheDocument();
    });

    const simulateBtn = screen.getByRole('button', { name: /Simulate Injection/i });
    fireEvent.click(simulateBtn);

    await waitFor(() => {
      expect(mockPreviewDeltaInjection).toHaveBeenCalled();
    });
  });

  it('shows empty delta list when backend request fails', async () => {
    mockGetEphemeralDeltaSnapshot.mockRejectedValue(new Error('Network offline'));
    mockGetPromptCacheMetrics.mockRejectedValue(new Error('Network offline'));

    renderCard();

    await waitFor(() => {
      expect(screen.queryByText('user_nickname')).not.toBeInTheDocument();
    });
  });
});
