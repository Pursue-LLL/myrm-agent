import { bareHost, type EmbedDescriptor, type EmbedMatcher } from './types';

export const vimeo: EmbedMatcher = (url: URL): EmbedDescriptor | null => {
  const host = bareHost(url.hostname);
  if (host !== 'vimeo.com' && host !== 'player.vimeo.com') {return null;}

  const id = url.pathname
    .split('/')
    .filter(Boolean)
    .reverse()
    .find((segment) => /^\d+$/.test(segment));

  if (!id) {return null;}

  return {
    id: `vimeo:${id}`,
    label: 'Vimeo',
    provider: 'vimeo',
    renderer: 'frame',
    sourceUrl: url.toString(),
    embedUrl: `https://player.vimeo.com/video/${id}`,
    aspectRatio: 16 / 9,
    maxWidth: 640,
  };
};
