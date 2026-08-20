import { bareHost, type EmbedDescriptor, type EmbedMatcher, type FrameEmbed } from './types';

const LATLNG_RE = /@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)(?:,(\d+(?:\.\d+)?)z)?/;

function googleMapsEmbed(url: URL): FrameEmbed | null {
  const host = bareHost(url.hostname);
  if (host !== 'google.com' && host !== 'maps.google.com' && !host.startsWith('google.')) {
    return null;
  }

  const isMapsPath = host.startsWith('maps.') || url.pathname.startsWith('/maps');
  if (!isMapsPath) {
    return null;
  }

  const coords = url.pathname.match(LATLNG_RE);
  const placeName = url.pathname.match(/\/place\/([^/@]+)/);
  const query = url.searchParams.get('q') || url.searchParams.get('query');
  let q = '';
  let zoom = '';

  if (coords) {
    q = `${coords[1]},${coords[2]}`;
    zoom = coords[3] ? String(Math.round(Number(coords[3]))) : '';
  } else if (query) {
    q = query;
  } else if (placeName) {
    q = decodeURIComponent(placeName[1].replace(/\+/g, ' '));
  }

  if (!q) {
    return null;
  }

  const params = new URLSearchParams({ output: 'embed', q });
  if (zoom) {
    params.set('z', zoom);
  }

  return {
    id: `googlemaps:${q}${zoom ? `@${zoom}` : ''}`,
    label: 'Google Maps',
    provider: 'googlemaps',
    renderer: 'frame',
    sourceUrl: url.toString(),
    embedUrl: `https://maps.google.com/maps?${params.toString()}`,
    aspectRatio: 16 / 10,
    maxWidth: 640,
  };
}

function openStreetMapEmbed(url: URL): FrameEmbed | null {
  if (bareHost(url.hostname) !== 'openstreetmap.org') {
    return null;
  }

  const match = url.hash.match(/map=(\d+(?:\.\d+)?)\/(-?\d+(?:\.\d+)?)\/(-?\d+(?:\.\d+)?)/);
  if (!match) {
    return null;
  }

  const zoom = Number(match[1]);
  const lat = Number(match[2]);
  const lng = Number(match[3]);
  const lonDelta = 360 / 2 ** zoom;
  const latDelta = lonDelta / 2;

  const bbox = [lng - lonDelta / 2, lat - latDelta / 2, lng + lonDelta / 2, lat + latDelta / 2]
    .map((v) => v.toFixed(5))
    .join(',');

  const params = new URLSearchParams({ bbox, layer: 'mapnik', marker: `${lat},${lng}` });

  return {
    id: `openstreetmap:${lat},${lng}@${zoom}`,
    label: 'OpenStreetMap',
    provider: 'openstreetmap',
    renderer: 'frame',
    sourceUrl: url.toString(),
    embedUrl: `https://www.openstreetmap.org/export/embed.html?${params.toString()}`,
    aspectRatio: 16 / 10,
    maxWidth: 640,
  };
}

export const maps: EmbedMatcher = (url: URL): EmbedDescriptor | null => googleMapsEmbed(url) || openStreetMapEmbed(url);
