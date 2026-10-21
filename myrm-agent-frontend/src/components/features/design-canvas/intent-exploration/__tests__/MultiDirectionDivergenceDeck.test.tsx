import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MultiDirectionDivergenceDeck } from '../MultiDirectionDivergenceDeck';
import { useDesignIntentStore } from '../useDesignIntentStore';

describe('MultiDirectionDivergenceDeck', () => {
  beforeEach(() => {
    useDesignIntentStore.getState().reset();
  });

  it('renders nothing when isExplorationOpen is false', () => {
    render(<MultiDirectionDivergenceDeck />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders 3 direction variant cards when opened', () => {
    useDesignIntentStore.getState().generateVariants();
    render(<MultiDirectionDivergenceDeck />);

    expect(screen.getByRole('dialog', { name: '多方向初稿探索选型中枢' })).toBeInTheDocument();
    expect(screen.getByText('多方向初稿铺开与决策选型')).toBeInTheDocument();

    expect(screen.getByText('方向 A · 极简留白典范')).toBeInTheDocument();
    expect(screen.getByText('方向 B · 视觉张力冲击')).toBeInTheDocument();
    expect(screen.getByText('方向 C · 结构卡片阵列')).toBeInTheDocument();
  });

  it('selects variant direction when clicking on card or action button', () => {
    useDesignIntentStore.getState().generateVariants();
    render(<MultiDirectionDivergenceDeck />);

    const boldCard = screen.getByText('方向 B · 视觉张力冲击');
    fireEvent.click(boldCard);

    expect(useDesignIntentStore.getState().selectedVariantId).toBe('direction-b-bold');
  });

  it('closes modal on close button or confirm button click', () => {
    useDesignIntentStore.getState().generateVariants();
    render(<MultiDirectionDivergenceDeck />);

    const confirmBtn = screen.getByText('确认锁定并载入画布深化');
    fireEvent.click(confirmBtn);

    expect(useDesignIntentStore.getState().isExplorationOpen).toBe(false);
  });
});
