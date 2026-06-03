import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { UITabs } from '../components/UITabs';

const defaultProps = {
  id: 'tabs-1',
  props: {
    tabs: [{ label: 'Tab A' }, { label: 'Tab B' }],
  },
  bindings: {},
  events: {},
  data: {},
  onDataChange: vi.fn(),
  onAction: vi.fn(),
};

describe('UITabs', () => {
  describe('basic rendering', () => {
    it('renders tab triggers with labels', () => {
      render(
        <UITabs {...defaultProps}>
          <div>Content A</div>
          <div>Content B</div>
        </UITabs>,
      );
      expect(screen.getByText('Tab A')).toBeInTheDocument();
      expect(screen.getByText('Tab B')).toBeInTheDocument();
    });

    it('renders first tab content by default (defaultIndex=0)', () => {
      render(
        <UITabs {...defaultProps}>
          <div>Content A</div>
          <div>Content B</div>
        </UITabs>,
      );
      expect(screen.getByText('Content A')).toBeInTheDocument();
    });

    it('renders correct default tab when defaultIndex is specified', () => {
      const props = {
        ...defaultProps,
        props: {
          ...defaultProps.props,
          defaultIndex: 1,
        },
      };
      render(
        <UITabs {...props}>
          <div>Content A</div>
          <div>Content B</div>
        </UITabs>,
      );
      expect(screen.getByText('Content B')).toBeInTheDocument();
    });
  });

  describe('tab switching', () => {
    it('switches content when clicking a different tab', async () => {
      const user = userEvent.setup();
      render(
        <UITabs {...defaultProps}>
          <div>Content A</div>
          <div>Content B</div>
        </UITabs>,
      );

      await user.click(screen.getByText('Tab B'));
      expect(screen.getByText('Content B')).toBeInTheDocument();
    });
  });

  describe('empty/fallback handling', () => {
    it('renders children directly when tabs array is empty', () => {
      const props = {
        ...defaultProps,
        props: { tabs: [] },
      };
      render(
        <UITabs {...props}>
          <div>Fallback Content</div>
        </UITabs>,
      );
      expect(screen.getByText('Fallback Content')).toBeInTheDocument();
    });

    it('renders children directly when tabs is undefined', () => {
      const props = {
        ...defaultProps,
        props: {},
      };
      render(
        <UITabs {...props}>
          <div>No Tabs</div>
        </UITabs>,
      );
      expect(screen.getByText('No Tabs')).toBeInTheDocument();
    });
  });

  describe('boundary conditions', () => {
    it('handles more tabs than children gracefully', () => {
      const props = {
        ...defaultProps,
        props: {
          tabs: [{ label: 'Tab A' }, { label: 'Tab B' }, { label: 'Tab C' }],
        },
      };
      render(
        <UITabs {...props}>
          <div>Content A</div>
        </UITabs>,
      );
      expect(screen.getByText('Tab A')).toBeInTheDocument();
      expect(screen.getByText('Tab C')).toBeInTheDocument();
      expect(screen.getByText('Content A')).toBeInTheDocument();
    });

    it('handles more children than tabs (extra children ignored)', () => {
      const props = {
        ...defaultProps,
        props: {
          tabs: [{ label: 'Only Tab' }],
        },
      };
      render(
        <UITabs {...props}>
          <div>Content 1</div>
          <div>Content 2</div>
          <div>Content 3</div>
        </UITabs>,
      );
      expect(screen.getByText('Only Tab')).toBeInTheDocument();
      expect(screen.getByText('Content 1')).toBeInTheDocument();
    });

    it('handles single tab', () => {
      const props = {
        ...defaultProps,
        props: {
          tabs: [{ label: 'Single' }],
        },
      };
      render(
        <UITabs {...props}>
          <div>Single Content</div>
        </UITabs>,
      );
      expect(screen.getByText('Single')).toBeInTheDocument();
      expect(screen.getByText('Single Content')).toBeInTheDocument();
    });
  });

  describe('accessibility', () => {
    it('renders tablist role', () => {
      render(
        <UITabs {...defaultProps}>
          <div>A</div>
          <div>B</div>
        </UITabs>,
      );
      expect(screen.getByRole('tablist')).toBeInTheDocument();
    });

    it('renders tab triggers with tab role', () => {
      render(
        <UITabs {...defaultProps}>
          <div>A</div>
          <div>B</div>
        </UITabs>,
      );
      const tabs = screen.getAllByRole('tab');
      expect(tabs).toHaveLength(2);
      expect(tabs[0]).toHaveTextContent('Tab A');
      expect(tabs[1]).toHaveTextContent('Tab B');
    });

    it('renders tabpanel role for active content', () => {
      render(
        <UITabs {...defaultProps}>
          <div>A</div>
          <div>B</div>
        </UITabs>,
      );
      expect(screen.getByRole('tabpanel')).toBeInTheDocument();
    });
  });

  describe('variant support', () => {
    it('renders outline variant with border classes', () => {
      const props = {
        ...defaultProps,
        props: {
          ...defaultProps.props,
          variant: 'outline',
        },
      };
      const { container } = render(
        <UITabs {...props}>
          <div>A</div>
          <div>B</div>
        </UITabs>,
      );
      const tabsList = container.querySelector('[role="tablist"]');
      expect(tabsList?.className).toContain('bg-transparent');
      expect(tabsList?.className).toContain('border');
    });

    it('renders default variant without outline classes', () => {
      const { container } = render(
        <UITabs {...defaultProps}>
          <div>A</div>
          <div>B</div>
        </UITabs>,
      );
      const tabsList = container.querySelector('[role="tablist"]');
      expect(tabsList?.className).not.toContain('bg-transparent');
    });
  });

  describe('keyboard navigation', () => {
    it('switches tabs with arrow keys', async () => {
      const user = userEvent.setup();
      render(
        <UITabs {...defaultProps}>
          <div>Content A</div>
          <div>Content B</div>
        </UITabs>,
      );

      const firstTab = screen.getByText('Tab A');
      await user.click(firstTab);
      await user.keyboard('{ArrowRight}');
      expect(screen.getByText('Content B')).toBeInTheDocument();
    });
  });

  describe('no children', () => {
    it('renders tabs without children gracefully', () => {
      render(<UITabs {...defaultProps} />);
      expect(screen.getByRole('tablist')).toBeInTheDocument();
      expect(screen.getByText('Tab A')).toBeInTheDocument();
    });
  });

  describe('tab switch round-trip', () => {
    it('can switch back and forth between tabs', async () => {
      const user = userEvent.setup();
      render(
        <UITabs {...defaultProps}>
          <div>Content A</div>
          <div>Content B</div>
        </UITabs>,
      );

      await user.click(screen.getByText('Tab B'));
      expect(screen.getByText('Content B')).toBeInTheDocument();

      await user.click(screen.getByText('Tab A'));
      expect(screen.getByText('Content A')).toBeInTheDocument();
    });
  });
});
