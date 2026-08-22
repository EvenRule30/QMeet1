const CALENDAR_PANEL_DATE_HINT_KEY = 'qmeet-calendar-panel-date-hint';
const ISO_DATE_KEY_RE = /^\d{4}-\d{2}-\d{2}$/;

function isValidDateKey(value: string): boolean {
  if (!ISO_DATE_KEY_RE.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
}

export function rememberCalendarPanelDateHint(dateKey: string): void {
  if (typeof window === 'undefined') return;
  const normalized = dateKey.trim();
  if (!isValidDateKey(normalized)) return;
  try {
    window.sessionStorage.setItem(CALENDAR_PANEL_DATE_HINT_KEY, normalized);
  } catch {
    // Session storage can be unavailable in restricted browser modes.
  }
}

export function consumeCalendarPanelDateHint(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const stored = window.sessionStorage.getItem(CALENDAR_PANEL_DATE_HINT_KEY);
    window.sessionStorage.removeItem(CALENDAR_PANEL_DATE_HINT_KEY);
    if (!stored) return null;
    const normalized = stored.trim();
    return isValidDateKey(normalized) ? normalized : null;
  } catch {
    return null;
  }
}
