import { afterEach, describe, expect, it } from 'vitest';
import { incognitoUploadOptions } from '../incognitoUploadOptions';
import useChatStore from '@/store/useChatStore';

describe('incognitoUploadOptions', () => {
  const initial = useChatStore.getState();

  afterEach(() => {
    useChatStore.setState({ incognitoMode: initial.incognitoMode, chatId: initial.chatId });
  });

  it('binds an upload to the current chat while incognito is on', () => {
    useChatStore.setState({ incognitoMode: true, chatId: 'chat-incognito' });

    expect(incognitoUploadOptions()).toEqual({ incognitoChatId: 'chat-incognito' });
  });

  it('leaves the upload unbound in a normal chat', () => {
    useChatStore.setState({ incognitoMode: false, chatId: 'chat-normal' });

    expect(incognitoUploadOptions()).toEqual({});
  });

  it('does not bind to a chat that has no id yet', () => {
    useChatStore.setState({ incognitoMode: true, chatId: '' });

    expect(incognitoUploadOptions()).toEqual({});
  });
});
