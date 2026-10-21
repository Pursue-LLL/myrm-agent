import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DualOrthogonalReviewerCard } from '../DualOrthogonalReviewerCard';

describe('DualOrthogonalReviewerCard', () => {
  it('renders card header, dual reviewer panels, arbiter verdict, and live accessible output', () => {
    render(<DualOrthogonalReviewerCard />);

    // 1. Header & Title
    expect(screen.getByTestId('dual-orthogonal-reviewer-card')).toBeInTheDocument();
    expect(
      screen.getByText('DualOrthogonalReviewerGateWithBlindCleanContextSubagent'),
    ).toBeInTheDocument();
    expect(screen.getByText('P0 质量门禁守卫')).toBeInTheDocument();

    // 2. Dual Reviewer Panels
    expect(screen.getByTestId('reviewer-a-panel')).toBeInTheDocument();
    expect(screen.getByText('Reviewer A · 意图一致性审查')).toBeInTheDocument();
    expect(screen.getByTestId('reviewer-b-panel')).toBeInTheDocument();
    expect(screen.getByText('Reviewer B · 盲态无偏代码审查')).toBeInTheDocument();
    expect(screen.getByTestId('blind-context-tag')).toHaveTextContent('CLEAN CONTEXT');

    // 3. Initial Arbiter Verdict (Admitted)
    const arbiterBadge = screen.getByTestId('arbiter-decision-badge');
    expect(arbiterBadge).toHaveTextContent('admitted');
    expect(screen.getByText('双审通过 · 准入合流 (ADMITTED)')).toBeInTheDocument();

    // 4. Live Output
    const liveOutput = screen.getByTestId('orthogonal-reviewer-status-live');
    expect(liveOutput).toHaveTextContent('正交双视角审查门禁已就绪');
  });

  it('triggers Intent Drift scenario and reflects Reviewer A blockers and auto-fix prompts', () => {
    render(<DualOrthogonalReviewerCard />);

    // Click Intent Drift Scenario button
    fireEvent.click(screen.getByText('意图偏离拦截 (Drift)'));

    // Arbiter decision should be BLOCKED
    const arbiterBadge = screen.getByTestId('arbiter-decision-badge');
    expect(arbiterBadge).toHaveTextContent('blocked');
    expect(screen.getByText('双审拦截 · 阻断合流 (BLOCKED)')).toBeInTheDocument();

    // Blocker Reasons Panel
    expect(screen.getByTestId('blocker-reasons-panel')).toBeInTheDocument();
    expect(screen.getByText(/缺少落盘对账机制/i)).toBeInTheDocument();

    // Auto-fix Prompts
    expect(screen.getByTestId('autofix-prompts-section')).toBeInTheDocument();
    expect(screen.getByText(/FIX\(intent_drift\)/i)).toBeInTheDocument();

    // Live Output
    expect(screen.getByTestId('orthogonal-reviewer-status-live')).toHaveTextContent(
      '警报：Reviewer A 意图核验未通过，阻断门禁生效',
    );
  });

  it('triggers Blind Safety scenario and catches forbidden Any types and edge case faults', () => {
    render(<DualOrthogonalReviewerCard />);

    // Click Blind Safety Scenario button
    fireEvent.click(screen.getByText('盲审类型拦截 (Type/Bound)'));

    // Arbiter decision should be BLOCKED
    expect(screen.getByTestId('arbiter-decision-badge')).toHaveTextContent('blocked');

    // Reviewer B findings
    expect(screen.getByText('禁止使用 Any 类型')).toBeInTheDocument();
    expect(screen.getByText('未防除零异常')).toBeInTheDocument();

    // Blocker Reasons Panel
    expect(screen.getByText(/Reviewer B \(Blind\): \[TYPE_SAFETY\] 禁止使用 Any 类型/i)).toBeInTheDocument();
    expect(screen.getByText(/Reviewer B \(Blind\): \[BOUNDARY_EDGE_CASE\] 未防除零异常/i)).toBeInTheDocument();

    // Live Output
    expect(screen.getByTestId('orthogonal-reviewer-status-live')).toHaveTextContent(
      '警报：Reviewer B 盲审拦截类型逃逸与边界隐患',
    );
  });

  it('triggers Double Blocker and supports dispatching auto-fix instructions', () => {
    render(<DualOrthogonalReviewerCard />);

    // Click Double Blocker button
    fireEvent.click(screen.getByText('双重致命阻断 (Double Block)'));

    expect(screen.getByTestId('arbiter-decision-badge')).toHaveTextContent('blocked');
    expect(screen.getByTestId('orthogonal-reviewer-status-live')).toHaveTextContent(
      '严重警报：双审双重视角均触发 Critical 阻断，系统禁止合流！',
    );

    // Dispatch Auto Fix
    const dispatchButtons = screen.getAllByRole('button', { name: /执行自动修复指令/i });
    expect(dispatchButtons.length).toBeGreaterThan(0);
    fireEvent.click(dispatchButtons[0]);

    // Live status should reflect dispatched fix
    expect(screen.getByTestId('orthogonal-reviewer-status-live')).toHaveTextContent('已派发自愈修复指令');
  });

  it('resets back to clean admitted state when clicking clean scenario button', () => {
    render(<DualOrthogonalReviewerCard />);

    // First drift
    fireEvent.click(screen.getByText('意图偏离拦截 (Drift)'));
    expect(screen.getByTestId('arbiter-decision-badge')).toHaveTextContent('blocked');

    // Reset to clean
    fireEvent.click(screen.getByText('双审全通 (Admitted)'));
    expect(screen.getByTestId('arbiter-decision-badge')).toHaveTextContent('admitted');
    expect(screen.queryByTestId('blocker-reasons-panel')).not.toBeInTheDocument();
    expect(screen.queryByTestId('autofix-prompts-section')).not.toBeInTheDocument();
    expect(screen.getByTestId('orthogonal-reviewer-status-live')).toHaveTextContent(
      '双重视角均绿灯通过，仲裁器已核发准入凭据 (ADMITTED)',
    );
  });
});
