import type { CommandMatch } from '../commands';

const FOCUS_TASK_READ_NOUN = /\b(?:tasks?|task\s+list|steps?|action\s+items|checklist)\b/i;
const FOCUS_TASK_READ_VERB = /\b(?:read|list|show|display|review|recall|tell\s+me|what|which)\b/i;
const FOCUS_TASK_REFERENCE = /\b(?:focus|focus\s+session|active\s+focus|current\s+focus|linked\s+tasks?)\b/i;
const TASK_MUTATION_OR_COMPLETION = /\b(?:add|create|make|generate|put|save|remember|mark|complete|completed|finish|finished|delete|remove|clear|reopen|restore)\b/i;

/**
 * Deterministic ownership floor for explicit reads of tasks linked to Active
 * Focus. This recognizes scope only; canonical Focus state remains authoritative
 * for membership and Memory supplies the task records used for display.
 */
export function isExplicitFocusTaskReadRequest(userMessage: string): boolean {
  const text = userMessage.replace(/\s+/g, ' ').trim();
  if (!text) return false;
  if (!FOCUS_TASK_READ_NOUN.test(text)) return false;
  if (!FOCUS_TASK_REFERENCE.test(text)) return false;
  if (!FOCUS_TASK_READ_VERB.test(text)) return false;
  if (TASK_MUTATION_OR_COMPLETION.test(text)) return false;
  return true;
}

/**
 * Re-enter the existing read-memory execution seam with an explicit scope tag.
 * App.tsx consumes this payload before the generic Memory handler so a missing
 * Active Focus cannot silently fall back to the global task list.
 */
export function buildExplicitFocusTaskReadCommand(): CommandMatch {
  return {
    command: 'read-memory',
    confirmation: 'Reading Focus tasks.',
    payload: 'focus-task-read',
  };
}
