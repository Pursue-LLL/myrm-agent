import { describe, expect, it } from 'vitest';
import { isDeployCandidateArtifactType } from '../artifactUtils';
import { ArtifactType } from '@/store/chat/types';

describe('isDeployCandidateArtifactType', () => {
  it('allows full-spectrum business artifact types for enterprise publishing', () => {
    const supportedTypes: ArtifactType[] = [
      'html',
      'code',
      'document',
      'pdf',
      'spreadsheet',
      'presentation',
      'word_document',
      'svg',
    ];

    supportedTypes.forEach((type) => {
      expect(isDeployCandidateArtifactType(type)).toBe(true);
    });
  });

  it('rejects raw audio and video without viewer wrapper', () => {
    expect(isDeployCandidateArtifactType('audio' as ArtifactType)).toBe(false);
    expect(isDeployCandidateArtifactType('video' as ArtifactType)).toBe(false);
  });
});
