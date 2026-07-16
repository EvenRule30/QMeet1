export type OrbState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

export type ActivePanel =
  | 'none'
  | 'menu'
  | 'settings'
  | 'status'
  | 'notes'
  | 'calendar'
  | 'search'
  | 'memory';

export type AssistantActivityKind =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'search'
  | 'calendar'
  | 'notes'
  | 'settings'
  | 'status'
  | 'navigation'
  | 'memory'
  | 'confirmation'
  | 'error';

export interface AssistantActivity {
  kind: AssistantActivityKind;
  label: string;
  detail: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  variant?: 'normal' | 'tool' | 'notice' | 'error';
}

export interface BackendStatus {
  ok: boolean;
  provider: string;
  model: string;
  hasOpenAIKey: boolean;
  maxOutputTokens: number;
}

export interface Note {
  id: string;
  content: string;
  createdAt: string;
}

export interface MemoryTask {
  id: string;
  title: string;
  createdAt: string;
  completedAt?: string;
}

export interface RecentAction {
  id: string;
  label: string;
  detail: string;
  createdAt: string;
}

export type MemorySessionMode =
  | 'general'
  | 'coding'
  | 'meeting'
  | 'planning'
  | 'research'
  | 'personal';

export interface ActiveSession {
  id: string;
  title: string;
  mode: MemorySessionMode;
  goal: string;
  startedAt: string;
  updatedAt: string;
  pinnedNoteIds: string[];
  linkedTaskIds: string[];
  summary?: string | null;
}

export interface RecentFocusSession {
  id: string;
  title: string;
  mode: MemorySessionMode;
  goal: string;
  startedAt: string;
  endedAt: string;
  pinnedNoteIds: string[];
  linkedTaskIds: string[];
  summary?: string | null;
  summaryNoteId?: string | null;
}

export interface ActiveSessionReplaceRequest {
  activeSession: ActiveSession | null;
}

export interface ActiveSessionUpdateRequest {
  title?: string | null;
  mode?: MemorySessionMode | null;
  goal?: string | null;
  pinnedNoteIds?: string[] | null;
  linkedTaskIds?: string[] | null;
  summary?: string | null;
}

export interface ActiveSessionResponse {
  ok: boolean;
  provider: 'local-json';
  activeSession: ActiveSession | null;
  message: string;
}

export interface ActiveSessionClearResponse {
  ok: boolean;
  provider: 'local-json';
  activeSession: ActiveSession | null;
  removedActiveSession: boolean;
  recentFocusSessions?: RecentFocusSession[];
  archivedFocusSession?: RecentFocusSession | null;
  message: string;
}


export interface RecentFocusSessionsReplaceRequest {
  recentFocusSessions: RecentFocusSession[];
}

export interface RecentFocusSessionsResponse {
  ok: boolean;
  provider: 'local-json';
  recentFocusSessions: RecentFocusSession[];
  message: string;
}

export interface RecentFocusSessionDeleteResponse {
  ok: boolean;
  provider: 'local-json';
  deletedRecentFocusSessionId: string;
  message: string;
}

export interface RecentFocusSessionsClearResponse {
  ok: boolean;
  provider: 'local-json';
  removedCount: number;
  recentFocusSessions: RecentFocusSession[];
  message: string;
}

export interface MemoryStatusResponse {
  ok: boolean;
  provider: 'local-json';
  configured: boolean;
  path: string;
  taskCount: number;
  completedCount: number;
  actionCount: number;
  noteCount: number;
  activeSessionSet?: boolean;
  activeSessionTitle?: string;
  recentFocusSessionCount?: number;
  lastFocusSessionTitle?: string;
  message: string;
}

export interface MemoryTasksResponse {
  ok: boolean;
  provider: 'local-json';
  tasks: MemoryTask[];
  message: string;
}

export interface MemoryTaskCreateRequest {
  title: string;
}

export interface MemoryTasksReplaceRequest {
  tasks: MemoryTask[];
}

export interface MemoryTaskUpdateRequest {
  title?: string;
  completedAt?: string | null;
}

export interface MemoryTaskDeleteResponse {
  ok: boolean;
  provider: 'local-json';
  deletedTaskId: string;
  message: string;
}

export interface MemoryClearCompletedResponse {
  ok: boolean;
  provider: 'local-json';
  removedCount: number;
  tasks: MemoryTask[];
  message: string;
}

export interface MemoryContextReplaceRequest {
  tasks: MemoryTask[];
  recentActions: RecentAction[];
  notes: Note[];
  activeSession?: ActiveSession | null;
  recentFocusSessions?: RecentFocusSession[];
}

export interface MemoryContextResponse {
  ok: boolean;
  provider: 'local-json';
  tasks: MemoryTask[];
  recentActions: RecentAction[];
  notes: Note[];
  activeSession?: ActiveSession | null;
  recentFocusSessions?: RecentFocusSession[];
  archivedFocusSession?: RecentFocusSession | null;
  message: string;
}

export interface MemoryContextExportResponse {
  ok: boolean;
  provider: 'local-json';
  version: number;
  exportedAt: string;
  tasks: MemoryTask[];
  recentActions: RecentAction[];
  notes: Note[];
  activeSession?: ActiveSession | null;
  recentFocusSessions?: RecentFocusSession[];
  message: string;
}

export interface MemoryContextImportRequest {
  tasks: MemoryTask[];
  recentActions: RecentAction[];
  notes: Note[];
  activeSession?: ActiveSession | null;
  recentFocusSessions?: RecentFocusSession[];
}

export interface MemoryContextClearResponse {
  ok: boolean;
  provider: 'local-json';
  tasks: MemoryTask[];
  recentActions: RecentAction[];
  notes: Note[];
  activeSession?: ActiveSession | null;
  recentFocusSessions?: RecentFocusSession[];
  removedTaskCount: number;
  removedActionCount: number;
  removedNoteCount: number;
  removedActiveSession?: boolean;
  removedRecentFocusSessionCount?: number;
  message: string;
}

export interface MemoryNoteCreateRequest {
  content: string;
}

export interface MemoryNotesReplaceRequest {
  notes: Note[];
}

export interface MemoryNotesResponse {
  ok: boolean;
  provider: 'local-json';
  notes: Note[];
  message: string;
}

export interface MemoryNoteDeleteResponse {
  ok: boolean;
  provider: 'local-json';
  deletedNoteId: string;
  message: string;
}

export interface MemoryNotesClearResponse {
  ok: boolean;
  provider: 'local-json';
  removedCount: number;
  notes: Note[];
  message: string;
}

export interface RecentActionCreateRequest {
  label: string;
  detail?: string;
}

export interface RecentActionsReplaceRequest {
  recentActions: RecentAction[];
}

export interface RecentActionsResponse {
  ok: boolean;
  provider: 'local-json';
  recentActions: RecentAction[];
  message: string;
}

export interface RecentActionDeleteResponse {
  ok: boolean;
  provider: 'local-json';
  deletedActionId: string;
  message: string;
}

export interface RecentActionsClearResponse {
  ok: boolean;
  provider: 'local-json';
  removedCount: number;
  recentActions: RecentAction[];
  message: string;
}

export interface CalendarEvent {
  id: string;
  title: string;
  dateKey: string;
  time: string;
  createdAt: string;
  source?: 'local' | 'google';
  googleEventId?: string;
  start?: string | null;
  end?: string | null;
  location?: string;
  description?: string;
  allDay?: boolean;
  calendarId?: string;
}

export type CalendarBackendView = 'today' | 'tomorrow' | 'week';

export interface CalendarBackendStatus {
  ok: boolean;
  provider: 'google';
  configured: boolean;
  connected: boolean;
  calendarId: string;
  writeEnabled?: boolean;
  scope?: string;
  message: string;
}

export interface CalendarAuthStartResponse {
  ok: boolean;
  authUrl: string;
  message: string;
}

export interface CalendarAuthResetResponse {
  ok: boolean;
  message: string;
}

export interface CalendarEventsResponse {
  ok: boolean;
  configured: boolean;
  connected: boolean;
  source: 'google';
  view: CalendarBackendView;
  events: CalendarEvent[];
  message: string;
}

export interface CalendarCreateEventRequest {
  title: string;
  day: 'today' | 'tomorrow';
  time: string;
  description?: string;
  location?: string;
}

export interface CalendarCreateEventResponse {
  ok: boolean;
  configured: boolean;
  connected: boolean;
  source: 'google';
  event: CalendarEvent | null;
  message: string;
}

export interface CalendarUpdateEventRequest {
  title?: string;
  day?: 'today' | 'tomorrow';
  time?: string;
  description?: string;
  location?: string;
}

export interface CalendarUpdateEventResponse {
  ok: boolean;
  configured: boolean;
  connected: boolean;
  source: 'google';
  event: CalendarEvent | null;
  message: string;
}

export interface CalendarDeleteEventResponse {
  ok: boolean;
  configured: boolean;
  connected: boolean;
  source: 'google';
  deletedEventId: string;
  message: string;
}

export interface SearchSourceItem {
  title: string;
  url: string;
  domain: string;
  usedFor?: string;
}

export interface SearchResultCard {
  title: string;
  detail: string;
}

export interface SearchResponse {
  ok: boolean;
  query: string;
  summary: string;
  recommendation?: string;
  steps?: string[];
  cards?: SearchResultCard[];
  sources: SearchSourceItem[];
  provider: string;
  message: string;
}

export type CommandIntentName = 'command' | 'chat';

export type CommandAction =
  | 'none'
  | 'open_panel'
  | 'close_panel'
  | 'go_home'
  | 'clear_chat'
  | 'end_chat'
  | 'save_note'
  | 'read_notes'
  | 'delete_last_note'
  | 'clear_notes'
  | 'prepare_search'
  | 'clear_search'
  | 'read_memory'
  | 'save_task'
  | 'mark_task_done'
  | 'add_calendar_event'
  | 'read_calendar'
  | 'delete_last_calendar_event'
  | 'edit_calendar_event'
  | 'clear_calendar'
  | 'voice_output_on'
  | 'voice_output_off'
  | 'voice_slower'
  | 'voice_faster'
  | 'voice_normal'
  | 'cancel';

export interface CommandIntentResponse {
  intent: CommandIntentName;
  action: CommandAction;
  confidence: number;
  frontendCommand: string;
  payload: Record<string, unknown>;
  reason?: string;
}
