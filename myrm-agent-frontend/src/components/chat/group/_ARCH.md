# components/chat/group/

## Overview

Bot Mode multi-agent group chat and Hermes peer messaging workspace components.
Provides Discord/Slack-style multi-bot channels, Composer `@-mention` auto-completion dropdown, deterministic SVG avatar palette rendering, and canonical peer dialogue archives.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `index.ts` | Facade | Public exports for group chat models and React components | ✅ |
| `deterministicAvatar.ts` | Utility | Deterministic SVG avatar and theme color generator | ✅ |
| `groupChatTypes.ts` | Schema | TypeScript data contracts for participants, rooms, messages, and peer archives | ✅ |
| `groupChatService.ts` | Service | Client communication layer with offline resilient fallbacks | ✅ |
| `ComposerMentionDropdown.tsx` | Component | Keyboard-driven accessible agent `@-mention` auto-completion dropdown | ✅ |
| `GroupRoomSidebar.tsx` | Component | Sidebar showing room participants, locked avatar badges, and canonical peer DM archives | ✅ |
| `GroupChatRoomLayout.tsx` | Layout | Main multi-bot workspace timeline view with Bot Mode header badge | ✅ |

## Dependencies

- `lucide-react`: Icons (`Bot`, `User`, `Users`, `Send`, `Hash`, `Shield`, `Inbox`, `Sparkles`, `Lock`)
- `next-intl`: Internationalization strings
