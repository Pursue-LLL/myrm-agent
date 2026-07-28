import { bareHost, type EmbedDescriptor, type EmbedMatcher } from './types';

const EMBED_TYPES = new Set(['album', 'artist', 'episode', 'playlist', 'show', 'track']);
const COMPACT_HEIGHT = 152;

export const spotify: EmbedMatcher = (url: URL): EmbedDescriptor | null => {
  if (bareHost(url.hostname) !== 'open.spotify.com') return null;

  const segments = url.pathname.split('/').filter(Boolean);
  const start = segments[0]?.startsWith('intl-') ? 1 : 0;
  const type = segments[start] || '';
  const id = segments[start + 1] || '';

  if (!EMBED_TYPES.has(type) || !/^[A-Za-z0-9]+$/.test(id)) return null;

  return {
    id: `spotify:${type}:${id}`,
    label: 'Spotify',
    provider: 'spotify',
    renderer: 'frame',
    sourceUrl: url.href,
    embedUrl: `https://open.spotify.com/embed/${type}/${id}`,
    height: COMPACT_HEIGHT,
    maxWidth: 480,
  };
};
