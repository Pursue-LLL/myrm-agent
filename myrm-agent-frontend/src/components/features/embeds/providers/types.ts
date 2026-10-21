export type EmbedProvider =
  'googlemaps' | 'instagram' | 'openstreetmap' | 'pinterest' | 'spotify' | 'tiktok' | 'twitter' | 'vimeo' | 'youtube';

export type EmbedRenderer = 'frame' | 'tweet';

interface EmbedLayout {
  aspectRatio?: number;
  height?: number;
  maxWidth?: number;
}

interface BaseEmbed extends EmbedLayout {
  id: string;
  label: string;
  provider: EmbedProvider;
  renderer: EmbedRenderer;
  sourceUrl: string;
}

export interface FrameEmbed extends BaseEmbed {
  embedUrl: string;
  renderer: 'frame';
}

export interface TweetEmbed extends BaseEmbed {
  renderer: 'tweet';
  tweetId: string;
}

export type EmbedDescriptor = FrameEmbed | TweetEmbed;

export type EmbedMatcher = (url: URL) => EmbedDescriptor | null;

export function bareHost(host: string): string {
  return host.replace(/^(?:www|m|mobile)\./i, '').toLowerCase();
}
