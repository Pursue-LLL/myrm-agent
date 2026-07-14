import type { Messages } from './locale-manifest';

export function mergeMessages(base: Messages, extra: Partial<Messages>): Messages {
  return {
    ...base,
    ...extra,
    settings: {
      ...base.settings,
      ...extra.settings,
    },
  } as Messages;
}
