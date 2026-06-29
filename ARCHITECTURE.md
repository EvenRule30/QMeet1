# QMeet Architecture & Component Design

## Visual Component Hierarchy

```
┌─────────────────────────────────────────────────────────┐
│                   Root (#root)                          │
│            <div id="root">                              │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                  App Component                          │
│  src/app/App.tsx (state management)                     │
│                                                         │
│  State:                                                 │
│  - chatActive: boolean                                  │
│  - orbState: OrbState                                   │
│  - messages: Message[]                                  │
└─────────────────────────────────────────────────────────┘
                          ↓
        ┌─────────────────────────────────┐
        │     agent-screen (flex col)      │
        └─────────────────────────────────┘
                          ↓
    ┌─────────────────────────────────┐
    │      TopStatusBar (40px)         │
    │  - QMeet logo                    │
    │  - orbState indicator            │
    │  - Current time (updates 1sec)   │
    │  - End button (if chatActive)    │
    │  - Connected indicator           │
    └─────────────────────────────────┘
                          ↓
    ┌─────────────────────────────────┐
    │     agent-body (flex row)        │
    │   Grows to fill remaining space  │
    └─────────────────────────────────┘
            ↙                        ↘
    ┌──────────────┐          ┌────────────────┐
    │  orb-area    │          │  chat-area     │
    │              │          │                │
    │  Width:      │          │  Width:        │
    │  100% idle   │          │  0% idle       │
    │  38% active  │          │  62% active    │
    │              │          │                │
    │  Animated    │          │  Animated      │
    │  transition  │          │  opacity fade  │
    │  0.65s       │          │  0.65s / 0.5s  │
    │              │          │                │
    │ ┌──────────┐ │          │ ┌────────────┐ │
    │ │   Orb    │ │          │ │ ChatPanel  │ │
    │ │(Orb.tsx) │ │          │ │(flex col)  │ │
    │ │          │ │          │ │            │ │
    │ │ - Sphere │ │          │ │ Messages:  │ │
    │ │ - Halo   │ │          │ │ - User     │ │
    │ │ - Orbit  │ │          │ │ - Assistant│ │
    │ │ - Dots   │ │          │ │ - Thinking │ │
    │ │          │ │          │ │            │ │
    │ │ States:  │ │          │ │ Max height │ │
    │ │ - idle   │ │          │ │ Scroll if  │ │
    │ │ - listen │ │          │ │ needed     │ │
    │ │ - think  │ │          │ └────────────┘ │
    │ │ - speak  │ │          │                │
    │ │ - error  │ │          │ ┌────────────┐ │
    │ └──────────┘ │          │ │ PromptBar  │ │
    │              │          │ │(60px, flex)│ │
    │ Idle Hint    │          │ │            │ │
    │ (fade anim)  │          │ │ - Input    │ │
    │              │          │ │ - Button   │ │
    │ Click→listen │          │ │            │ │
    └──────────────┘          │ Disabled     │
                              │ when thinking│
                              └────────────┘ │
                              └────────────────┘
```

## Layout Transition (600px height example)

### Idle State (chatActive = false)

```
┌─────────────────────────────────┐
│     TopStatusBar (40px)         │
├─────────────────────────────────┤
│                                 │
│         orb-area (100%)         │
│                                 │
│       ┌─────────────┐            │
│       │     Orb     │            │
│       │   (220px)   │            │
│       │             │            │
│       └─────────────┘            │
│                                 │
│     Ask QMeet anything…         │
│   (idle hint, pulsing)          │
│                                 │
│                                 │
└─────────────────────────────────┘
```

### Active Chat State (chatActive = true)

```
┌─────────────────────────────────┐
│  TopStatusBar | End button      │
├─────────┬───────────────────────┤
│         │                       │
│ orb     │    chat-area (62%)    │
│ (38%)   │                       │
│         │  ┌─────────────────┐  │
│  ┌───┐  │  │ Message 1       │  │
│  │Orb│  │  │ User: Hi        │  │
│  │160 │  │  │                 │  │
│  │px  │  │  │ Message 2       │  │
│  │    │  │  │ Asst: Hello... │  │
│  └───┘  │  └─────────────────┘  │
│         │                       │
│         │  ┌─────────────────┐  │
│         │  │ Prompt bar      │  │
│         │  │ [Ask QMeet…] ⬆  │  │
│         │  └─────────────────┘  │
└─────────┴───────────────────────┘
```

## State Machine Diagram

```
                    ┌─────────────┐
                    │    IDLE     │
                    │ Orb centered│
                    │ Hint shown  │
                    └──────┬──────┘
                           │
                 Click orb or start chat
                           │
                           ↓
                    ┌─────────────┐
                    │ LISTENING   │
                    │ Orb green   │
                    │ Chat panel  │
                    │ animates in │
                    └──────┬──────┘
                           │
                    (simulated delay)
                           │
                           ↓
                    ┌─────────────┐
                    │  THINKING   │
                    │ Orb purple  │
                    │ User msg    │
                    │ appears     │
                    └──────┬──────┘
                           │
                    (await backend)
                           │
                           ↓
                    ┌─────────────┐
                    │  SPEAKING   │
                    │ Orb cyan    │
                    │ Asst msg    │
                    │ appears     │
                    └──────┬──────┘
                           │
                    (simulated duration)
                           │
                           ↓
                    ┌─────────────┐
                    │    IDLE     │
                    │ Wait input  │
                    │ (cycle)     │
                    └──────┬──────┘
                           │
                    ┌──────────────────┐
                    │ Click End button │
                    │ Clear messages   │
                    │ Shrink orb       │
                    │ Hide chat panel  │
                    └──────┬───────────┘
                           │
                           ↓
                    ┌─────────────┐
                    │    IDLE     │
                    │ (reset)     │
                    └─────────────┘
```

## CSS Layout Model

```
Root Document (1024×600)
│
└── agent-screen [display: flex; flex-direction: column]
    │
    ├── status-bar [height: 40px; position: relative; z-index: 10]
    │   ├── status-left [display: flex; gap: 12px]
    │   │   ├── status-logo [gradient text]
    │   │   ├── status-divider
    │   │   └── status-state [color varies by orbState]
    │   │
    │   └── status-right [display: flex; gap: 16px]
    │       ├── status-time [monospace, muted]
    │       ├── end-btn [conditional, hidden unless chatActive]
    │       └── connection-indicator [flex, pulsing dot]
    │
    └── agent-body [flex: 1; display: flex; overflow: hidden]
        │
        ├── orb-area [width: 100%→38%; transition: 0.65s cubic-bezier(...)]
        │   ├── orb-container [position: relative]
        │   │   ├── orb-halo [position: absolute; inset: -55%]
        │   │   ├── orb-sphere [position: absolute; inset: 0]
        │   │   │   ├── orb-gradient [radial-gradient × 4]
        │   │   │   └── orb-gloss [specular highlight]
        │   │   ├── orb-depth [box-shadow with multiple glows]
        │   │   └── orb-orbital-wrap [position: absolute; inset: 0; z-index: 5]
        │   │       ├── orbit-group-1 [3 dots, clockwise, radius var(--orbit-r-1)]
        │   │       └── orbit-group-2 [3 dots, CCW, radius var(--orbit-r-2)]
        │   │
        │   └── idle-hint [position: absolute; bottom: 28px; animation: fade 3.5s ∞]
        │
        └── chat-area [width: 0%→62%; opacity: 0→1; transition: 0.65s + 0.5s fade]
            │
            ├── chat-panel [flex: 1; overflow: hidden]
            │   └── chat-messages [flex: 1; overflow-y: auto]
            │       ├── message.message-user [flex-direction: row-reverse]
            │       ├── message.message-assistant [flex-direction: row]
            │       │   ├── message-avatar [30px circle, gradient border]
            │       │   └── message-bubble [max-width: 78%; padding: 10px 14px]
            │       │       ├── p [font-size: 15px; line-height: 1.58]
            │       │       └── message-time [font-size: 10px; muted]
            │       │
            │       └── thinking-bubble [display: flex; thinking-dots × 3]
            │           └── thinking-dots span [animation: bounce 1.2s ∞]
            │
            └── prompt-bar [height: 60px; display: flex; gap: 10px]
                ├── prompt-input [flex: 1; height: 44px; border-radius: 22px]
                │                 [background: rgba(0, 180, 255, 0.04)]
                │                 [border: 1px solid rgba(0, 180, 255, 0.13)]
                │
                └── send-btn [width: 44px; height: 44px; border-radius: 50%]
                             [background: linear-gradient(135deg, #00d4ff, #0088cc)]
                             [box-shadow: 0 0 20px rgba(0, 180, 255, 0.35)]
```

## Data Flow

```
User Input
    │
    ├─────→ PromptBar.onSend(text)
    │           │
    │           ├─→ Append user Message to state
    │           ├─→ setOrbState('thinking')
    │           ├─→ TODO: Await backend response
    │           ├─→ setOrbState('speaking')
    │           ├─→ Append assistant Message
    │           └─→ setOrbState('idle')
    │
    └─→ ChatPanel receives messages[]
            │
            └─→ Render <div className="message">
                for each message in array
                
App.tsx holds all state
    │
    ├─→ TopStatusBar receives orbState
    │   └─→ Renders state label + icon
    │
    └─→ Orb receives orbState
        └─→ CSS animates orb-sphere + orb-depth
            based on .orb-{orbState} class
```

## Type Definitions

```typescript
// src/app/types.ts

type OrbState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}
```

## Animation Timings

| Animation | Duration | Easing | Loop | Purpose |
|-----------|----------|--------|------|---------|
| hint-fade | 3.5s | ease-in-out | ∞ | Idle hint pulsing |
| orb-breathe | 4s | ease-in-out | ∞ | Idle breathing |
| orb-glow-pulse | 4s | ease-in-out | ∞ | Glow intensity |
| orb-ripple | 0.9s | ease-in-out | ∞ | Speaking ripple |
| msg-in | 0.3s | ease-out | 1x | Message entry |
| dot-bounce | 1.2s | ease-in-out | ∞ | Thinking dots |
| conn-pulse | 2.5s | ease-in-out | ∞ | Status indicator |
| orb-area width | 0.65s | cubic-bezier(0.4, 0, 0.2, 1) | 1x | Layout shift |
| chat-area opacity | 0.5s | ease | 1x | Chat fade (delayed 0.1s) |

## Color Palette

```css
--bg-primary: #07091a;          /* Deep navy background */
--bg-secondary: rgba(7, 9, 26, 0.96);  /* Status bar overlay */
--text-primary: #e8edf5;         /* Light gray-blue */
--text-muted: #2a3d55;           /* Muted state text */
--text-hint: #3d5a80;            /* Dimmed text */

--accent-cyan: #00d4ff;          /* Primary accent (speaking) */
--accent-cyan-light: #00ffb3;    /* Listening accent */
--accent-purple: #cc44ff;        /* Secondary accent (thinking) */
--accent-purple-light: #aa55ff;  /* Thinking brighter */
--accent-error: #ff4466;         /* Error state */

--border-cyan: rgba(0, 180, 255, 0.1);    /* Subtle border */
--glow-cyan: rgba(0, 212, 255, 0.35);     /* Glow effect */
```

## Performance Considerations

**Animations:**
- Use `transform` and `opacity` for animations (GPU accelerated)
- Avoid animating `width` and `height` (layout thrashing)
- Orb state changes only trigger CSS recomputes, not DOM changes

**Rendering:**
- Message list uses key={msg.id} for proper reconciliation
- useCallback prevents unnecessary function recreations
- No inline event handlers (all extracted to named functions)

**Bundle Size:**
- 102 KB gzipped (includes React 18)
- ~40 KB of CSS (well-optimized)
- ~60 KB of JS (App + components)
- Suitable for Raspberry Pi with 4G RAM

---

For more details, see README.md and REFACTORING_SUMMARY.md.
