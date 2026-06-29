# QMeet — AI Tablet Interface

A clean, maintainable dark-mode AI agent tablet UI built with React + Vite.

**Target:** Raspberry Pi 7" tablet running at 1024×600 landscape.

## Getting Started

```bash
pnpm install
pnpm dev
```

The dev server runs at `http://localhost:5173/`.

## Project Structure

```
src/
├── app/
│   ├── App.tsx                    # Main component & interaction logic
│   ├── App.css                    # Component styling
│   ├── types.ts                   # Type definitions
│   ├── utils.ts                   # Mock responses & utilities
│   └── components/
│       ├── Orb.tsx               # Animated glowing orb
│       ├── TopStatusBar.tsx       # Status bar with time & state
│       ├── ChatPanel.tsx          # Message display area
│       └── PromptBar.tsx          # Input field & send button
├── styles/
│   ├── index.css                  # Main style entry point
│   ├── globals.css                # Global resets & variables
│   └── fonts.css                  # Google Fonts import
└── main.tsx                       # React DOM entry point
```

## Architecture

### Component Hierarchy

- **App** (state management & orchestration)
  - TopStatusBar (status display)
  - AgentScreen
    - Orb (glowing animated sphere)
    - ChatPanel (message history)
    - PromptBar (user input)

### State Variables

- `chatActive`: boolean — whether conversation has started
- `orbState`: OrbState — one of: `idle`, `listening`, `thinking`, `speaking`, `error`
- `messages`: Message[] — array of chat messages

### Interaction Flow

1. **Idle State** — Orb centered, idle hint visible. User can click orb to listen.
2. **Listening** — Orb pulses green. STT captures voice input.
3. **Processing** — Orb shifts left, chat panel appears. Orb pulses purple.
4. **Speaking** — Assistant responds. Orb pulses cyan. Messages appear in chat.
5. **Back to Idle** — After response, waits for next input.

## Backend Integration (TODO)

The app is ready for FastAPI backend integration. Look for `// TODO: Backend integration` comments in `src/app/App.tsx`.

### Option 1: WebSocket (Streaming)
```typescript
const ws = new WebSocket('ws://localhost:8000/ws/chat');
ws.onmessage = (e) => {
  const data = JSON.parse(e.data);
  // Append assistant message chunks
};
```

### Option 2: REST API
```typescript
const res = await fetch('http://localhost:8000/api/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ message: text }),
});
const { reply } = await res.json();
```

## Styling

All styling is in CSS with no CSS-in-JS or utility frameworks. The color palette is:

- **Background:** `#07091a` (deep navy)
- **Accent Cyan:** `#00d4ff`
- **Accent Purple:** `#cc44ff`
- **Text:** `#e8edf5` (light gray-blue)

The orb is fully procedural CSS with animated gradients and orbital dots.

## Development Notes

- No unused dependencies — only React, Vite, and @vitejs/plugin-react.
- No shadcn/ui components or other bloat.
- Mock responses in `src/app/utils.ts` for testing without backend.
- Responsive breakpoints preserved but app is locked to 1024×600.
- All interactive states have visual feedback (color changes, animations, disabling).

## Building

```bash
pnpm build      # Production build
pnpm preview    # Preview build
```

The production build is ~342 KB (102 KB gzipped) including all React code.

## Browser Support

Modern browsers only (Chrome, Firefox, Safari, Edge). The app uses CSS gradients, animations, and CSS Grid — no IE11 support.
