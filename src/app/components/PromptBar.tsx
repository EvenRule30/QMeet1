import { useState, useCallback, useEffect } from 'react';

interface PromptBarProps {
  onSend: (text: string) => void;
  disabled: boolean;
}

type PromptCommandEventDetail = {
  command: string;
};

const QMEET_PROMPT_COMMAND_EVENT = 'qmeet-prompt-command';

export function PromptBar({ onSend, disabled }: PromptBarProps) {
  const [input, setInput] = useState('');

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || disabled) return;

    onSend(trimmed);
    setInput('');
  }, [input, disabled, onSend]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const handlePromptCommand = (event: Event) => {
      const detail = (event as CustomEvent<PromptCommandEventDetail>).detail;
      const command =
        typeof detail?.command === 'string' ? detail.command.trim() : '';

      if (!command) return;

      if (disabled) {
        setInput(command);
        return;
      }

      onSend(command);
      setInput('');
    };

    window.addEventListener(QMEET_PROMPT_COMMAND_EVENT, handlePromptCommand);

    return () => {
      window.removeEventListener(
        QMEET_PROMPT_COMMAND_EVENT,
        handlePromptCommand,
      );
    };
  }, [disabled, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="prompt-bar">
      <input
        className="prompt-input"
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask QMeet…"
        disabled={disabled}
        autoComplete="off"
      />
      <button
        className={`send-btn${disabled || !input.trim() ? ' send-disabled' : ''}`}
        onClick={handleSend}
        disabled={disabled || !input.trim()}
        aria-label="Send message"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <line x1="22" y1="2" x2="11" y2="13" />
          <polygon points="22 2 15 22 11 13 2 9 22 2" />
        </svg>
      </button>
    </div>
  );
}
