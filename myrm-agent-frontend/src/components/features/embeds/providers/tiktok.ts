import { bareHost, type EmbedDescriptor, type EmbedMatcher } from './types';

export const tiktok: EmbedMatcher = (url: URL): EmbedDescriptor | null => {
  if (bareHost(url.hostname) !== 'tiktok.com') {
    return null;
  }

  const segments = url.pathname.split('/').filter(Boolean);
  const videoIndex = segments.indexOf('video');
  const id = videoIndex >= 0 ? segments[videoIndex + 1] : '';

  if (!/^\d+$/.test(id || '')) {
    return null;
  }

  return {
    id: `tiktok:${id}`,
    label: 'TikTok',
    provider: 'tiktok',
    renderer: 'frame',
    sourceUrl: url.href,
    embedUrl: `https://www.tiktok.com/player/v1/${id}`,
    aspectRatio: 9 / 16,
    maxWidth: 365,
  };
};
