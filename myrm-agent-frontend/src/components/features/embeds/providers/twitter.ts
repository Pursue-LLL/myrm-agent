import { bareHost, type EmbedDescriptor, type EmbedMatcher } from './types';

export const twitter: EmbedMatcher = (url: URL): EmbedDescriptor | null => {
  const host = bareHost(url.hostname);
  if (
    host !== 'twitter.com' &&
    host !== 'x.com' &&
    host !== 'vxtwitter.com' &&
    host !== 'fxtwitter.com' &&
    host !== 'fixupx.com'
  ) {
    return null;
  }

  const match = url.pathname.match(/^\/([^/]+)\/status\/(\d+)/);
  if (!match) {
    return null;
  }

  const tweetId = match[2];
  return {
    id: `twitter:${tweetId}`,
    label: 'X',
    provider: 'twitter',
    renderer: 'tweet',
    sourceUrl: `https://x.com${url.pathname}`,
    tweetId,
    maxWidth: 550,
  };
};
