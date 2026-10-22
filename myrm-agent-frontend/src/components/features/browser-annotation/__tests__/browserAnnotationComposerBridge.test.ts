import { describe, it, expect, vi } from 'vitest';
import {
  dispatchAnnotationToComposer,
  subscribeComposerAnnotation,
  COMPOSER_ANNOTATION_EVENT,
} from '../browserAnnotationComposerBridge';
import type { AnnotationExportPayload } from '../browserAnnotationTypes';

describe('browserAnnotationComposerBridge', () => {
  it('dispatches custom event and receives payload via subscription', () => {
    const callback = vi.fn();
    const unsubscribe = subscribeComposerAnnotation(callback);

    const testPayload: AnnotationExportPayload = {
      chatId: 'chat-test-123',
      pageUrl: 'http://localhost:3000/preview',
      pageTitle: 'Test Preview',
      totalPins: 1,
      groups: [],
      formattedPrompt: '## Test Prompt',
    };

    dispatchAnnotationToComposer(testPayload);

    expect(callback).toHaveBeenCalledTimes(1);
    expect(callback).toHaveBeenCalledWith(testPayload);

    unsubscribe();

    // After unsubscribe, further dispatches should not trigger callback
    dispatchAnnotationToComposer(testPayload);
    expect(callback).toHaveBeenCalledTimes(1);
  });

  it('exposes correct event name constant', () => {
    expect(COMPOSER_ANNOTATION_EVENT).toBe('myrm:inject-composer-annotation');
  });
});
