import type { ActivePanel, ActiveSession, MemorySessionMode, MemoryTask, RecentFocusSession, VisualContext, VisualObservation } from '../types';
import type { CommandMatch, FocusSessionCommandPayload } from '../commands';
import {
  clearActiveSession,
  clearVisualContext,
  createVisualObservation,
  deleteVisualObservationById,
  replaceActiveSession,
  updateActiveSession,
  updateVisualContext,
} from '../api';


const ENHANCED_FOCUS_RECAP_CHAT_EVENT = 'qmeet-enhanced-focus-recap-chat';

type EnhancedFocusRecapChatEventDetail = {
  prompt: string;
  visibleText: string;
};

type CalendarFocusPrepEventDetail = {
  requestedAt: string;
  source: 'memory-command';
};

export type MemoryCommandResult = {
  handled: boolean;
  confirmationContent?: string;
  shouldSpeakConfirmation?: boolean;
};

type ActiveSessionStateEventDetail = {
  activeSession: ActiveSession | null;
};

type NormalizedFocusPayload = {
  title?: string;
  mode?: MemorySessionMode;
  goal?: string;
  forceEnd?: boolean;
};

const ACTIVE_SESSION_STORAGE_KEY = 'qmeet-active-session';
const ACTIVE_SESSION_SESSION_STORAGE_KEY = 'qmeet-active-session-live';
const ACTIVE_SESSION_STATE_EVENT = 'qmeet-active-session-state';
const SAVE_FOCUS_SUMMARY_NOTE_EVENT = 'qmeet-save-focus-summary-note';
const MEMORY_TASKS_STORAGE_KEY = 'qmeet-memory-tasks';
const NOTES_STORAGE_KEY = 'qmeet-notes';
const RECENT_ACTIONS_STORAGE_KEY = 'qmeet-recent-actions';
const RECENT_FOCUS_SESSIONS_STORAGE_KEY = 'qmeet-recent-focus-sessions';
const VISUAL_CONTEXT_STORAGE_KEY = 'qmeet-visual-context';
const VISUAL_CONTEXT_STATE_EVENT = 'qmeet-visual-context-state';
const CALENDAR_FOCUS_PREP_EVENT = 'qmeet-calendar-focus-prep-command';
const ACTIVE_SESSION_COMMAND_HANDLER_MARKER = 'phase16a-v1-calendar-focus';

function createId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function isMemorySessionMode(value: string | undefined): value is MemorySessionMode {
  return (
    value === 'general' ||
    value === 'coding' ||
    value === 'meeting' ||
    value === 'planning' ||
    value === 'research' ||
    value === 'personal'
  );
}

function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string');
}

function normalizeActiveSession(value: unknown): ActiveSession | null {
  if (!value || typeof value !== 'object') return null;

  const candidate = value as Partial<ActiveSession>;
  if (typeof candidate.title !== 'string' || !candidate.title.trim()) {
    return null;
  }

  const now = new Date().toISOString();

  return {
    id:
      typeof candidate.id === 'string' && candidate.id.trim()
        ? candidate.id
        : createId('session'),
    title: candidate.title.trim(),
    mode: isMemorySessionMode(candidate.mode) ? candidate.mode : 'general',
    goal: typeof candidate.goal === 'string' ? candidate.goal : '',
    startedAt:
      typeof candidate.startedAt === 'string' ? candidate.startedAt : now,
    updatedAt:
      typeof candidate.updatedAt === 'string' ? candidate.updatedAt : now,
    pinnedNoteIds: readStringArray(candidate.pinnedNoteIds),
    linkedTaskIds: readStringArray(candidate.linkedTaskIds),
    ...(typeof candidate.summary === 'string'
      ? { summary: candidate.summary }
      : candidate.summary === null
        ? { summary: null }
        : {}),
  };
}

function readStoredActiveSession(): ActiveSession | null {
  if (typeof window === 'undefined') return null;

  const storageKeys = [ACTIVE_SESSION_STORAGE_KEY, ACTIVE_SESSION_SESSION_STORAGE_KEY];

  for (const storageKey of storageKeys) {
    try {
      const storage =
        storageKey === ACTIVE_SESSION_SESSION_STORAGE_KEY
          ? window.sessionStorage
          : window.localStorage;
      const rawSession = storage.getItem(storageKey);
      if (!rawSession) continue;
      const activeSession = normalizeActiveSession(JSON.parse(rawSession));
      if (activeSession) return activeSession;
    } catch {
      // Try the next fallback store.
    }
  }

  return null;
}


function normalizeRecentFocusSession(value: unknown): RecentFocusSession | null {
  if (!value || typeof value !== 'object') return null;

  const candidate = value as Partial<RecentFocusSession>;
  if (typeof candidate.title !== 'string' || !candidate.title.trim()) {
    return null;
  }

  const now = new Date().toISOString();

  return {
    id:
      typeof candidate.id === 'string' && candidate.id.trim()
        ? candidate.id
        : createId('recent-session'),
    title: candidate.title.trim(),
    mode: isMemorySessionMode(candidate.mode) ? candidate.mode : 'general',
    goal: typeof candidate.goal === 'string' ? candidate.goal : '',
    startedAt:
      typeof candidate.startedAt === 'string' ? candidate.startedAt : now,
    endedAt: typeof candidate.endedAt === 'string' ? candidate.endedAt : now,
    pinnedNoteIds: readStringArray(candidate.pinnedNoteIds),
    linkedTaskIds: readStringArray(candidate.linkedTaskIds),
    ...(typeof candidate.summary === 'string'
      ? { summary: candidate.summary }
      : candidate.summary === null
        ? { summary: null }
        : {}),
    ...(typeof candidate.summaryNoteId === 'string'
      ? { summaryNoteId: candidate.summaryNoteId }
      : candidate.summaryNoteId === null
        ? { summaryNoteId: null }
        : {}),
  };
}

function readStoredRecentFocusSessions(): RecentFocusSession[] {
  if (typeof window === 'undefined') return [];

  try {
    const rawSessions = window.localStorage.getItem(RECENT_FOCUS_SESSIONS_STORAGE_KEY);
    if (!rawSessions) return [];
    const parsedSessions = JSON.parse(rawSessions);
    if (!Array.isArray(parsedSessions)) return [];

    return parsedSessions
      .map(normalizeRecentFocusSession)
      .filter((session): session is RecentFocusSession => session !== null)
      .sort((a, b) => {
        const bTime = new Date(b.endedAt).getTime();
        const aTime = new Date(a.endedAt).getTime();
        return (Number.isNaN(bTime) ? 0 : bTime) - (Number.isNaN(aTime) ? 0 : aTime);
      });
  } catch {
    return [];
  }
}


function createEmptyVisualContext(): VisualContext {
  return {
    enabled: false,
    lastObservation: null,
    recentObservations: [],
  };
}

function isVisualContextSource(value: unknown): value is VisualObservation['source'] {
  return value === 'manual' || value === 'camera' || value === 'screen';
}

function normalizeVisualObservation(value: unknown): VisualObservation | null {
  if (!value || typeof value !== 'object') return null;

  const candidate = value as Partial<VisualObservation>;
  if (typeof candidate.summary !== 'string' || !candidate.summary.trim()) {
    return null;
  }

  const now = new Date().toISOString();
  return {
    id:
      typeof candidate.id === 'string' && candidate.id.trim()
        ? candidate.id
        : createId('visual'),
    source: isVisualContextSource(candidate.source) ? candidate.source : 'manual',
    summary: candidate.summary.trim(),
    capturedAt:
      typeof candidate.capturedAt === 'string' && candidate.capturedAt.trim()
        ? candidate.capturedAt
        : now,
    ...(typeof candidate.confidence === 'number'
      ? { confidence: candidate.confidence }
      : candidate.confidence === null
        ? { confidence: null }
        : {}),
    ...(typeof candidate.relatedFocusId === 'string' && candidate.relatedFocusId.trim()
      ? { relatedFocusId: candidate.relatedFocusId }
      : {}),
  };
}

function normalizeVisualContext(value: unknown): VisualContext {
  if (!value || typeof value !== 'object') return createEmptyVisualContext();

  const candidate = value as Partial<VisualContext>;
  const recentObservations = Array.isArray(candidate.recentObservations)
    ? candidate.recentObservations
        .map(normalizeVisualObservation)
        .filter((observation): observation is VisualObservation => observation !== null)
        .sort((a, b) => {
          const bTime = new Date(b.capturedAt).getTime();
          const aTime = new Date(a.capturedAt).getTime();
          return (Number.isNaN(bTime) ? 0 : bTime) - (Number.isNaN(aTime) ? 0 : aTime);
        })
    : [];
  const lastObservation = normalizeVisualObservation(candidate.lastObservation) ?? recentObservations[0] ?? null;

  return {
    enabled: Boolean(candidate.enabled || lastObservation || recentObservations.length > 0),
    lastObservation,
    recentObservations,
  };
}

function readStoredVisualContext(): VisualContext {
  if (typeof window === 'undefined') return createEmptyVisualContext();

  try {
    const rawVisualContext = window.localStorage.getItem(VISUAL_CONTEXT_STORAGE_KEY);
    if (!rawVisualContext) return createEmptyVisualContext();
    return normalizeVisualContext(JSON.parse(rawVisualContext));
  } catch {
    return createEmptyVisualContext();
  }
}

function writeStoredVisualContext(visualContext: VisualContext) {
  if (typeof window === 'undefined') return;

  try {
    window.localStorage.setItem(
      VISUAL_CONTEXT_STORAGE_KEY,
      JSON.stringify(normalizeVisualContext(visualContext)),
    );
  } catch (error) {
    console.warn('Visual context local save failed:', error);
  }
}

function dispatchVisualContextState(visualContext: VisualContext) {
  if (typeof window === 'undefined') return;

  window.dispatchEvent(
    new CustomEvent(VISUAL_CONTEXT_STATE_EVENT, {
      detail: { visualContext: normalizeVisualContext(visualContext) },
    }),
  );
}

function applyVisualContext(visualContext: VisualContext) {
  const normalizedContext = normalizeVisualContext(visualContext);
  writeStoredVisualContext(normalizedContext);
  dispatchVisualContextState(normalizedContext);
}

function formatVisualObservationTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'unknown time';

  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function describeVisualObservation(observation: VisualObservation): string {
  const sourceText = observation.source === 'manual' ? 'manual' : observation.source;
  return `${observation.summary} (${sourceText}, ${formatVisualObservationTime(observation.capturedAt)})`;
}

function describeVisualContext(visualContext: VisualContext): string {
  const normalizedContext = normalizeVisualContext(visualContext);
  const lastObservation = normalizedContext.lastObservation ?? normalizedContext.recentObservations[0] ?? null;

  if (!lastObservation) {
    return normalizedContext.enabled
      ? 'Visual context is enabled, but no observations have been saved yet.'
      : 'No visual observations have been saved yet.';
  }

  const recentCount = normalizedContext.recentObservations.length;
  const recentText = recentCount > 1
    ? ` ${recentCount} recent visual observations are saved.`
    : '';

  return `Last visual observation: ${describeVisualObservation(lastObservation)}.${recentText}`;
}


function describeLastVisualObservation(visualContext: VisualContext): string {
  const normalizedContext = normalizeVisualContext(visualContext);
  const lastObservation = normalizedContext.lastObservation ?? normalizedContext.recentObservations[0] ?? null;

  if (!lastObservation) {
    return 'No visual observations have been saved yet.';
  }

  return `Last visual observation: ${describeVisualObservation(lastObservation)}.`;
}

function describeVisualHistory(visualContext: VisualContext): string {
  const normalizedContext = normalizeVisualContext(visualContext);
  const observations = normalizedContext.recentObservations.slice(0, 5);

  if (observations.length === 0) {
    return 'No visual observations have been saved yet.';
  }

  const lines = observations.map((observation, index) => {
    return `${index + 1}. ${describeVisualObservation(observation)}`;
  });
  const remaining = normalizedContext.recentObservations.length - observations.length;

  return `Recent visual observations: ${lines.join('; ')}${remaining > 0 ? `; plus ${remaining} more` : ''}.`;
}

function describeVisualContextSummary(visualContext: VisualContext): string {
  const normalizedContext = normalizeVisualContext(visualContext);
  const observations = normalizedContext.recentObservations;
  const lastObservation = normalizedContext.lastObservation ?? observations[0] ?? null;

  if (!lastObservation) {
    return normalizedContext.enabled
      ? 'Visual context is enabled, but no visual observations have been saved yet.'
      : 'Visual context is empty. Use a manual visual note or Analyze Snapshot to add an observation.';
  }

  const sourceCounts = observations.reduce<Record<string, number>>((counts, observation) => {
    counts[observation.source] = (counts[observation.source] ?? 0) + 1;
    return counts;
  }, {});
  const sourceText = Object.entries(sourceCounts)
    .map(([source, count]) => `${count} ${source}`)
    .join(', ');
  const linkedCount = observations.filter((observation) => observation.relatedFocusId).length;

  return [
    `Visual context summary: ${observations.length} saved observation${observations.length === 1 ? '' : 's'}${sourceText ? ` (${sourceText})` : ''}.`,
    `Latest: ${describeVisualObservation(lastObservation)}.`,
    linkedCount > 0
      ? `${linkedCount} observation${linkedCount === 1 ? '' : 's'} linked to a focus session.`
      : 'No observations are linked to a focus session yet.',
  ].join(' ');
}


function describeVisualContextByReadMode(visualContext: VisualContext, readMode: string | undefined): string {
  const normalizedReadMode = (readMode ?? '').toLowerCase().trim();

  if (normalizedReadMode === 'last') {
    return describeLastVisualObservation(visualContext);
  }

  if (normalizedReadMode === 'history' || normalizedReadMode === 'observations') {
    return describeVisualHistory(visualContext);
  }

  if (normalizedReadMode === 'summary' || normalizedReadMode === 'recap') {
    return describeVisualContextSummary(visualContext);
  }

  return describeVisualContext(visualContext);
}

function getFocusLinkedVisualObservations(
  visualContext: VisualContext,
  activeSession: ActiveSession | null,
): VisualObservation[] {
  if (!activeSession) return [];
  return normalizeVisualContext(visualContext).recentObservations.filter(
    (observation) => observation.relatedFocusId === activeSession.id,
  );
}

function describeFocusVisualObservations(activeSession: ActiveSession | null): string {
  if (!activeSession) {
    return 'No active focus session is running, so there are no focus-linked visual observations to show.';
  }

  const linkedObservations = getFocusLinkedVisualObservations(
    readStoredVisualContext(),
    activeSession,
  );

  if (linkedObservations.length === 0) {
    return `No visual observations are linked to the current focus: ${activeSession.title}. Use "save this visual context to my focus" after a camera analysis or manual visual note to attach one.`;
  }

  const lines = linkedObservations.slice(0, 5).map((observation, index) => {
    return `${index + 1}. ${describeVisualObservation(observation)}`;
  });
  const remaining = linkedObservations.length - lines.length;

  return `Visual observations linked to ${activeSession.title}: ${lines.join('; ')}${remaining > 0 ? `; plus ${remaining} more` : ''}.`;
}

function linkLatestVisualObservationToFocus(): {
  activeSession: ActiveSession | null;
  observation: VisualObservation | null;
  visualContext: VisualContext;
  alreadyLinked: boolean;
} {
  const activeSession = readStoredActiveSession();
  const previousContext = readStoredVisualContext();
  const observation = previousContext.lastObservation ?? previousContext.recentObservations[0] ?? null;

  if (!activeSession || !observation) {
    return {
      activeSession,
      observation,
      visualContext: previousContext,
      alreadyLinked: false,
    };
  }

  if (observation.relatedFocusId === activeSession.id) {
    return {
      activeSession,
      observation,
      visualContext: previousContext,
      alreadyLinked: true,
    };
  }

  const linkedObservation: VisualObservation = {
    ...observation,
    relatedFocusId: activeSession.id,
  };
  const recentObservations = [
    linkedObservation,
    ...previousContext.recentObservations.filter(
      (item) => item.id !== observation.id,
    ),
  ].slice(0, 20);
  const nextContext = normalizeVisualContext({
    enabled: true,
    lastObservation: linkedObservation,
    recentObservations,
  });

  applyVisualContext(nextContext);
  updateVisualContext({
    lastObservation: linkedObservation,
    recentObservations,
    enabled: true,
  }).then((response) => {
    if (response.visualContext) {
      applyVisualContext(normalizeVisualContext(response.visualContext));
    }
  }).catch((error) => {
    console.warn('Visual focus-link backend update failed:', error);
  });

  return {
    activeSession,
    observation: linkedObservation,
    visualContext: nextContext,
    alreadyLinked: false,
  };
}

function addLocalVisualObservation(summary: string): VisualObservation | null {
  const trimmedSummary = summary.trim();
  if (!trimmedSummary) return null;

  const activeSession = readStoredActiveSession();
  const observation: VisualObservation = {
    id: createId('visual'),
    source: 'manual',
    summary: trimmedSummary,
    capturedAt: new Date().toISOString(),
    ...(activeSession ? { relatedFocusId: activeSession.id } : {}),
  };

  const previousContext = readStoredVisualContext();
  const nextContext = normalizeVisualContext({
    enabled: true,
    lastObservation: observation,
    recentObservations: [
      observation,
      ...previousContext.recentObservations.filter((item) => item.id !== observation.id),
    ].slice(0, 20),
  });

  applyVisualContext(nextContext);

  createVisualObservation({
    summary: observation.summary,
    source: 'manual',
    capturedAt: observation.capturedAt,
    ...(observation.relatedFocusId ? { relatedFocusId: observation.relatedFocusId } : {}),
  })
    .then((response) => {
      if (response.visualContext) {
        applyVisualContext(normalizeVisualContext(response.visualContext));
      }
    })
    .catch((error) => {
      console.warn('Visual observation backend save failed:', error);
    });

  return observation;
}

function clearStoredVisualContext() {
  const emptyContext = createEmptyVisualContext();
  applyVisualContext(emptyContext);
  clearVisualContext()
    .then((response) => {
      if (response.visualContext) {
        applyVisualContext(normalizeVisualContext(response.visualContext));
      }
    })
    .catch((error) => {
      console.warn('Visual context backend clear failed:', error);
    });
}

function deleteLastStoredVisualObservation(): VisualObservation | null {
  const previousContext = readStoredVisualContext();
  const observation = previousContext.lastObservation ?? previousContext.recentObservations[0] ?? null;
  if (!observation) return null;

  const remainingObservations = previousContext.recentObservations.filter(
    (item) => item.id !== observation.id,
  );
  const nextContext = normalizeVisualContext({
    enabled: previousContext.enabled && remainingObservations.length > 0,
    lastObservation: remainingObservations[0] ?? null,
    recentObservations: remainingObservations,
  });

  applyVisualContext(nextContext);

  deleteVisualObservationById(observation.id)
    .then((response) => {
      if (response.visualContext) {
        applyVisualContext(normalizeVisualContext(response.visualContext));
      }
    })
    .catch((error) => {
      console.warn('Visual observation backend delete failed:', error);
    });

  return observation;
}

function formatFocusHistoryTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'unknown time';

  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function selectRecentFocusSession(mode?: MemorySessionMode): RecentFocusSession | null {
  const sessions = readStoredRecentFocusSessions();
  if (!mode) return sessions[0] ?? null;

  return sessions.find((session) => session.mode === mode) ?? null;
}

function describeRecentFocusSession(
  session: RecentFocusSession | null,
  label = 'Last focus',
): string {
  if (!session) {
    return 'No recent focus sessions have been saved yet.';
  }

  const goalText = session.goal ? ` Goal: ${session.goal}.` : ' No goal was set.';
  const taskText = session.linkedTaskIds.length > 0
    ? ` ${session.linkedTaskIds.length} linked task${session.linkedTaskIds.length === 1 ? '' : 's'}.`
    : '';
  const noteText = session.pinnedNoteIds.length > 0 || session.summaryNoteId
    ? ' Summary note saved.'
    : '';

  return `${label}: ${session.title}. Mode: ${session.mode}. Ended: ${formatFocusHistoryTime(session.endedAt)}.${goalText}${taskText}${noteText}`;
}

function describeRecentFocusSessions(sessions: RecentFocusSession[]): string {
  if (sessions.length === 0) {
    return 'No recent focus sessions have been saved yet.';
  }

  const sessionLines = sessions.slice(0, 5).map((session, index) => {
    const goalText = session.goal ? ` Goal: ${session.goal}.` : '';
    const taskText = session.linkedTaskIds.length > 0
      ? ` ${session.linkedTaskIds.length} task${session.linkedTaskIds.length === 1 ? '' : 's'}.`
      : '';
    const noteText = session.pinnedNoteIds.length > 0 || session.summaryNoteId
      ? ' Saved note.'
      : '';

    return `${index + 1}. ${session.title} (${session.mode}) ended ${formatFocusHistoryTime(session.endedAt)}.${goalText}${taskText}${noteText}`;
  });

  return `Recent focus sessions: ${sessionLines.join(' ')}`;
}

function createActiveSessionFromRecent(session: RecentFocusSession): ActiveSession {
  const now = new Date().toISOString();

  return {
    id: createId('session'),
    title: session.title,
    mode: session.mode,
    goal: session.goal,
    startedAt: now,
    updatedAt: now,
    pinnedNoteIds: [...session.pinnedNoteIds],
    linkedTaskIds: [...session.linkedTaskIds],
  };
}

function readStoredMemoryTasks(): MemoryTask[] {
  if (typeof window === 'undefined') return [];

  try {
    const rawTasks = window.localStorage.getItem(MEMORY_TASKS_STORAGE_KEY);
    if (!rawTasks) return [];
    const parsedTasks = JSON.parse(rawTasks);
    if (!Array.isArray(parsedTasks)) return [];

    return parsedTasks
      .filter((task) => task && typeof task.title === 'string')
      .map((task) => ({
        id: typeof task.id === 'string' ? task.id : createId('task'),
        title: task.title,
        createdAt:
          typeof task.createdAt === 'string'
            ? task.createdAt
            : new Date().toISOString(),
        ...(typeof task.completedAt === 'string'
          ? { completedAt: task.completedAt }
          : {}),
      }));
  } catch {
    return [];
  }
}

type StoredRecentAction = {
  id: string;
  label: string;
  detail: string;
  createdAt: string;
};

function readStoredRecentActions(): StoredRecentAction[] {
  if (typeof window === 'undefined') return [];

  try {
    const rawActions = window.localStorage.getItem(RECENT_ACTIONS_STORAGE_KEY);
    if (!rawActions) return [];
    const parsedActions = JSON.parse(rawActions);
    if (!Array.isArray(parsedActions)) return [];

    return parsedActions
      .filter((action) => action && typeof action.label === 'string')
      .map((action) => ({
        id: typeof action.id === 'string' ? action.id : createId('action'),
        label: action.label,
        detail: typeof action.detail === 'string' ? action.detail : '',
        createdAt:
          typeof action.createdAt === 'string'
            ? action.createdAt
            : new Date().toISOString(),
      }));
  } catch {
    return [];
  }
}


type StoredNote = {
  id: string;
  content: string;
  createdAt: string;
};

function readStoredNotes(): StoredNote[] {
  if (typeof window === 'undefined') return [];

  try {
    const rawNotes = window.localStorage.getItem(NOTES_STORAGE_KEY);
    if (!rawNotes) return [];
    const parsedNotes = JSON.parse(rawNotes);
    if (!Array.isArray(parsedNotes)) return [];

    return parsedNotes
      .filter((note) => note && typeof note.content === 'string')
      .map((note) => ({
        id: typeof note.id === 'string' ? note.id : createId('note'),
        content: note.content,
        createdAt:
          typeof note.createdAt === 'string'
            ? note.createdAt
            : new Date().toISOString(),
      }));
  } catch {
    return [];
  }
}

type RecapWindow = {
  label: string;
  start?: Date;
  end?: Date;
};

function startOfLocalDay(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

function addDays(value: Date, days: number): Date {
  const next = new Date(value);
  next.setDate(next.getDate() + days);
  return next;
}

function getFocusRecapWindow(rawPayload: string | undefined): RecapWindow {
  const payload = (rawPayload ?? '').toLowerCase();
  const todayStart = startOfLocalDay(new Date());

  if (/yesterday/.test(payload) && !/since/.test(payload)) {
    const yesterdayStart = addDays(todayStart, -1);
    return {
      label: 'Yesterday',
      start: yesterdayStart,
      end: todayStart,
    };
  }

  if (/since-yesterday|since yesterday|changed/.test(payload)) {
    return {
      label: 'Since yesterday',
      start: addDays(todayStart, -1),
    };
  }

  if (/today/.test(payload)) {
    return {
      label: 'Today',
      start: todayStart,
      end: addDays(todayStart, 1),
    };
  }

  return {
    label: 'Recent focus activity',
    start: addDays(todayStart, -7),
  };
}

function timeValue(value: string | undefined): number {
  if (!value) return 0;
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? 0 : time;
}

function isWithinRecapWindow(value: string | undefined, window: RecapWindow): boolean {
  const time = timeValue(value);
  if (!time) return false;
  if (window.start && time < window.start.getTime()) return false;
  if (window.end && time >= window.end.getTime()) return false;
  return true;
}

function compactRecapText(value: string, maxLength = 80): string {
  const cleaned = value.replace(/\s+/g, ' ').trim();
  if (cleaned.length <= maxLength) return cleaned;
  return `${cleaned.slice(0, maxLength - 1).trim()}…`;
}

function formatRecapItemTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'unknown time';

  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function describeTaskList(tasks: MemoryTask[], label: string, maxItems = 4): string {
  if (tasks.length === 0) return '';
  const taskLines = tasks.slice(0, maxItems).map((task, index) => {
    const status = task.completedAt ? 'done' : 'open';
    return `${index + 1}. ${compactRecapText(task.title, 72)} (${status})`;
  });
  const remaining = tasks.length - taskLines.length;
  return `${label}: ${taskLines.join('; ')}${remaining > 0 ? `; plus ${remaining} more` : ''}.`;
}

function buildFocusActivityRecap(rawPayload: string | undefined): string {
  const window = getFocusRecapWindow(rawPayload);
  const activeSession = readStoredActiveSession();
  const recentSessions = readStoredRecentFocusSessions().filter((session) =>
    isWithinRecapWindow(session.endedAt, window),
  );
  const tasks = readStoredMemoryTasks();
  const windowTasks = tasks
    .filter((task) =>
      isWithinRecapWindow(task.completedAt ?? task.createdAt, window),
    )
    .sort((a, b) => timeValue(b.completedAt ?? b.createdAt) - timeValue(a.completedAt ?? a.createdAt));
  const openTasks = tasks
    .filter((task) => !task.completedAt)
    .slice(0, 5);
  const notes = readStoredNotes()
    .filter((note) => isWithinRecapWindow(note.createdAt, window))
    .sort((a, b) => timeValue(b.createdAt) - timeValue(a.createdAt));
  const actions = readStoredRecentActions()
    .filter((action) => isWithinRecapWindow(action.createdAt, window))
    .sort((a, b) => timeValue(b.createdAt) - timeValue(a.createdAt));

  const lines: string[] = [`${window.label} recap.`];

  if (activeSession) {
    lines.push(
      `Active focus: ${activeSession.title} (${activeSession.mode}).${
        activeSession.goal ? ` Goal: ${activeSession.goal}.` : ' No goal set.'
      }${
        activeSession.linkedTaskIds.length > 0
          ? ` ${activeSession.linkedTaskIds.length} linked task${activeSession.linkedTaskIds.length === 1 ? '' : 's'}.`
          : ''
      }`,
    );
  }

  if (recentSessions.length > 0) {
    const sessionLines = recentSessions.slice(0, 4).map((session, index) => {
      const goalText = session.goal ? ` — ${compactRecapText(session.goal, 70)}` : '';
      return `${index + 1}. ${session.title} (${session.mode}, ended ${formatRecapItemTime(session.endedAt)})${goalText}`;
    });
    const remaining = recentSessions.length - sessionLines.length;
    lines.push(
      `Ended focus sessions: ${sessionLines.join('; ')}${remaining > 0 ? `; plus ${remaining} more` : ''}.`,
    );
  }

  const completedTasks = windowTasks.filter((task) => task.completedAt);
  const createdTasks = windowTasks.filter((task) => !task.completedAt);
  const completedTaskText = describeTaskList(completedTasks, 'Completed tasks');
  if (completedTaskText) lines.push(completedTaskText);
  const createdTaskText = describeTaskList(createdTasks, 'New open tasks');
  if (createdTaskText) lines.push(createdTaskText);

  if (openTasks.length > 0) {
    lines.push(describeTaskList(openTasks, 'Current open tasks'));
  }

  if (notes.length > 0) {
    const noteLines = notes.slice(0, 3).map((note, index) => {
      return `${index + 1}. ${compactRecapText(note.content, 84)}`;
    });
    const remaining = notes.length - noteLines.length;
    lines.push(`Notes saved: ${noteLines.join('; ')}${remaining > 0 ? `; plus ${remaining} more` : ''}.`);
  }

  if (actions.length > 0) {
    const actionLines = actions.slice(0, 5).map((action) => {
      const detail = action.detail ? ` — ${compactRecapText(action.detail, 60)}` : '';
      return `${action.label}${detail}`;
    });
    lines.push(`Recent actions: ${actionLines.join('; ')}.`);
  }

  if (lines.length === 1) {
    return `${window.label} recap. I do not see focus sessions, tasks, notes, or recent actions in that window yet.`;
  }

  return lines.join(' ');
}


function normalizeEnhancedRecapPayload(rawPayload: string | undefined): string {
  const payload = (rawPayload ?? '')
    .toLowerCase()
    .replace(/\s+/g, '-')
    .trim();

  if (payload.includes('today')) return 'today';
  if (payload.includes('yesterday') && !payload.includes('since')) return 'yesterday';
  if (payload.includes('week') || payload.includes('weekly')) return 'recent';
  if (payload.includes('next-priority') || payload.includes('priority')) return 'next-priority';
  return payload || 'enhanced-recent';
}

function buildEnhancedFocusRecapVisibleText(rawPayload: string | undefined): string {
  const payload = normalizeEnhancedRecapPayload(rawPayload);

  if (payload === 'today') return 'Enhanced recap for today';
  if (payload === 'yesterday') return 'Enhanced recap for yesterday';
  if (payload === 'next-priority') return 'What should I focus on next?';
  return 'Enhanced recent focus recap';
}

function buildEnhancedFocusRecapPrompt(rawPayload: string | undefined): string {
  const payload = normalizeEnhancedRecapPayload(rawPayload);
  const localRecapPayload = payload === 'next-priority' ? 'recent' : payload;
  const localRecap = buildFocusActivityRecap(localRecapPayload);
  const activeSession = readStoredActiveSession();
  const recentSessions = readStoredRecentFocusSessions().slice(0, 6);
  const tasks = readStoredMemoryTasks();
  const openTasks = tasks.filter((task) => !task.completedAt).slice(0, 8);
  const recentlyCompletedTasks = tasks
    .filter((task) => task.completedAt)
    .sort((a, b) => timeValue(b.completedAt) - timeValue(a.completedAt))
    .slice(0, 8);
  const notes = readStoredNotes()
    .sort((a, b) => timeValue(b.createdAt) - timeValue(a.createdAt))
    .slice(0, 6);
  const actions = readStoredRecentActions()
    .sort((a, b) => timeValue(b.createdAt) - timeValue(a.createdAt))
    .slice(0, 10);

  const activeFocusText = activeSession
    ? [
        `Title: ${activeSession.title}`,
        `Mode: ${activeSession.mode}`,
        activeSession.goal ? `Goal: ${activeSession.goal}` : 'Goal: none set',
        `Started: ${activeSession.startedAt}`,
        `Updated: ${activeSession.updatedAt}`,
        `Linked task count: ${activeSession.linkedTaskIds.length}`,
        `Pinned note count: ${activeSession.pinnedNoteIds.length}`,
      ].join('\n')
    : 'No active focus session.';

  const recentFocusText = recentSessions.length > 0
    ? recentSessions
        .map((session, index) => {
          return `${index + 1}. ${session.title} (${session.mode}) ended ${session.endedAt}${session.goal ? ` — goal: ${session.goal}` : ''}${session.summaryNoteId || session.pinnedNoteIds.length > 0 ? ' — summary saved' : ''}`;
        })
        .join('\n')
    : 'No recent focus sessions.';

  const openTaskText = openTasks.length > 0
    ? openTasks.map((task, index) => `${index + 1}. ${task.title}`).join('\n')
    : 'No open tasks.';

  const completedTaskText = recentlyCompletedTasks.length > 0
    ? recentlyCompletedTasks.map((task, index) => `${index + 1}. ${task.title} — completed ${task.completedAt}`).join('\n')
    : 'No recently completed tasks.';

  const noteText = notes.length > 0
    ? notes.map((note, index) => `${index + 1}. ${compactRecapText(note.content, 180)} — saved ${note.createdAt}`).join('\n')
    : 'No recent notes.';

  const actionText = actions.length > 0
    ? actions.map((action, index) => `${index + 1}. ${action.label}${action.detail ? ` — ${action.detail}` : ''} — ${action.createdAt}`).join('\n')
    : 'No recent actions.';

  const modeInstruction = payload === 'next-priority'
    ? 'The user wants help choosing the next priority. Emphasize the strongest next action and why it should come first.'
    : 'The user wants an enhanced natural-language recap. Emphasize progress, changes, open loops, and the next useful action.';

  return [
    'QMeet enhanced work recap request.',
    modeInstruction,
    'Use only the memory snapshot below. Do not invent completed work that is not represented here. If there is not much data, say so and give a small next step.',
    'Write like the orb assistant speaking to the user: direct, practical, and concise.',
    'Use this structure: 1) concise recap, 2) what changed, 3) open loops, 4) suggested next action.',
    'Do not mention localStorage, sessionStorage, JSON, APIs, routes, event names, or implementation details.',
    '',
    `<requested_timeframe>${payload}</requested_timeframe>`,
    '<local_recap_fallback>',
    localRecap,
    '</local_recap_fallback>',
    '<active_focus>',
    activeFocusText,
    '</active_focus>',
    '<recent_focus_sessions>',
    recentFocusText,
    '</recent_focus_sessions>',
    '<open_tasks>',
    openTaskText,
    '</open_tasks>',
    '<recently_completed_tasks>',
    completedTaskText,
    '</recently_completed_tasks>',
    '<recent_notes>',
    noteText,
    '</recent_notes>',
    '<recent_actions>',
    actionText,
    '</recent_actions>',
  ].join('\n');
}

function dispatchEnhancedFocusRecapChat(rawPayload: string | undefined) {
  if (typeof window === 'undefined') return;

  const detail: EnhancedFocusRecapChatEventDetail = {
    prompt: buildEnhancedFocusRecapPrompt(rawPayload),
    visibleText: buildEnhancedFocusRecapVisibleText(rawPayload),
  };

  window.setTimeout(() => {
    window.dispatchEvent(
      new CustomEvent<EnhancedFocusRecapChatEventDetail>(
        ENHANCED_FOCUS_RECAP_CHAT_EVENT,
        { detail },
      ),
    );
  }, 0);
}

function writeStoredActiveSession(activeSession: ActiveSession | null) {
  if (typeof window === 'undefined') return;

  try {
    if (activeSession) {
      const serializedSession = JSON.stringify(activeSession);
      window.localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, serializedSession);
      window.sessionStorage.setItem(
        ACTIVE_SESSION_SESSION_STORAGE_KEY,
        serializedSession,
      );
    } else {
      window.localStorage.removeItem(ACTIVE_SESSION_STORAGE_KEY);
      window.sessionStorage.removeItem(ACTIVE_SESSION_SESSION_STORAGE_KEY);
    }
  } catch (error) {
    console.error('Failed to write active session fallback:', error);
  }
}

function dispatchActiveSessionState(activeSession: ActiveSession | null) {
  if (typeof window === 'undefined') return;

  window.dispatchEvent(
    new CustomEvent<ActiveSessionStateEventDetail>(ACTIVE_SESSION_STATE_EVENT, {
      detail: { activeSession },
    }),
  );
}


function dispatchFocusSummaryNote(
  activeSession: ActiveSession,
  summary: string,
  options: { endAfterSave?: boolean } = {},
) {
  if (typeof window === 'undefined') return;

  window.dispatchEvent(
    new CustomEvent(SAVE_FOCUS_SUMMARY_NOTE_EVENT, {
      detail: {
        sessionId: activeSession.id,
        summary,
        title: activeSession.title,
        endAfterSave: Boolean(options.endAfterSave),
      },
    }),
  );
}

function persistActiveSessionToBackend(activeSession: ActiveSession | null) {
  if (activeSession) {
    replaceActiveSession({ activeSession }).catch((error) => {
      console.warn('Active session backend save failed:', error);
    });
    return;
  }

  clearActiveSession().catch((error) => {
    console.warn('Active session backend clear failed:', error);
  });
}

function patchActiveSessionInBackend(
  updates: Partial<
    Pick<
      ActiveSession,
      'title' | 'mode' | 'goal' | 'pinnedNoteIds' | 'linkedTaskIds' | 'summary'
    >
  >,
) {
  updateActiveSession(updates).catch((error) => {
    console.warn('Active session backend update failed:', error);
  });
}

function applyActiveSession(activeSession: ActiveSession | null) {
  writeStoredActiveSession(activeSession);
  dispatchActiveSessionState(activeSession);
}

function createActiveSession(
  payload: FocusSessionCommandPayload | undefined,
  fallbackTitle?: string,
): ActiveSession {
  const now = new Date().toISOString();
  const title =
    payload?.title?.trim() || fallbackTitle?.trim() || 'Focus session';
  const mode = isMemorySessionMode(payload?.mode) ? payload.mode : 'general';
  const goal = payload?.goal?.trim() ?? '';

  return {
    id: createId('session'),
    title,
    mode,
    goal,
    startedAt: now,
    updatedAt: now,
    pinnedNoteIds: [],
    linkedTaskIds: [],
  };
}

function updateLocalActiveSession(
  payload: FocusSessionCommandPayload | undefined,
): ActiveSession {
  const existingSession = readStoredActiveSession();

  if (!existingSession) {
    return createActiveSession(
      {
        title: payload?.title?.trim() || 'Focus session',
        mode: payload?.mode,
        goal: payload?.goal,
      },
      'Focus session',
    );
  }

  return {
    ...existingSession,
    ...(payload?.title?.trim() ? { title: payload.title.trim() } : {}),
    ...(isMemorySessionMode(payload?.mode) ? { mode: payload.mode } : {}),
    ...(typeof payload?.goal === 'string'
      ? { goal: payload.goal.trim() }
      : {}),
    updatedAt: new Date().toISOString(),
  };
}

function describeActiveSession(activeSession: ActiveSession | null): string {
  if (!activeSession) {
    return 'No active focus session is running.';
  }

  const goalText = activeSession.goal
    ? ` Goal: ${activeSession.goal}.`
    : ' No goal has been set yet.';
  const linkedTaskText =
    activeSession.linkedTaskIds.length > 0
      ? ` ${activeSession.linkedTaskIds.length} linked task${
          activeSession.linkedTaskIds.length === 1 ? '' : 's'
        }.`
      : '';
  const pinnedNoteText =
    activeSession.pinnedNoteIds.length > 0
      ? ` ${activeSession.pinnedNoteIds.length} pinned note${
          activeSession.pinnedNoteIds.length === 1 ? '' : 's'
        }.`
      : '';
  const linkedVisualCount = getFocusLinkedVisualObservations(
    readStoredVisualContext(),
    activeSession,
  ).length;
  const linkedVisualText =
    linkedVisualCount > 0
      ? ` ${linkedVisualCount} linked visual observation${
          linkedVisualCount === 1 ? '' : 's'
        }.`
      : '';

  return `Current focus: ${activeSession.title}. Mode: ${activeSession.mode}.${goalText}${linkedTaskText}${pinnedNoteText}${linkedVisualText}`;
}

function normalizeFocusPayload(
  payload: FocusSessionCommandPayload | undefined,
): NormalizedFocusPayload {
  const title = payload?.title?.trim();
  const goal = payload?.goal?.trim();
  const mode = isMemorySessionMode(payload?.mode) ? payload.mode : undefined;

  return {
    ...(title ? { title } : {}),
    ...(mode ? { mode } : {}),
    ...(goal ? { goal } : {}),
  };
}


function compactTaskSubject(value: string, fallback: string): string {
  const cleaned = value.replace(/\s+/g, ' ').trim();
  if (!cleaned) return fallback;
  return cleaned.length > 72 ? `${cleaned.slice(0, 69).trim()}...` : cleaned;
}

function uniqueTaskTitles(titles: string[]): string[] {
  const seen = new Set<string>();
  const uniqueTitles: string[] = [];

  for (const title of titles) {
    const cleaned = title.replace(/\s+/g, ' ').trim();
    if (!cleaned) continue;
    const key = cleaned.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    uniqueTitles.push(cleaned);
  }

  return uniqueTitles.slice(0, 5);
}

function generateFocusTaskTitles(activeSession: ActiveSession): string[] {
  const title = compactTaskSubject(activeSession.title, 'current focus');
  const goal = compactTaskSubject(activeSession.goal, title);
  const target = activeSession.goal ? goal : title;

  switch (activeSession.mode) {
    case 'coding':
      return uniqueTaskTitles([
        `Define the target behavior for ${title}`,
        `Inspect the relevant code paths for ${title}`,
        `Implement the smallest working change for ${target}`,
        `Test ${title} from the UI and backend`,
        `Commit the finished ${title} changes`,
      ]);
    case 'research':
      return uniqueTaskTitles([
        `List the key questions for ${title}`,
        `Gather useful sources or examples for ${target}`,
        `Compare findings and note tradeoffs for ${title}`,
        `Decide the next action from the ${title} research`,
      ]);
    case 'meeting':
      return uniqueTaskTitles([
        `Clarify the meeting objective for ${title}`,
        `Prepare agenda points for ${target}`,
        `Capture decisions from ${title}`,
        `Save follow-up tasks after ${title}`,
      ]);
    case 'planning':
      return uniqueTaskTitles([
        `Define the desired outcome for ${title}`,
        `Break ${target} into milestones`,
        `Identify blockers and dependencies for ${title}`,
        `Choose the first next action for ${title}`,
      ]);
    case 'personal':
      return uniqueTaskTitles([
        `Clarify what success looks like for ${title}`,
        `Choose one small next step for ${target}`,
        `Set aside time for ${title}`,
        `Review progress on ${title}`,
      ]);
    default:
      return uniqueTaskTitles([
        `Clarify the outcome for ${title}`,
        `Break ${target} into smaller steps`,
        `Identify the next concrete action for ${title}`,
        `Review progress and update the focus session`,
      ]);
  }
}

function linkTasksToActiveSession(
  activeSession: ActiveSession,
  tasks: MemoryTask[],
): ActiveSession {
  const linkedTaskIds = Array.from(
    new Set([
      ...activeSession.linkedTaskIds,
      ...tasks.map((task) => task.id).filter(Boolean),
    ]),
  );

  return {
    ...activeSession,
    linkedTaskIds,
    updatedAt: new Date().toISOString(),
  };
}

function describeFocusTasks(activeSession: ActiveSession, tasks: MemoryTask[]): string {
  if (tasks.length === 0) {
    return `I could not create tasks for ${activeSession.title}.`;
  }

  const taskList = tasks
    .map((task, index) => `${index + 1}. ${task.title}`)
    .join(' ');

  return `Added ${tasks.length} task${tasks.length === 1 ? '' : 's'} for ${activeSession.title}: ${taskList}`;
}


function formatFocusSummaryTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unknown';

  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function sentenceList(items: string[], fallback: string): string {
  const cleanedItems = items
    .map((item) => item.replace(/\s+/g, ' ').trim())
    .filter(Boolean);

  if (cleanedItems.length === 0) return fallback;
  return cleanedItems.join('; ');
}

function buildFocusSummary(activeSession: ActiveSession): string {
  const storedTasks = readStoredMemoryTasks();
  const storedRecentActions = readStoredRecentActions();
  const linkedTaskIds = new Set(activeSession.linkedTaskIds);
  const linkedTasks = storedTasks.filter((task) => linkedTaskIds.has(task.id));
  const openLinkedTasks = linkedTasks.filter((task) => !task.completedAt);
  const completedLinkedTasks = linkedTasks.filter((task) => task.completedAt);
  const recentFocusActions = storedRecentActions
    .filter((action) => {
      const actionText = `${action.label} ${action.detail}`.toLowerCase();
      return (
        actionText.includes('focus') ||
        actionText.includes(activeSession.title.toLowerCase()) ||
        (activeSession.goal && actionText.includes(activeSession.goal.toLowerCase()))
      );
    })
    .slice(0, 5)
    .map((action) =>
      action.detail ? `${action.label}: ${action.detail}` : action.label,
    );
  const linkedVisualObservations = getFocusLinkedVisualObservations(
    readStoredVisualContext(),
    activeSession,
  );

  const lines = [
    `Focus summary - ${activeSession.title}`,
    `Mode: ${activeSession.mode}`,
    activeSession.goal ? `Goal: ${activeSession.goal}` : 'Goal: No goal set',
    `Started: ${formatFocusSummaryTime(activeSession.startedAt)}`,
    `Last updated: ${formatFocusSummaryTime(activeSession.updatedAt)}`,
    linkedTasks.length > 0
      ? `Linked tasks: ${linkedTasks.length} total, ${openLinkedTasks.length} open, ${completedLinkedTasks.length} completed. ${sentenceList(
          linkedTasks.slice(0, 5).map((task) => task.title),
          '',
        )}`.trim()
      : 'Linked tasks: None yet',
    linkedVisualObservations.length > 0
      ? `Linked visual observations: ${linkedVisualObservations.length}. ${sentenceList(
          linkedVisualObservations.slice(0, 3).map((observation) => observation.summary),
          '',
        )}`.trim()
      : 'Linked visual observations: None yet',
    recentFocusActions.length > 0
      ? `Recent focus actions: ${sentenceList(recentFocusActions, 'None yet')}`
      : 'Recent focus actions: None yet',
  ];

  return lines.join('\n');
}

function describeFocusSummary(activeSession: ActiveSession): string {
  const storedTasks = readStoredMemoryTasks();
  const linkedTaskIds = new Set(activeSession.linkedTaskIds);
  const linkedTasks = storedTasks.filter((task) => linkedTaskIds.has(task.id));
  const taskText = linkedTasks.length > 0
    ? ` ${linkedTasks.length} linked task${linkedTasks.length === 1 ? '' : 's'}.`
    : '';
  const linkedVisualCount = getFocusLinkedVisualObservations(
    readStoredVisualContext(),
    activeSession,
  ).length;
  const visualText = linkedVisualCount > 0
    ? ` ${linkedVisualCount} linked visual observation${linkedVisualCount === 1 ? '' : 's'}.`
    : '';
  const goalText = activeSession.goal ? ` Goal: ${activeSession.goal}.` : ' No goal has been set yet.';

  return `Focus summary for ${activeSession.title}. Mode: ${activeSession.mode}.${goalText}${taskText}${visualText}`;
}

function hasSavedFocusSummary(activeSession: ActiveSession): boolean {
  return activeSession.pinnedNoteIds.length > 0 || Boolean(activeSession.summary?.trim());
}

function shouldGuardFocusEnd(activeSession: ActiveSession): boolean {
  if (hasSavedFocusSummary(activeSession)) return false;

  const hasGoal = Boolean(activeSession.goal.trim());
  const hasLinkedTasks = activeSession.linkedTaskIds.length > 0;
  const hasSessionDetail = activeSession.title.trim().toLowerCase() !== 'focus session';

  return hasGoal || hasLinkedTasks || hasSessionDetail;
}

function describeFocusEndGuard(activeSession: ActiveSession): string {
  const storedTasks = readStoredMemoryTasks();
  const linkedTaskIds = new Set(activeSession.linkedTaskIds);
  const linkedTasks = storedTasks.filter((task) => linkedTaskIds.has(task.id));
  const openLinkedTasks = linkedTasks.filter((task) => !task.completedAt).length;
  const completedLinkedTasks = linkedTasks.filter((task) => task.completedAt).length;
  const taskText = linkedTasks.length > 0
    ? ` It has ${linkedTasks.length} linked task${linkedTasks.length === 1 ? '' : 's'} (${openLinkedTasks} open, ${completedLinkedTasks} done).`
    : '';
  const goalText = activeSession.goal ? ` Goal: ${activeSession.goal}.` : '';

  return `You have an active focus with no saved summary note: ${activeSession.title}.${goalText}${taskText} Say "end with summary" to save a note and end it, "end focus anyway" to end without saving, or "cancel" to keep it running.`;
}

function describeFocusStart(payload: FocusSessionCommandPayload | undefined) {
  const title = payload?.title?.trim() || 'Focus session';
  const mode = payload?.mode ? ` ${payload.mode}` : '';
  const goal = payload?.goal?.trim();

  return `Started${mode} focus session: ${title}.${goal ? ` Goal: ${goal}.` : ''}`;
}

function describeFocusUpdate(payload: FocusSessionCommandPayload | undefined) {
  const pieces: string[] = [];

  if (payload?.title?.trim()) {
    pieces.push(`title: ${payload.title.trim()}`);
  }
  if (payload?.mode) {
    pieces.push(`mode: ${payload.mode}`);
  }
  if (payload?.goal?.trim()) {
    pieces.push(`goal: ${payload.goal.trim()}`);
  }

  return pieces.length > 0
    ? `Updated focus session ${pieces.join(', ')}.`
    : 'Focus session updated.';
}


function dispatchCalendarFocusPrep() {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent<CalendarFocusPrepEventDetail>(CALENDAR_FOCUS_PREP_EVENT, {
      detail: {
        requestedAt: new Date().toISOString(),
        source: 'memory-command',
      },
    }),
  );
}

export function handleMemoryCommand(
  commandMatch: CommandMatch,
  deps: {
    voiceOutputEnabled: boolean;
    setActivePanel: (panel: ActivePanel) => void;
    closePanel: () => void;
    getMemoryReadout: () => string;
    saveMemoryTask: (title: string) => MemoryTask | null;
    markMemoryTaskDone: (
      lookup?: string,
      operation?: 'complete' | 'delete',
    ) => MemoryTask | null;
    clearCompletedTasks: () => number;
  },
): MemoryCommandResult {
  switch (commandMatch.command) {
    case 'open-memory':
      deps.setActivePanel('memory');
      return { handled: true };

    case 'close-memory':
      deps.closePanel();
      return { handled: true };

    case 'recap-focus-activity': {
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: buildFocusActivityRecap(commandMatch.payload),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'enhanced-focus-recap': {
      deps.setActivePanel('memory');
      dispatchEnhancedFocusRecapChat(commandMatch.payload);
      return {
        handled: true,
        confirmationContent:
          'Preparing an enhanced recap from your focus history, tasks, notes, and recent actions.',
        shouldSpeakConfirmation: false,
      };
    }


    case 'prepare-calendar-focus': {
      deps.setActivePanel('calendar');
      dispatchCalendarFocusPrep();
      return {
        handled: true,
        confirmationContent:
          'Preparing focus from your next calendar event. I will refresh your calendar, start a meeting prep focus if I find an upcoming event, and show the calendar panel.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'read-last-focus-session': {
      deps.setActivePanel('memory');
      const mode = commandMatch.focusSession?.mode;
      const recentSession = selectRecentFocusSession(mode);
      const label = mode ? `Last ${mode} focus` : 'Last focus';

      return {
        handled: true,
        confirmationContent: describeRecentFocusSession(recentSession, label),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'read-focus-history': {
      deps.setActivePanel('memory');
      const recentSessions = readStoredRecentFocusSessions();

      return {
        handled: true,
        confirmationContent: describeRecentFocusSessions(recentSessions),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'resume-last-focus-session': {
      deps.setActivePanel('memory');
      const mode = commandMatch.focusSession?.mode;
      const recentSession = selectRecentFocusSession(mode);

      if (!recentSession) {
        return {
          handled: true,
          confirmationContent: mode
            ? `No recent ${mode} focus session was found.`
            : 'No recent focus session was found to resume.',
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }

      const resumedSession = createActiveSessionFromRecent(recentSession);
      applyActiveSession(resumedSession);
      persistActiveSessionToBackend(resumedSession);

      return {
        handled: true,
        confirmationContent: `Resumed ${resumedSession.mode} focus session: ${resumedSession.title}.${resumedSession.goal ? ` Goal: ${resumedSession.goal}.` : ''}`,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'read-focus-session': {
      deps.setActivePanel('memory');
      const activeSession = readStoredActiveSession();

      return {
        handled: true,
        confirmationContent: describeActiveSession(activeSession),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'read-memory': {
      deps.setActivePanel('memory');
      const activeSession = readStoredActiveSession();
      const memoryReadout = deps.getMemoryReadout();

      const focusReadout = activeSession ? describeActiveSession(activeSession) : '';
      const normalizedMemoryReadout = activeSession
        ? memoryReadout.replace(/^No active focus session\.\s*/i, '')
        : memoryReadout;

      return {
        handled: true,
        confirmationContent: focusReadout
          ? `${focusReadout} ${normalizedMemoryReadout}`.trim()
          : normalizedMemoryReadout,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'start-focus-session': {
      const detail = normalizeFocusPayload(commandMatch.focusSession);
      const title = detail.title || commandMatch.payload?.trim() || 'Focus session';
      const focusPayload = {
        ...commandMatch.focusSession,
        title,
      };

      const session = createActiveSession(
        focusPayload,
        title,
      );

      applyActiveSession(session);
      persistActiveSessionToBackend(session);
      deps.setActivePanel('memory');

      return {
        handled: true,
        confirmationContent: describeFocusStart(focusPayload),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'update-focus-session': {
      const payload = commandMatch.focusSession ?? {};

      const existingSession = readStoredActiveSession();
      const hadExistingSession = !!existingSession;
      const updatedSession = updateLocalActiveSession(payload);

      applyActiveSession(updatedSession);

      if (hadExistingSession) {
        patchActiveSessionInBackend({
          ...(payload.title?.trim() ? { title: payload.title.trim() } : {}),
          ...(isMemorySessionMode(payload.mode) ? { mode: payload.mode } : {}),
          ...(typeof payload.goal === 'string'
            ? { goal: payload.goal.trim() }
            : {}),
        });
      } else {
        persistActiveSessionToBackend(updatedSession);
      }

      deps.setActivePanel('memory');

      return {
        handled: true,
        confirmationContent: hadExistingSession
          ? describeFocusUpdate(payload)
          : describeFocusStart(updatedSession),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'end-focus-session': {
      const existingSession = readStoredActiveSession();
      deps.setActivePanel('memory');

      if (!existingSession) {
        return {
          handled: true,
          confirmationContent: 'No active focus session was running.',
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }

      const forceEnd = Boolean(commandMatch.focusSession?.forceEnd);
      if (!forceEnd && shouldGuardFocusEnd(existingSession)) {
        return {
          handled: true,
          confirmationContent: describeFocusEndGuard(existingSession),
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }

      applyActiveSession(null);
      persistActiveSessionToBackend(null);
      return {
        handled: true,
        confirmationContent: forceEnd
          ? `Ended focus session without saving a summary: ${existingSession.title}.`
          : `Ended focus session: ${existingSession.title}.`,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }



    case 'summarize-focus-session': {
      const activeSession = readStoredActiveSession();
      deps.setActivePanel('memory');

      if (!activeSession) {
        return {
          handled: true,
          confirmationContent:
            'No active focus session is running. Start a focus session first, then I can summarize it.',
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }

      const summary = buildFocusSummary(activeSession);
      return {
        handled: true,
        confirmationContent: summary,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'save-focus-summary': {
      const activeSession = readStoredActiveSession();

      if (!activeSession) {
        deps.setActivePanel('memory');
        return {
          handled: true,
          confirmationContent:
            'No active focus session is running. Start a focus session first, then I can save a summary note.',
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }

      const summary = buildFocusSummary(activeSession);
      dispatchFocusSummaryNote(activeSession, summary);
      patchActiveSessionInBackend({ summary });
      deps.setActivePanel('notes');

      return {
        handled: true,
        confirmationContent: `Saved focus summary as a note for ${activeSession.title}. ${describeFocusSummary(activeSession)}`,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'end-focus-with-summary': {
      const activeSession = readStoredActiveSession();

      if (!activeSession) {
        deps.setActivePanel('memory');
        return {
          handled: true,
          confirmationContent:
            'No active focus session is running, so there is nothing to summarize or end.',
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }

      const summary = buildFocusSummary(activeSession);
      dispatchFocusSummaryNote(activeSession, summary, { endAfterSave: true });
      applyActiveSession(null);
      persistActiveSessionToBackend(null);
      deps.setActivePanel('notes');

      return {
        handled: true,
        confirmationContent: `Saved a summary note and ended focus session: ${activeSession.title}.`,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'focus-to-tasks': {
      const activeSession = readStoredActiveSession();
      deps.setActivePanel('memory');

      if (!activeSession) {
        return {
          handled: true,
          confirmationContent:
            'No active focus session is running. Start a focus session first, then I can turn it into tasks.',
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }

      const createdTasks = generateFocusTaskTitles(activeSession)
        .map((title) => deps.saveMemoryTask(title))
        .filter((task): task is MemoryTask => task !== null);

      if (createdTasks.length > 0) {
        const updatedSession = linkTasksToActiveSession(activeSession, createdTasks);
        applyActiveSession(updatedSession);
        patchActiveSessionInBackend({ linkedTaskIds: updatedSession.linkedTaskIds });
      }

      return {
        handled: true,
        confirmationContent: describeFocusTasks(activeSession, createdTasks),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'link-visual-to-focus': {
      deps.setActivePanel('memory');
      const result = linkLatestVisualObservationToFocus();

      if (!result.activeSession) {
        return {
          handled: true,
          confirmationContent:
            'No active focus session is running. Start a focus first, then I can link the latest visual observation to it.',
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }

      if (!result.observation) {
        return {
          handled: true,
          confirmationContent:
            'No visual observation has been saved yet. Take and analyze a snapshot, or add a manual visual note first.',
          shouldSpeakConfirmation: deps.voiceOutputEnabled,
        };
      }

      return {
        handled: true,
        confirmationContent: result.alreadyLinked
          ? `The latest visual observation is already linked to ${result.activeSession.title}: ${result.observation.summary}.`
          : `Linked latest visual observation to ${result.activeSession.title}: ${result.observation.summary}.`,
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'read-focus-visuals': {
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: describeFocusVisualObservations(readStoredActiveSession()),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'create-visual-observation': {
      const observation = addLocalVisualObservation(commandMatch.payload ?? '');
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: observation
          ? `Saved visual observation: ${observation.summary}.`
          : 'I did not catch the visual observation text.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'read-visual-context': {
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: describeVisualContextByReadMode(
          readStoredVisualContext(),
          commandMatch.payload,
        ),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'read-last-visual-observation': {
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: describeLastVisualObservation(readStoredVisualContext()),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'read-visual-history': {
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: describeVisualHistory(readStoredVisualContext()),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'summarize-visual-context': {
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: describeVisualContextSummary(readStoredVisualContext()),
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'clear-visual-context': {
      const previousContext = readStoredVisualContext();
      const removedCount = previousContext.recentObservations.length;
      clearStoredVisualContext();
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: removedCount > 0
          ? `Cleared ${removedCount} visual observation${removedCount === 1 ? '' : 's'}.`
          : 'No visual observations to clear.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'delete-last-visual-observation': {
      const deletedObservation = deleteLastStoredVisualObservation();
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: deletedObservation
          ? `Deleted visual observation: ${deletedObservation.summary}.`
          : 'No visual observations to delete.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'remember-task': {
      const savedTask = deps.saveMemoryTask(commandMatch.payload ?? '');
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: savedTask
          ? `Saved task: ${savedTask.title}.`
          : 'I did not catch the task text.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'mark-task-done': {
      const completedTask = deps.markMemoryTaskDone(commandMatch.payload);
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: completedTask
          ? `Marked task done: ${completedTask.title}.`
          : commandMatch.payload
            ? `I could not find an open task matching "${commandMatch.payload}".`
            : 'No open tasks to complete.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'delete-last-task': {
      const deletedTask = deps.markMemoryTaskDone(undefined, 'delete');
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent: deletedTask
          ? `Deleted task: ${deletedTask.title}.`
          : 'No tasks to delete.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    case 'clear-done-tasks': {
      const removedCount = deps.clearCompletedTasks();
      deps.setActivePanel('memory');
      return {
        handled: true,
        confirmationContent:
          removedCount > 0
            ? `Cleared ${removedCount} completed task${
                removedCount === 1 ? '' : 's'
              }.`
            : 'No completed tasks to clear.',
        shouldSpeakConfirmation: deps.voiceOutputEnabled,
      };
    }

    default:
      return { handled: false };
  }
}
