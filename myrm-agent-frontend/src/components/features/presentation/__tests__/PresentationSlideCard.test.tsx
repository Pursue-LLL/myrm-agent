/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PresentationSlideCard } from '../PresentationSlideCard';
import type { SlideData } from '@/services/presentation';

describe('PresentationSlideCard component', () => {
  const heroSlide: SlideData = {
    slide_number: 1,
    title: 'Enterprise Multi-Agent Architecture',
    subtitle: 'Autonomous Collaboration at Scale',
    layout: 'title_hero',
    elements: [
      {
        element_type: 'card',
        title: 'Core Engine',
        body: 'Distributed Execution',
      },
    ],
  };

  const comparisonSlide: SlideData = {
    slide_number: 2,
    title: 'Traditional vs Agentic Paradigm',
    subtitle: 'Architectural Shift',
    layout: 'two_column_comparison',
    elements: [
      {
        element_type: 'card',
        title: 'Traditional Scripts',
        body: 'Rigid execution paths',
        bullet_points: ['Hardcoded rules', 'Manual maintenance'],
      },
      {
        element_type: 'card',
        title: 'Autonomous Agents',
        body: 'Self-adapting feedback loops',
        bullet_points: ['Intelligent retries', 'Contextual decisions'],
      },
    ],
  };

  const metricSlide: SlideData = {
    slide_number: 3,
    title: 'System Throughput & Scalability',
    subtitle: 'Benchmarked Performance',
    layout: 'three_card_flow',
    elements: [
      {
        element_type: 'card',
        title: 'Latency',
        metric_value: '42ms',
        metric_label: 'P95 response time',
      },
      {
        element_type: 'card',
        title: 'Concurrency',
        metric_value: '10K',
        metric_label: 'Concurrent sandboxes',
      },
      {
        element_type: 'card',
        title: 'Cost Reduction',
        metric_value: '78%',
        metric_label: 'Token caching savings',
      },
    ],
  };

  const visualSlide: SlideData = {
    slide_number: 4,
    title: 'Concept Illustration Breakdown',
    subtitle: 'Visual Topology',
    layout: 'concept_illustration_focus',
    elements: [
      {
        element_type: 'card',
        title: 'Agent Mesh Topology',
        body: 'Decentralized message passing mesh',
      },
      {
        element_type: 'concept_illustration',
        illustration_prompt: 'High-tech distributed mesh topology node graph',
      },
    ],
  };

  it('renders hero title slide correctly', () => {
    render(<PresentationSlideCard slide={heroSlide} templateStyle="enterprise_blue" />);
    expect(screen.getAllByText('Enterprise Multi-Agent Architecture').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Autonomous Collaboration at Scale').length).toBeGreaterThan(0);
    expect(screen.getByText('SLIDE #1')).toBeInTheDocument();
  });

  it('renders two column comparison with bullets', () => {
    render(<PresentationSlideCard slide={comparisonSlide} templateStyle="minimal_dark" />);
    expect(screen.getByText('Traditional Scripts')).toBeInTheDocument();
    expect(screen.getByText('Autonomous Agents')).toBeInTheDocument();
    expect(screen.getByText('Hardcoded rules')).toBeInTheDocument();
    expect(screen.getByText('Intelligent retries')).toBeInTheDocument();
  });

  it('renders metric values in flow cards', () => {
    render(<PresentationSlideCard slide={metricSlide} templateStyle="tech_emerald" />);
    expect(screen.getByText('42ms')).toBeInTheDocument();
    expect(screen.getByText('10K')).toBeInTheDocument();
    expect(screen.getByText('78%')).toBeInTheDocument();
  });

  it('renders concept illustration focus layout', () => {
    render(<PresentationSlideCard slide={visualSlide} templateStyle="creative_gradient" />);
    expect(screen.getByText('Agent Mesh Topology')).toBeInTheDocument();
    expect(screen.getByText('Visual Concept')).toBeInTheDocument();
    expect(screen.getByText('High-tech distributed mesh topology node graph')).toBeInTheDocument();
  });

  it('renders properly in thumbnail mode without crashing', () => {
    const { container } = render(
      <PresentationSlideCard slide={heroSlide} isThumbnail={true} />,
    );
    expect(container.querySelector('article')).toHaveClass('aspect-video');
  });
});
