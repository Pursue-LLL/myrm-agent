import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { FiveContractDeliveryStatusPanel } from '../FiveContractDeliveryStatusPanel';
import * as chatService from '@/services/chat';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

describe('FiveContractDeliveryStatusPanel', () => {
  it('renders nothing when snapshot is not available', async () => {
    vi.spyOn(chatService, 'getChatDeliveryContracts').mockRejectedValueOnce(new Error('Network error'));
    const { container } = render(<FiveContractDeliveryStatusPanel chatId="chat-1" />);
    await waitFor(() => {
      expect(container.firstChild).toBeNull();
    });
  });

  it('renders 5 contract phases when data is successfully loaded', async () => {
    vi.spyOn(chatService, 'getChatDeliveryContracts').mockResolvedValueOnce({
      contracts: {
        task_intent: {
          phase: 'task_intent',
          status: 'satisfied',
          summary: 'Objective aligned',
          progress_pct: 100,
        },
        scene_environment: {
          phase: 'scene_environment',
          status: 'satisfied',
          summary: 'Sandbox mounted',
          progress_pct: 100,
        },
        action_execution: {
          phase: 'action_execution',
          status: 'in_progress',
          summary: 'Running tools',
          progress_pct: 80,
        },
        delivery_artifact: {
          phase: 'delivery_artifact',
          status: 'pending',
          summary: 'Pending outputs',
          progress_pct: 0,
        },
        acceptance_verification: {
          phase: 'acceptance_verification',
          status: 'pending',
          summary: 'Pending test verification',
          progress_pct: 0,
        },
      },
      current_phase: 'action_execution',
      overall_progress_pct: 56,
      is_fully_satisfied: false,
      has_violations: false,
    });

    render(<FiveContractDeliveryStatusPanel chatId="chat-123" />);

    await waitFor(() => {
      expect(screen.getByText('56%')).toBeInTheDocument();
      expect(screen.getByText('title')).toBeInTheDocument();
    });
  });
});
