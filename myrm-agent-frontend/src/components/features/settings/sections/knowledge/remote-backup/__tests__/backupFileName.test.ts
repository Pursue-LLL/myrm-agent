import { describe, expect, it } from 'vitest';
import { deviceOf } from '../backupFileName';

describe('deviceOf', () => {
  it('reads the device out of a backup name', () => {
    expect(deviceOf('myrm.20261026093015.macbook-pro.a1b2c3d4.darwin.json.gz')).toBe('macbook-pro');
  });

  it('keeps dots and non-latin letters, which a device label may carry', () => {
    expect(deviceOf('myrm.20261026093015.my.laptop.local.a1b2c3d4.linux.json.gz')).toBe('my.laptop.local');
    expect(deviceOf('myrm.20261026093015.办公室电脑.a1b2c3d4.windows.json.gz')).toBe('办公室电脑');
  });

  it.each([
    'myrm.20260101000000.old-host.linux.json.gz',
    'myrm.json.gz',
    'notes.json.gz',
    'myrm.20261026093015.macbook-pro.a1b2c3d4.darwin.json',
    '',
  ])('has no device for %j, which does not follow the shape', (name) => {
    expect(deviceOf(name)).toBeNull();
  });
});
