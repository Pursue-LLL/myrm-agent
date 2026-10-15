import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { RadialStarMapCanvas } from '../RadialStarMapCanvas';
import { StarMapPlaybackController } from '../StarMapPlaybackController';
import { StarMapNodeDetailSheet } from '../StarMapNodeDetailSheet';
import { useStarMapStore } from '../useStarMapStore';
import { INITIAL_STAR_MAP_NODES } from '../starMapCatalogData';

describe('Star Map Visualizer Components', () => {
  beforeEach(() => {
    act(() => {
      useStarMapStore.getState().resetState();
    });
  });

  describe('RadialStarMapCanvas Component', () => {
    it('renders the SVG star map canvas with concentric rings and legend', () => {
      render(<RadialStarMapCanvas />);

      expect(screen.getByTestId('radial-star-map-canvas')).toBeInTheDocument();
      expect(screen.getByText('AI 学习星图与演化全景')).toBeInTheDocument();
      expect(screen.getByText(/金星 = 技能 · 蓝钻 = 记忆/)).toBeInTheDocument();
      expect(screen.getByTestId('star-map-svg-container')).toBeInTheDocument();
      expect(screen.getByText('初创原点')).toBeInTheDocument();
      expect(screen.getByText('前沿最新')).toBeInTheDocument();
    });

    it('toggles privacy label hiding mode', () => {
      render(<RadialStarMapCanvas />);

      const privacyBtn = screen.getByRole('button', { name: '隐藏文本以脱敏' });
      fireEvent.click(privacyBtn);

      expect(useStarMapStore.getState().filter.hideLabels).toBe(true);
      expect(screen.getByText('脱敏中 (无文字)')).toBeInTheDocument();

      const showBtn = screen.getByRole('button', { name: '显示节点文本' });
      fireEvent.click(showBtn);

      expect(useStarMapStore.getState().filter.hideLabels).toBe(false);
      expect(screen.getByText('明文显示')).toBeInTheDocument();
    });

    it('switches between star map and list views', () => {
      render(<RadialStarMapCanvas />);

      const listBtn = screen.getByRole('button', { name: '切换至列表视图' });
      fireEvent.click(listBtn);

      expect(useStarMapStore.getState().viewMode).toBe('list');
      expect(screen.getByTestId('star-map-list-view')).toBeInTheDocument();

      const mapBtn = screen.getByRole('button', { name: '切换至星图视图' });
      fireEvent.click(mapBtn);

      expect(useStarMapStore.getState().viewMode).toBe('map');
      expect(screen.getByTestId('star-map-svg-container')).toBeInTheDocument();
    });

    it('opens detail sheet on node click and highlights on hover', () => {
      render(<RadialStarMapCanvas />);

      const firstNode = INITIAL_STAR_MAP_NODES[0];
      const nodeEl = screen.getByTestId(`star-node-${firstNode.id}`);

      fireEvent.mouseEnter(nodeEl);
      expect(useStarMapStore.getState().hoveredNodeId).toBe(firstNode.id);

      fireEvent.mouseLeave(nodeEl);
      expect(useStarMapStore.getState().hoveredNodeId).toBeNull();

      fireEvent.click(nodeEl);
      expect(useStarMapStore.getState().isDetailSheetOpen).toBe(true);
      expect(useStarMapStore.getState().selectedNodeId).toBe(firstNode.id);
    });

    it('handles image export action', async () => {
      const eventSpy = vi.fn();
      window.addEventListener('myrm:star-map-image-exported', eventSpy);

      render(<RadialStarMapCanvas />);

      const exportBtn = screen.getByRole('button', { name: '导出星图图片' });
      fireEvent.click(exportBtn);

      expect(eventSpy).toHaveBeenCalledTimes(1);

      window.removeEventListener('myrm:star-map-image-exported', eventSpy);
    });
  });

  describe('StarMapPlaybackController Component', () => {
    it('renders scope filter tabs and handles selection', () => {
      render(<StarMapPlaybackController />);

      expect(screen.getByTestId('star-map-playback-controller')).toBeInTheDocument();

      const usedTab = screen.getByRole('button', { name: '已高频使用' });
      fireEvent.click(usedTab);

      expect(useStarMapStore.getState().filter.scope).toBe('used');
    });

    it('toggles playback play and pause', () => {
      render(<StarMapPlaybackController />);

      const playBtn = screen.getByRole('button', { name: '开始时间线回放' });
      fireEvent.click(playBtn);

      expect(useStarMapStore.getState().playback.isPlaying).toBe(true);

      const pauseBtn = screen.getByRole('button', { name: '暂停回放' });
      fireEvent.click(pauseBtn);

      expect(useStarMapStore.getState().playback.isPlaying).toBe(false);
    });

    it('switches playback speed multiplier', () => {
      render(<StarMapPlaybackController />);

      const speedBtn = screen.getByRole('button', { name: '2x' });
      fireEvent.click(speedBtn);

      expect(useStarMapStore.getState().playback.playbackSpeed).toBe(2);
    });

    it('handles timeline slider change and reset button', () => {
      render(<StarMapPlaybackController />);

      const slider = screen.getByRole('slider', { name: '回放时间进度滑块' });
      fireEvent.change(slider, { target: { value: '0.4' } });

      expect(useStarMapStore.getState().playback.currentProgress).toBe(0.4);

      const resetBtn = screen.getByRole('button', { name: '重置时间游标到原点' });
      fireEvent.click(resetBtn);

      expect(useStarMapStore.getState().playback.currentProgress).toBe(0);
    });
  });

  describe('StarMapNodeDetailSheet Component', () => {
    it('does not render when isDetailSheetOpen is false', () => {
      render(<StarMapNodeDetailSheet />);
      expect(screen.queryByTestId('star-map-detail-sheet')).toBeNull();
    });

    it('renders detail sheet for selected skill node', () => {
      act(() => {
        useStarMapStore.getState().openDetailSheet(INITIAL_STAR_MAP_NODES[0].id);
      });

      render(<StarMapNodeDetailSheet />);

      expect(screen.getByTestId('star-map-detail-sheet')).toBeInTheDocument();
      expect(screen.getByText('TypeScript Clean Architecture 审查')).toBeInTheDocument();
      expect(screen.getByText('技能实体')).toBeInTheDocument();
      expect(screen.getByText('38 次')).toBeInTheDocument();
      expect(screen.getByText('chat-sess-1029')).toBeInTheDocument();

      const closeBtn = screen.getByRole('button', { name: '关闭节点详情' });
      fireEvent.click(closeBtn);

      expect(useStarMapStore.getState().isDetailSheetOpen).toBe(false);
    });

    it('navigates to neighbor node upon clicking related node item', () => {
      act(() => {
        useStarMapStore.getState().openDetailSheet('skill-ts-clean-arch');
      });

      render(<StarMapNodeDetailSheet />);

      // Find neighbor in the list
      const neighborItem = screen.getByText('WCAG 语义化与 a11y 自动化断言');
      fireEvent.click(neighborItem);

      expect(useStarMapStore.getState().selectedNodeId).toBe('skill-vitest-a11y');
    });
  });
});
