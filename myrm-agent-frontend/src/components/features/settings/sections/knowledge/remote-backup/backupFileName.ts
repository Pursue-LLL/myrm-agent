/**
 * [INPUT]
 * - (none): pure string handling
 *
 * [OUTPUT]
 * - deviceOf: the device a cloud backup was made on, read from its file name
 *
 * [POS]
 * The name of a cloud backup is `myrm.<time>.<device>.<instance>.<platform>.json.gz`. The list shows the device so that
 * backups of several computers can be told apart, and keeps the raw name out of sight; a name that does not follow the
 * shape (a file from an older version, or one that is not ours) simply has no device.
 */

const BACKUP_NAME = /^myrm\.\d{14}\.(.+)\.[0-9a-f]{8,}\.[a-z0-9_-]+\.json\.gz$/;

export function deviceOf(fileName: string): string | null {
  return BACKUP_NAME.exec(fileName)?.[1] ?? null;
}
