import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { UnattendedReliabilityTriadHUD } from '../UnattendedReliabilityTriadHUD';
import type { ReliabilityTriadScoreData } from '../unattendedReliabilityTypes';

describe('UnattendedReliabilityTriadHUD', () => {
  const mockScoreData: ReliabilityTriadScoreData = {
    total_evaluated_runs: 25,
    resume_rate_pct: 100.0,
    zero_duplicate_side_effect_rate_pct: 100.0,
    honest_blocker_rate_pct: 96.0,
    composite_triad_score: 98.6,
    hallucinated_success_count: 0,
    duplicate_side_effect_count: 0,
    failed_resume_count: 0,
    recent_records: [
      {
        run_id: 'run_bench_01',
        task_name: 'Sandbox restart after kill',
        resume_status: 'RESUMED_SUCCESS',
        side_effect_status: 'ZERO_DUPLICATE',
        reporting_status: 'GENUINE_SUCCESS',
        detail: 'Durable Guardian checkpoint recovered',
        timestamp_ms: 1710000001000,
      },
      {
        run_id: 'run_bench_02',
        task_name: 'Missing API key gate',
        resume_status: 'NOT_APPLICABLE',
        side_effect_status: 'NO_SIDE_EFFECTS',
        reporting_status: 'HONEST_BLOCKER',
        detail: 'Truthfully reported missing secret',
        timestamp_ms: 1710000002000,
      },
    ],
  };

  it('renders triad composite score, three pillars, and run records', () => {
    const onRefresh = vi.fn();
    const onRunBenchmark = vi.fn();
    const onReset = vi.fn();

    render(
      <UnattendedReliabilityTriadHUD
        scoreData={mockScoreData}
        onRefresh={onRefresh}
        onRunBenchmark={onRunBenchmark}
        onReset={onReset}
      />
    );

    // 标题与工业级徽标
    expect(
      screen.getByText('无人值守可靠性三联自证 HUD (Unattended Reliability Triad)')
    ).toBeInTheDocument();
    expect(screen.getByText('工业级无人值守 (Production-Grade)')).toBeInTheDocument();

    // 核心卡片
    expect(screen.getByText('98.6')).toBeInTheDocument();
    expect(screen.getByText('已评估任务: 25 次')).toBeInTheDocument();
    expect(screen.getByText(/1. 重启后续跑率/)).toBeInTheDocument();
    expect(screen.getByText(/2. 零重复副作用率/)).toBeInTheDocument();
    expect(screen.getByText(/3. 阻断如实上报率/)).toBeInTheDocument();

    // 运行事实审计列表
    expect(screen.getByText('Sandbox restart after kill')).toBeInTheDocument();
    expect(screen.getByText('Missing API key gate')).toBeInTheDocument();
    expect(screen.getByText('RESUMED_SUCCESS')).toBeInTheDocument();
    expect(screen.getByText('HONEST_BLOCKER')).toBeInTheDocument();
  });

  it('triggers onRunBenchmark callback when clicking benchmark button', async () => {
    const onRunBenchmark = vi.fn().mockResolvedValue(undefined);

    render(
      <UnattendedReliabilityTriadHUD
        scoreData={mockScoreData}
        onRunBenchmark={onRunBenchmark}
      />
    );

    const benchBtn = screen.getByRole('button', { name: /复跑自证验收用例/ });
    await React.act(async () => {
      fireEvent.click(benchBtn);
    });

    expect(onRunBenchmark).toHaveBeenCalledTimes(1);
  });

  it('triggers onRefresh and onReset callbacks', () => {
    const onRefresh = vi.fn();
    const onReset = vi.fn();

    render(
      <UnattendedReliabilityTriadHUD
        scoreData={mockScoreData}
        onRefresh={onRefresh}
        onReset={onReset}
      />
    );

    const refreshBtn = screen.getByRole('button', { name: '刷新' });
    fireEvent.click(refreshBtn);
    expect(onRefresh).toHaveBeenCalledTimes(1);

    const resetBtn = screen.getByRole('button', { name: '重置' });
    fireEvent.click(resetBtn);
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it('renders alert badge when composite score drops below 80', () => {
    const degradedScoreData: ReliabilityTriadScoreData = {
      ...mockScoreData,
      composite_triad_score: 65.0,
      hallucinated_success_count: 3,
    };

    render(<UnattendedReliabilityTriadHUD scoreData={degradedScoreData} />);
    expect(screen.getByText('⚠️ 可靠性隐患 (Reliability Alert)')).toBeInTheDocument();
  });
});
