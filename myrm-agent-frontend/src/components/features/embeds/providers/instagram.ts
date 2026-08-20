import { bareHost, type EmbedDescriptor, type EmbedMatcher } from './types';

export const instagram: EmbedMatcher = (url: URL): EmbedDescriptor | null => {
  if (bareHost(url.hostname) !== 'instagram.com') {
    return null;
  }

  const [typeRaw, code] = url.pathname.split('/').filter(Boolean);
  const type = typeRaw === 'reels' ? 'reel' : typeRaw;

  if (!code || !['p', 'reel', 'tv'].includes(type || '') || !/^[A-Za-z0-9_-]+$/.test(code)) {
    return null;
  }

  return {
    id: `instagram:${code}`,
    label: 'Instagram',
    provider: 'instagram',
    renderer: 'frame',
    sourceUrl: url.href,
    embedUrl: `https://www.instagram.com/${type}/${code}/embed`,
    height: 450,
    maxWidth: 400,
  };
};
