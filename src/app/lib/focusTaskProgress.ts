import { QMEET_API_BASE_URL } from '../api';

export type FocusTaskProgressTarget = {
  id: string;
  title: string;
  completedAt: string;
};

export type FocusTaskProgressResult = {
  ok: boolean;
  operation: 'record_focus_task_progress';
  outcome: 'recorded' | 'reused';
  verified: boolean;
  focusId: string;
  focusTitle: string;
  tasks: FocusTaskProgressTarget[];
  nextAction: string;
  allLinkedTasksComplete: boolean;
  sourceTurnId: string;
  message: string;
};

function createSourceTurnId(): string {
  const randomId =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `focus-task-progress-${randomId}`;
}

function errorDetail(payload: unknown): string {
  if (!payload || typeof payload !== 'object') return '';
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail.trim();
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === 'string') return message.trim();
  }
  return '';
}

export async function recordVerifiedFocusTaskProgress(
  expectedFocusId: string,
  tasks: FocusTaskProgressTarget[],
): Promise<FocusTaskProgressResult> {
  const response = await fetch(`${QMEET_API_BASE_URL}/api/focus/task-progress`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      expectedFocusId,
      tasks,
      sourceTurnId: createSourceTurnId(),
      confirmed: true,
    }),
  });

  const payload = (await response.json().catch(() => null)) as
    | FocusTaskProgressResult
    | { detail?: unknown }
    | null;
  if (!response.ok) {
    throw new Error(
      errorDetail(payload) ||
        `Focus task progress request failed with status ${response.status}.`,
    );
  }
  if (
    !payload ||
    !('verified' in payload) ||
    payload.verified !== true ||
    !('focusId' in payload) ||
    payload.focusId !== expectedFocusId
  ) {
    throw new Error('Focus task progress response did not verify canonically.');
  }
  return payload as FocusTaskProgressResult;
}
