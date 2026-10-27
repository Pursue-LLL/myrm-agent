import { describe, expect, it } from 'vitest';
import {
  DEFAULT_CONFIG,
  DEFAULT_KEEP,
  DEFAULT_SYNC_INTERVAL,
  KEEP_MAX,
  KEEP_MIN,
  clampKeep,
  isConnectionFilled,
  keepChoices,
  snapInterval,
  withDefaults,
} from '../remoteBackupConfig';

describe('snapInterval', () => {
  it.each([
    [60, 60],
    [360, 360],
    [720, 720],
    [1440, 1440],
    [5, 60],
    [90, 60],
    [300, 360],
    [500, 360],
    [1000, 720],
    [10080, 1440],
  ])('brings a stored %i minutes to the offered %i', (stored, offered) => {
    expect(snapInterval(stored)).toBe(offered);
  });

  it('resolves two equally near frequencies to the longer one, so a backup never runs more often than asked', () => {
    expect(snapInterval(210)).toBe(360);
    expect(snapInterval(540)).toBe(720);
  });

  it.each([undefined, null, Number.NaN, Number.POSITIVE_INFINITY, '60'])(
    'falls back to the default for %s',
    (stored) => {
      expect(snapInterval(stored)).toBe(DEFAULT_SYNC_INTERVAL);
    },
  );
});

describe('clampKeep', () => {
  it.each([
    [0, KEEP_MIN],
    [-3, KEEP_MIN],
    [150, KEEP_MAX],
    [7.6, 8],
    [10, 10],
  ])('keeps %s within the range the server accepts as %i', (stored, kept) => {
    expect(clampKeep(stored)).toBe(kept);
  });

  it.each([undefined, null, Number.NaN, '5'])('falls back to the default for %s', (stored) => {
    expect(clampKeep(stored)).toBe(DEFAULT_KEEP);
  });
});

describe('keepChoices', () => {
  it('offers the usual counts', () => {
    expect(keepChoices(10)).toEqual([3, 5, 10, 20, 50]);
  });

  it('adds the stored count when it is not among them, so a saved value never disappears', () => {
    expect(keepChoices(7)).toEqual([3, 5, 7, 10, 20, 50]);
    expect(keepChoices(100)).toEqual([3, 5, 10, 20, 50, 100]);
  });
});

describe('withDefaults', () => {
  it('gives a new user the defaults', () => {
    expect(withDefaults(undefined)).toEqual(DEFAULT_CONFIG);
  });

  it('fills what an older stored value lacks and keeps what it has', () => {
    const loaded = withDefaults({
      enabled: true,
      provider: 's3',
      autoSync: true,
      syncInterval: 5,
      maxBackups: 0,
      deviceName: 'Office',
      s3: { endpoint: 'https://s3.example.com' } as typeof DEFAULT_CONFIG.s3,
    });

    expect(loaded).toMatchObject({
      enabled: true,
      provider: 's3',
      autoSync: true,
      syncInterval: 60,
      maxBackups: KEEP_MIN,
      deviceName: 'Office',
    });
    expect(loaded.s3).toEqual({ ...DEFAULT_CONFIG.s3, endpoint: 'https://s3.example.com' });
    expect(loaded.webdav).toEqual(DEFAULT_CONFIG.webdav);
  });

  it('does not share nested settings with the defaults', () => {
    const loaded = withDefaults(undefined);

    expect(loaded.webdav).not.toBe(DEFAULT_CONFIG.webdav);
    expect(loaded.s3).not.toBe(DEFAULT_CONFIG.s3);
  });
});

describe('isConnectionFilled', () => {
  it('asks the chosen provider only', () => {
    const webdav = { ...DEFAULT_CONFIG, webdav: { ...DEFAULT_CONFIG.webdav, host: 'https://dav.example.com' } };

    expect(isConnectionFilled(webdav)).toBe(true);
    expect(isConnectionFilled({ ...webdav, provider: 's3' })).toBe(false);
  });

  it('does not count blanks as filled', () => {
    expect(isConnectionFilled({ ...DEFAULT_CONFIG, webdav: { ...DEFAULT_CONFIG.webdav, host: '   ' } })).toBe(false);
    expect(isConnectionFilled({ ...DEFAULT_CONFIG, provider: 's3', s3: { ...DEFAULT_CONFIG.s3, endpoint: ' ' } })).toBe(
      false,
    );
  });
});
