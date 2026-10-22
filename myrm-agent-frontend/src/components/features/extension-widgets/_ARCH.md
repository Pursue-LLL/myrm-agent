# Extension Widgets and ANSI Renderer Subsystem Architecture

## Overview
Provides a high-fidelity terminal ANSI escape sequence color renderer and modular extension widgets container (including Nano-Context token meter and Todo task checklist).

## Components & Files
| File | Role | Primary Consumers |
|---|---|---|
| `ansiRendererTypes.ts` | Domain types for ANSI tokens and extension widgets | UI components & tests |
| `ansiParser.ts` | Zero-dependency ANSI SGR color/style parser | `AnsiRenderer.tsx` |
| `AnsiRenderer.tsx` | Monospace React renderer supporting 16-color & 256-color codes | Terminal & widget outputs |
| `ExtensionWidgetHost.tsx` | Sidebar & footer container hosting Nano-Context and Todo widgets | Sidebar layout & dashboard |
| `index.ts` | Module export facade | External consumers |
