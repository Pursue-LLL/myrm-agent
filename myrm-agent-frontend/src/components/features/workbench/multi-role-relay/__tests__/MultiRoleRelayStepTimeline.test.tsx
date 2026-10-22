import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { MultiRoleRelayStepTimeline } from '../MultiRoleRelayStepTimeline';
import { StageArtifactSnapshotViewer } from '../StageArtifactSnapshotViewer';
import { useMultiRoleRelayStore } from '../useMultiRoleRelayStore';

describe('MultiRoleRelayStepTimeline and StageArtifactSnapshotViewer components', () => {
  beforeEach(() => {
    act(() => {
      useMultiRoleRelayStore.getState().resetState();
    });
  });

  describe('MultiRoleRelayStepTimeline', () => {
    it('renders timeline header, progress count and step capsules', () => {
      render(<MultiRoleRelayStepTimeline />);

      expect(
        screen.getByTestId('multi-role-relay-step-timeline')
      ).toBeInTheDocument();
      expect(screen.getByText('多智能体接力流水线')).toBeInTheDocument();
      expect(screen.getByText(/1\/3 棒已交接/)).toBeInTheDocument();
      expect(screen.getByText('1. 调研员')).toBeInTheDocument();
      expect(screen.getByText('2. 分析师')).toBeInTheDocument();
      expect(screen.getByText('3. 撰稿人')).toBeInTheDocument();
      expect(screen.getByText('完成')).toBeInTheDocument();
      expect(screen.getByText('进行中')).toBeInTheDocument();
    });

    it('switches selected snapshot when a stage button is clicked', () => {
      render(<MultiRoleRelayStepTimeline />);

      const analystBtn = screen.getByRole('button', {
        name: '查看第 2 棒 分析师 的交接产物',
      });
      fireEvent.click(analystBtn);

      expect(useMultiRoleRelayStore.getState().selectedSnapshot?.stageId).toBe(
        'stage-analyst'
      );
      expect(useMultiRoleRelayStore.getState().activeStageId).toBe(
        'stage-analyst'
      );
    });

    it('advances pipeline to next stage when advance button is clicked', () => {
      render(<MultiRoleRelayStepTimeline />);

      const advanceBtn = screen.getByRole('button', {
        name: '推进至下一棒角色',
      });
      act(() => {
        fireEvent.click(advanceBtn);
      });

      expect(useMultiRoleRelayStore.getState().activeStageId).toBe(
        'stage-copywriter'
      );
      expect(screen.getByText(/2\/3 棒已交接/)).toBeInTheDocument();
    });
  });

  describe('StageArtifactSnapshotViewer', () => {
    it('renders snapshot metadata, summary and content preview', () => {
      render(<StageArtifactSnapshotViewer />);

      expect(
        screen.getByTestId('stage-artifact-snapshot-viewer')
      ).toBeInTheDocument();
      expect(screen.getByText('竞品全景对比矩阵.json')).toBeInTheDocument();
      expect(screen.getByText('v1.0')).toBeInTheDocument();
      expect(screen.getByText(/调研员交付/)).toBeInTheDocument();
      expect(screen.getByText(/1420 Tokens/)).toBeInTheDocument();
      expect(
        screen.getByText(/已结构化萃取两家头部竞品商业与稳定性基准数据/)
      ).toBeInTheDocument();
    });

    it('opens diff studio when fork button is clicked', () => {
      render(<StageArtifactSnapshotViewer />);

      const forkBtn = screen.getByRole('button', {
        name: '基于当前快照发起分支微调',
      });
      fireEvent.click(forkBtn);

      expect(useMultiRoleRelayStore.getState().isDiffStudioOpen).toBe(true);
    });

    it('renders empty prompt when no snapshot is selected', () => {
      act(() => {
        useMultiRoleRelayStore.setState({ selectedSnapshot: null });
      });

      render(<StageArtifactSnapshotViewer />);
      expect(screen.getByTestId('stage-snapshot-empty')).toBeInTheDocument();
      expect(
        screen.getByText(/请在上方接力时序指示器中点击任意角色/)
      ).toBeInTheDocument();
    });
  });
});
