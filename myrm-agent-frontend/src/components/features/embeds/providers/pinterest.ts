import { bareHost, type EmbedDescriptor, type EmbedMatcher } from './types';

export const pinterest: EmbedMatcher = (url: URL): EmbedDescriptor | null => {
  if (!bareHost(url.hostname).includes('pinterest.')) {return null;}

  const segments = url.pathname.split('/').filter(Boolean);
  if (segments[0] !== 'pin' || !/^\d+$/.test(segments[1] || '')) {return null;}

  const id = segments[1];
  return {
    id: `pinterest:${id}`,
    label: 'Pinterest',
    provider: 'pinterest',
    renderer: 'frame',
    sourceUrl: url.toString(),
    embedUrl: `https://assets.pinterest.com/ext/embed.html?id=${id}`,
    height: 380,
    maxWidth: 236,
  };
};
