/**
 * Copy, validation, and threshold constants for Account-Wide Idle Chat Auto-Archive settings.
 *
 * Kept in a dedicated module to preserve fast refresh on settings components.
 */

export interface IdleChatArchiveOption {
  readonly label: string;
  readonly seconds: number;
}

export const IDLE_CHAT_ARCHIVE_COPY = {
  sectionTitle: "Idle Chat Auto-Archive",
  sectionDescription:
    "Automatically archive inactive chat conversations to keep your sidebar clean and focused.",
  toggleLabel: "Archive idle conversations automatically",
  toggleHint:
    "Archived chats remain searchable and can be restored at any time without data loss.",
  thresholdLabel: "Inactivity threshold",
  includeUserCreatedLabel: "Include manually created chats",
  includeUserCreatedHint:
    "When disabled, only assistant-triggered and automated sessions will be automatically archived.",
  pinnedExemptNote: "Pinned conversations are never automatically archived.",
  savedSuccess: "Auto-archive policy saved successfully.",
  saveFailed: "Failed to update auto-archive policy.",
} as const;

export const IDLE_CHAT_THRESHOLD_OPTIONS: readonly IdleChatArchiveOption[] = [
  { label: "1 Day", seconds: 86400 },
  { label: "3 Days", seconds: 86400 * 3 },
  { label: "7 Days (Default)", seconds: 86400 * 7 },
  { label: "14 Days", seconds: 86400 * 14 },
  { label: "30 Days", seconds: 86400 * 30 },
] as const;

export const DEFAULT_IDLE_ARCHIVE_POLICY = {
  enabled: false,
  idleThresholdSeconds: 86400 * 7,
  includeUserCreated: true,
} as const;
