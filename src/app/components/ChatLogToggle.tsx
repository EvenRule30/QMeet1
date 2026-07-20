import { useCallback, useEffect, useState } from 'react';

const CHAT_LOG_OPEN_CLASS = 'qmeet-chat-log-open';
const CHAT_LOG_STYLE_ID = 'qmeet-chat-log-toggle-styles-v4';

function getReactChatVisible(): boolean {
  if (typeof document === 'undefined') return false;
  return Boolean(document.querySelector('.chat-area.chat-area-visible'));
}

function focusPromptInput(delayMs = 180): void {
  if (typeof document === 'undefined') return;
  window.setTimeout(() => {
    const promptInput = document.querySelector<HTMLInputElement>('.chat-area .prompt-input');
    promptInput?.focus({ preventScroll: true });
  }, delayMs);
}

function installChatLogStyles(): void {
  if (typeof document === 'undefined') return;
  if (document.getElementById(CHAT_LOG_STYLE_ID)) return;

  document
    .querySelectorAll<HTMLStyleElement>('style[id^="qmeet-chat-log-toggle-styles"]')
    .forEach((existingStyle) => existingStyle.remove());

  const style = document.createElement('style');
  style.id = CHAT_LOG_STYLE_ID;
  style.textContent = `
    .qmeet-chat-log-toggle {
      position: fixed;
      left: 16px;
      bottom: 16px;
      z-index: 850;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0;
      width: 34px;
      height: 34px;
      padding: 0;
      border: 1px solid rgba(167, 243, 208, 0.16);
      border-radius: 999px;
      background: rgba(5, 12, 18, 0.32);
      color: rgba(219, 255, 247, 0.62);
      box-shadow: 0 0 14px rgba(34, 211, 238, 0.06);
      backdrop-filter: blur(10px);
      cursor: pointer;
      opacity: 0.42;
      transition:
        opacity 180ms ease,
        transform 180ms ease,
        border-color 180ms ease,
        background 180ms ease,
        box-shadow 180ms ease,
        width 180ms ease,
        gap 180ms ease;
    }

    .qmeet-chat-log-toggle:hover,
    .qmeet-chat-log-toggle:focus-visible,
    .qmeet-chat-log-toggle-open {
      width: 76px;
      gap: 7px;
      opacity: 0.9;
      transform: translateY(-1px);
      border-color: rgba(103, 232, 249, 0.38);
      background: rgba(8, 20, 28, 0.66);
      box-shadow: 0 0 24px rgba(34, 211, 238, 0.14);
    }

    .qmeet-chat-log-toggle-icon {
      width: 15px;
      height: 15px;
      display: block;
      flex: 0 0 auto;
    }

    .qmeet-chat-log-toggle-label {
      max-width: 0;
      overflow: hidden;
      white-space: nowrap;
      font-size: 10px;
      font-weight: 600;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      opacity: 0;
      transition: max-width 170ms ease, opacity 170ms ease;
    }

    .qmeet-chat-log-toggle:hover .qmeet-chat-log-toggle-label,
    .qmeet-chat-log-toggle:focus-visible .qmeet-chat-log-toggle-label,
    .qmeet-chat-log-toggle-open .qmeet-chat-log-toggle-label {
      max-width: 42px;
      opacity: 1;
    }

    /* Chat-log peek mode intentionally mirrors App's normal chat-active CSS.
       Avoid flex-basis/display overrides so the existing width transitions run
       instead of snapping the orb left. */
    html.${CHAT_LOG_OPEN_CLASS} .orb-area:not(.orb-area-active) {
      width: 38% !important;
      border-right: 1px solid rgba(0, 180, 255, 0.07);
    }

    html.${CHAT_LOG_OPEN_CLASS} .orb-area:not(.orb-area-active) .orb-container {
      width: 160px !important;
      height: 160px !important;
      --orbit-r-1: 100px;
      --orbit-r-2: 90px;
    }

    html.${CHAT_LOG_OPEN_CLASS} .chat-area.chat-area-hidden {
      width: 62% !important;
      opacity: 1 !important;
      pointer-events: auto !important;
    }

    html.${CHAT_LOG_OPEN_CLASS} .idle-hint {
      opacity: 0.28;
    }

    .qmeet-chat-log-toggle-hidden {
      opacity: 0;
      transform: translateY(6px) scale(0.92);
      pointer-events: none;
      visibility: hidden;
    }

    @media (max-width: 720px) {
      .qmeet-chat-log-toggle {
        left: 12px;
        bottom: 12px;
      }
    }
  `;
  document.head.appendChild(style);
}

export function ChatLogToggle() {
  const [peekOpen, setPeekOpen] = useState(false);
  const [reactChatVisible, setReactChatVisible] = useState(false);

  useEffect(() => {
    if (typeof document === 'undefined') return;

    installChatLogStyles();
    setReactChatVisible(getReactChatVisible());

    const updateReactChatVisible = () => {
      const nextVisible = getReactChatVisible();
      setReactChatVisible(nextVisible);
      if (nextVisible) {
        setPeekOpen(false);
      }
    };

    const observer = new MutationObserver(updateReactChatVisible);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['class'],
    });

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (typeof document === 'undefined') return;

    const root = document.documentElement;
    const shouldForceOpen = peekOpen && !reactChatVisible;
    root.classList.toggle(CHAT_LOG_OPEN_CLASS, shouldForceOpen);

    if (shouldForceOpen) {
      focusPromptInput(420);
    }

    return () => {
      root.classList.remove(CHAT_LOG_OPEN_CLASS);
    };
  }, [peekOpen, reactChatVisible]);

  useEffect(() => {
    if (!peekOpen || typeof window === 'undefined') return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setPeekOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [peekOpen]);

  const handleToggle = useCallback(() => {
    if (reactChatVisible) {
      focusPromptInput(60);
      return;
    }

    setPeekOpen((current) => !current);
  }, [reactChatVisible]);

  // Hide the discreet affordance when the real chat console is already open.
  // In that state the button is redundant and can collide with command/result toasts.
  // Keep it visible for its own temporary peek mode so the same button can close the peek.
  const hiddenByConsole = reactChatVisible;
  const open = peekOpen;

  return (
    <button
      className={`qmeet-chat-log-toggle${open ? ' qmeet-chat-log-toggle-open' : ''}${hiddenByConsole ? ' qmeet-chat-log-toggle-hidden' : ''}`}
      type="button"
      aria-label={open ? 'Hide chat log preview' : 'Open chat log'}
      aria-pressed={open}
      title={open ? 'Chat log open' : 'Open chat log'}
      onClick={handleToggle}
    >
      <svg
        className="qmeet-chat-log-toggle-icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" />
        <path d="M8 9h8" />
        <path d="M8 13h5" />
      </svg>
      <span className="qmeet-chat-log-toggle-label">Chat</span>
    </button>
  );
}
