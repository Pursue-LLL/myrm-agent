import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ApprovalPayloadData } from '@/store/useApprovalStore';
import { HighRiskDomActionContent } from '../HighRiskDomActionContent';
import { BARE_DESTRUCTIVE_TEXT, makeApproval } from './approvalKit';
import { propsOf } from './approvalStubs';

vi.mock('next-intl', async () => (await import('./approvalStubs')).nextIntlModule);
vi.mock(
  '@/components/approval/HighRiskEvidenceScreenshot',
  async () => (await import('./approvalStubs')).evidenceScreenshotModule,
);

afterEach(cleanup);

const highRisk = (payload: ApprovalPayloadData = {}, reason?: string) =>
  render(<HighRiskDomActionContent approval={makeApproval('high_risk_dom_action', payload, { reason })} />);

/** Everything coloured as destructive text: the warning icon and texts, and the key icons. */
const destructiveTextSites = (container: HTMLElement) => container.querySelectorAll('.text-destructive-text').length;

describe('HighRiskDomActionContent', () => {
  it('headlines the warning with the reason of the approval, or else the one of the payload', () => {
    highRisk({ reason: 'payload reason' }, 'approval reason');
    expect(screen.getByText('toolApproval.highRiskDomAction')).toBeDefined();
    expect(screen.getByText('approval reason')).toBeDefined();
    expect(screen.queryByText('payload reason')).toBeNull();
    cleanup();

    highRisk({ reason: 'payload reason' });
    expect(screen.getByText('payload reason')).toBeDefined();
  });

  it('shows the target element with its role, name and reference', () => {
    highRisk({ element: { role: 'button', name: 'Delete account', ref: 'e12' } });

    expect(screen.getByText('toolApproval.targetElement')).toBeDefined();
    expect(screen.getByText('button')).toBeDefined();
    expect(screen.getByText('"Delete account"')).toBeDefined();
    expect(screen.getByText('ref: e12')).toBeDefined();
    expect(document.querySelector('kbd')).toBeNull();
  });

  it('shows the key a keyboard action presses, on the element and in the action', () => {
    const { container } = highRisk({
      element: { role: 'textbox', name: 'Search', ref: 'e3', key: 'Enter' },
      tool_input: { action: 'press', ref: 'e3', text: 'Enter' },
    });

    expect(document.querySelector('kbd')?.textContent).toBe('Enter');
    expect(screen.getByText('toolApproval.keyActivation')).toBeDefined();
    expect(screen.queryByText('toolApproval.action')).toBeNull();
    expect(screen.getByText('press(e3, "Enter")')).toBeDefined();
    expect(destructiveTextSites(container)).toBe(5);
  });

  it('takes the key from the element when the action does not name one', () => {
    highRisk({ element: { role: 'textbox', name: 'Search', ref: 'e3', key: 'Tab' } });

    expect(document.querySelector('kbd')?.textContent).toBe('Tab');
  });

  it('takes the key from the action before the one of the element', () => {
    highRisk({
      element: { role: 'textbox', name: 'Search', ref: 'e3', key: 'Tab' },
      tool_input: { action: 'press', ref: 'e3', text: 'Enter' },
    });

    expect(document.querySelector('kbd')?.textContent).toBe('Enter');
  });

  it.each([
    ['the action presses a key', { tool_input: { action: 'press', ref: 'e3', text: 'Enter' } }],
    [
      'the element carries a key',
      {
        element: { role: 'textbox', name: 'Search', ref: 'e3', key: 'Tab' },
        tool_input: { action: 'click', ref: 'e3' },
      },
    ],
  ])('treats the action as a key activation when %s', (_, payload) => {
    highRisk(payload);

    expect(screen.getByText('toolApproval.keyActivation')).toBeDefined();
    expect(screen.queryByText('toolApproval.action')).toBeNull();
  });

  it('shows a click as an action with its reference, without key styling', () => {
    const { container } = highRisk({
      element: { role: 'button', name: 'Buy', ref: 'e7' },
      tool_input: { action: 'click', ref: 'e7' },
    });

    expect(screen.getByText('toolApproval.action')).toBeDefined();
    expect(screen.queryByText('toolApproval.keyActivation')).toBeNull();
    expect(screen.getByText('click(e7)')).toBeDefined();
    expect(destructiveTextSites(container)).toBe(3);
  });

  it('shows the JavaScript expression instead of an action when the action carries one', () => {
    highRisk({ tool_input: { action: 'evaluate', expression: 'document.cookie' } });

    expect(screen.getByText('toolApproval.jsExpression')).toBeDefined();
    expect(screen.getByText('document.cookie')).toBeDefined();
    expect(screen.queryByText('toolApproval.action')).toBeNull();
  });

  it('shows the app and window of a desktop action, and the page of a browser action', () => {
    highRisk({ app_name: 'Finder', window_title: 'Trash', page_url: 'https://example.com/pay' });

    expect(screen.getByText('Finder — Trash').getAttribute('title')).toBe('Finder — Trash');
    expect(screen.getByText('https://example.com/pay').getAttribute('title')).toBe('https://example.com/pay');
  });

  it('shows no page row without a page URL', () => {
    const { container } = highRisk();

    expect(container.querySelector('[title]')).toBeNull();
  });

  it('shows a lone app name or window title without a separator', () => {
    highRisk({ app_name: 'Finder' });
    expect(screen.getByText('Finder').getAttribute('title')).toBe('Finder');
    cleanup();

    highRisk({ window_title: 'Trash' });
    expect(screen.getByText('Trash').textContent).toBe('Trash');
  });

  describe('evidence screenshot', () => {
    it('is shown with its size and the highlighted point', () => {
      highRisk({ screenshot_base64: 'AAAA', screenshot_size: [1280, 720], highlight_coordinate: [40, 60] });

      expect(propsOf(screen.getByTestId('HighRiskEvidenceScreenshot'))).toEqual({
        screenshotBase64: 'AAAA',
        screenshotWidth: 1280,
        screenshotHeight: 720,
        highlightX: 40,
        highlightY: 60,
      });
    });

    it('is shown without a highlight when the action has no point', () => {
      highRisk({ screenshot_base64: 'AAAA', screenshot_size: [10, 20] });

      const props = propsOf(screen.getByTestId('HighRiskEvidenceScreenshot'));
      expect(props.highlightX).toBeUndefined();
      expect(props.highlightY).toBeUndefined();
    });

    it.each([
      ['no image', { screenshot_size: [10, 20] as [number, number] }],
      ['no size', { screenshot_base64: 'AAAA' }],
    ])('is left out with %s', (_, payload) => {
      highRisk(payload);

      expect(screen.queryByTestId('HighRiskEvidenceScreenshot')).toBeNull();
    });
  });

  it('colours the warning as destructive text and never as the fill token', () => {
    const { container } = highRisk({}, 'danger');

    expect(destructiveTextSites(container)).toBe(3);
    expect(container.innerHTML).not.toMatch(BARE_DESTRUCTIVE_TEXT);
  });
});
