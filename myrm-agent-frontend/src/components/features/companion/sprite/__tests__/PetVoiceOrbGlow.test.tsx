import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import PetVoiceOrbGlow from '../PetVoiceOrbGlow';

describe('PetVoiceOrbGlow component', () => {
  it('renders nothing when voiceState is idle', () => {
    const { container } = render(<PetVoiceOrbGlow voiceState="idle" size={64} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders listening pulse halo when voiceState is listening', () => {
    const { container } = render(<PetVoiceOrbGlow voiceState="listening" audioLevel={0.5} size={64} />);
    expect(container.firstChild).not.toBeNull();
    const halo = container.querySelector('.animate-pulse');
    expect(halo).toBeTruthy();
    expect(halo?.className).toContain('bg-blue-500/20');
  });

  it('renders speaking waveform halo when voiceState is speaking', () => {
    const { container } = render(<PetVoiceOrbGlow voiceState="speaking" audioLevel={0.8} size={64} />);
    expect(container.firstChild).not.toBeNull();
    const halo = container.querySelector('.bg-emerald-500\\/25');
    expect(halo).toBeTruthy();
  });

  it('renders processing spin halo when voiceState is processing', () => {
    const { container } = render(<PetVoiceOrbGlow voiceState="processing" size={64} />);
    expect(container.firstChild).not.toBeNull();
    const halo = container.querySelector('.animate-spin');
    expect(halo).toBeTruthy();
    expect(halo?.className).toContain('bg-purple-500/20');
  });
});
