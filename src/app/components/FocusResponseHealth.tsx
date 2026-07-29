import { useEffect, useMemo, useState } from 'react';

import { QMEET_API_BASE_URL } from '../api';

type GuardDecision = {
  sourceTurnId: string;
  focusId: string;
  outcome: 'takeover' | 'fallback' | string;
  reason: string;
  category: 'takeover' | 'expected' | 'safety' | 'system_failure' | 'unknown' | string;
  healthy: boolean;
  details: string[];
  responseSource: string;
  createdAt: string;
};

type FocusResponseDecision = GuardDecision & {
  candidateEligible: boolean | null;
};

type FocusRouteDecision = GuardDecision & {
  routeClass: string;
  focusRouteClass: string;
  legacyRouteClass: string;
  focusConfidence: number;
  minimumConfidence: number;
  legacyIntent: string;
  legacyAction: string;
};

type GuardSelection<TDecision extends GuardDecision> = {
  decisionCount: number;
  takeoverCount: number;
  fallbackCount: number;
  successRate: number;
  takeoverRate: number;
  guardedAttemptCount: number;
  guardedTakeoverRate: number;
  healthyDecisionCount: number;
  healthyDecisionRate: number;
  expectedFallbackCount: number;
  safetyFallbackCount: number;
  systemFailureCount: number;
  unknownFallbackCount: number;
  fallbackReasons: Record<string, number>;
  fallbackCategoryCounts: {
    expected: number;
    safety: number;
    systemFailure: number;
    unknown: number;
  };
  fallbackReasonsByCategory: {
    expected: Record<string, number>;
    safety: Record<string, number>;
    systemFailure: Record<string, number>;
    unknown: Record<string, number>;
  };
  latestDecision: TDecision | null;
  windowStart?: string;
};

type FocusStatusResponse = {
  ok: boolean;
  mode: string;
  responseMode: string;
  routeMode?: string;
  plannerEnabled: boolean;
  model: string;
  eventCount: number;
  responseSelection: GuardSelection<FocusResponseDecision>;
  routeSelection?: GuardSelection<FocusRouteDecision>;
  currentSession?: {
    startedAt: string;
    responseSelection: GuardSelection<FocusResponseDecision>;
    routeSelection?: GuardSelection<FocusRouteDecision>;
  };
};

const REFRESH_INTERVAL_MS = 10_000;

function formatPercent(value: number): string {
  if (!Number.isFinite(value)) return '—';
  const percentage = Math.max(0, Math.min(1, value)) * 100;
  return `${percentage >= 99.95 ? percentage.toFixed(0) : percentage.toFixed(1)}%`;
}

function formatPercentForCount(value: number, count: number): string {
  return count > 0 ? formatPercent(value) : '—';
}

function formatLabel(value: string): string {
  const normalized = value.trim().replace(/_/g, ' ');
  if (!normalized) return 'None';
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function formatDecision(decision: GuardDecision | null): string {
  if (!decision) return 'No guarded decisions yet';
  if (decision.outcome === 'takeover') return 'Guarded takeover';
  return `${formatLabel(decision.category)} fallback · ${formatLabel(decision.reason)}`;
}

function formatDecisionTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unknown time';
  return date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function healthCardClass(
  systemFailureCount: number,
  unknownFallbackCount: number,
): string {
  return systemFailureCount === 0 && unknownFallbackCount === 0
    ? 'status-card status-card-good'
    : 'status-card status-card-warn';
}

function responseDecisionDetail(decision: FocusResponseDecision | null): string {
  if (!decision) return '—';
  if (decision.outcome === 'takeover') {
    return formatLabel(decision.responseSource);
  }
  if (decision.details.length > 0) {
    return decision.details.map(formatLabel).join(', ');
  }
  if (decision.reason === 'missing_tool_request') {
    return 'No matching tool request was recorded for that turn';
  }
  if (decision.reason === 'tool_not_attached_to_focus') {
    return 'Tool result remained outside the active focus';
  }
  return 'No additional details';
}

function routeAgreementDetail(decision: FocusRouteDecision | null): string {
  if (!decision) return '—';

  if (
    decision.reason === 'confirmation_gated_legacy_route' &&
    decision.details.length > 0
  ) {
    return `Protected action: ${formatLabel(decision.details[0])}`;
  }

  const focusRoute = formatLabel(decision.focusRouteClass || 'none');
  const legacyRoute = formatLabel(decision.legacyRouteClass || 'none');
  if (decision.outcome === 'takeover') {
    return decision.routeClass
      ? `${formatLabel(decision.routeClass)} agreed`
      : `${focusRoute} agreed`;
  }
  if (decision.reason === 'route_disagreement') {
    return `Focus: ${focusRoute} · Legacy: ${legacyRoute}`;
  }
  if (decision.legacyAction) {
    return `Legacy action: ${formatLabel(decision.legacyAction)}`;
  }
  return decision.details.length > 0
    ? decision.details.map(formatLabel).join(', ')
    : 'No route details recorded';
}

export function FocusResponseHealth() {
  const [status, setStatus] = useState<FocusStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    let activeController: AbortController | null = null;

    const refresh = async () => {
      activeController?.abort();
      const controller = new AbortController();
      activeController = controller;

      try {
        const response = await fetch(`${QMEET_API_BASE_URL}/api/focus/status`, {
          headers: { Accept: 'application/json' },
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Focus status returned ${response.status}.`);
        }

        const nextStatus = (await response.json()) as FocusStatusResponse;
        if (!mounted) return;
        setStatus(nextStatus);
        setError('');
      } catch (caughtError) {
        if (!mounted || controller.signal.aborted) return;
        setError(
          caughtError instanceof Error
            ? caughtError.message
            : 'Focus guard health is unavailable.',
        );
      } finally {
        if (mounted) setLoading(false);
      }
    };

    void refresh();
    const intervalId = window.setInterval(() => {
      void refresh();
    }, REFRESH_INTERVAL_MS);

    return () => {
      mounted = false;
      activeController?.abort();
      window.clearInterval(intervalId);
    };
  }, []);

  const recordedResponseSelection = status?.responseSelection ?? null;
  const recordedRouteSelection = status?.routeSelection ?? null;
  const sessionResponseSelection =
    status?.currentSession?.responseSelection ?? recordedResponseSelection;
  const sessionRouteSelection =
    status?.currentSession?.routeSelection ?? recordedRouteSelection;
  const sessionStartedAt = status?.currentSession?.startedAt ?? '';
  const responseLatest = sessionResponseSelection?.latestDecision ?? null;
  const routeLatest = sessionRouteSelection?.latestDecision ?? null;

  const responseHealthClass = useMemo(() => {
    if (!sessionResponseSelection) return 'status-card';
    return healthCardClass(
      sessionResponseSelection.systemFailureCount,
      sessionResponseSelection.unknownFallbackCount,
    );
  }, [sessionResponseSelection]);

  const routeHealthClass = useMemo(() => {
    if (!sessionRouteSelection) return 'status-card';
    return healthCardClass(
      sessionRouteSelection.systemFailureCount,
      sessionRouteSelection.unknownFallbackCount,
    );
  }, [sessionRouteSelection]);

  if (loading && !recordedResponseSelection) {
    return (
      <div className="panel-section status-detail-section" aria-live="polite">
        <div className="panel-section-title">Focus Guard Health</div>
        <p className="panel-section-text">Loading guarded-response and routing metrics…</p>
      </div>
    );
  }

  if (!recordedResponseSelection) {
    return (
      <div className="panel-section status-detail-section" aria-live="polite">
        <div className="panel-section-title">Focus Guard Health</div>
        <p className="panel-section-text">
          {error || 'No Focus guard metrics are available yet.'}
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="panel-section status-detail-section" aria-live="polite">
        <div className="panel-section-title">Focus Response Health</div>
        {sessionResponseSelection ? (
          <>
            <div className="status-grid">
              <div className={responseHealthClass}>
                <div className="status-card-title">Healthy This Session</div>
                <div className="status-card-value">
                  {formatPercentForCount(
                    sessionResponseSelection.healthyDecisionRate,
                    sessionResponseSelection.decisionCount,
                  )}
                </div>
                <div className="status-card-meta">
                  {sessionResponseSelection.healthyDecisionCount} of{' '}
                  {sessionResponseSelection.decisionCount} decisions
                </div>
              </div>
              <div className="status-card status-card-good">
                <div className="status-card-title">Guarded Takeover</div>
                <div className="status-card-value">
                  {formatPercentForCount(
                    sessionResponseSelection.guardedTakeoverRate,
                    sessionResponseSelection.guardedAttemptCount,
                  )}
                </div>
                <div className="status-card-meta">
                  {sessionResponseSelection.takeoverCount} of{' '}
                  {sessionResponseSelection.guardedAttemptCount} attempts
                </div>
              </div>
              <div className="status-card">
                <div className="status-card-title">Expected Fallbacks</div>
                <div className="status-card-value">
                  {sessionResponseSelection.expectedFallbackCount}
                </div>
                <div className="status-card-meta">Current backend session</div>
              </div>
              <div
                className={`status-card ${
                  sessionResponseSelection.systemFailureCount === 0 &&
                  sessionResponseSelection.unknownFallbackCount === 0
                    ? 'status-card-good'
                    : 'status-card-warn'
                }`}
              >
                <div className="status-card-title">Session Failures</div>
                <div className="status-card-value">
                  {sessionResponseSelection.systemFailureCount}
                </div>
                <div className="status-card-meta">
                  All-time: {recordedResponseSelection.systemFailureCount} system ·{' '}
                  {recordedResponseSelection.unknownFallbackCount} unknown
                </div>
              </div>
            </div>
            <div className="status-detail-list">
              <div className="status-detail-row">
                <span>Session started</span>
                <strong>
                  {sessionStartedAt ? formatDecisionTime(sessionStartedAt) : 'Legacy metrics'}
                </strong>
              </div>
              <div className="status-detail-row">
                <span>Planner mode</span>
                <strong>{formatLabel(status?.mode || 'unknown')}</strong>
              </div>
              <div className="status-detail-row">
                <span>Visible response mode</span>
                <strong>{formatLabel(status?.responseMode || 'unknown')}</strong>
              </div>
              <div className="status-detail-row">
                <span>Session safety fallbacks</span>
                <strong>{sessionResponseSelection.safetyFallbackCount}</strong>
              </div>
              <div className="status-detail-row">
                <span>Latest session decision</span>
                <strong>{formatDecision(responseLatest)}</strong>
              </div>
              <div className="status-detail-row">
                <span>Session decision detail</span>
                <strong>{responseDecisionDetail(responseLatest)}</strong>
              </div>
              <div className="status-detail-row">
                <span>Session decision time</span>
                <strong>
                  {responseLatest ? formatDecisionTime(responseLatest.createdAt) : '—'}
                </strong>
              </div>
              <div className="status-detail-row">
                <span>Recorded response history</span>
                <strong>
                  {recordedResponseSelection.decisionCount} decisions ·{' '}
                  {recordedResponseSelection.systemFailureCount} system failures
                </strong>
              </div>
            </div>
          </>
        ) : (
          <p className="panel-section-text">No response-session metrics are available.</p>
        )}
      </div>

      <div className="panel-section status-detail-section" aria-live="polite">
        <div className="panel-section-title">Planner Routing Health</div>
        {sessionRouteSelection ? (
          <>
            <div className="status-grid">
              <div className={routeHealthClass}>
                <div className="status-card-title">Healthy This Session</div>
                <div className="status-card-value">
                  {formatPercentForCount(
                    sessionRouteSelection.healthyDecisionRate,
                    sessionRouteSelection.decisionCount,
                  )}
                </div>
                <div className="status-card-meta">
                  {sessionRouteSelection.healthyDecisionCount} of{' '}
                  {sessionRouteSelection.decisionCount} decisions
                </div>
              </div>
              <div className="status-card status-card-good">
                <div className="status-card-title">Guarded Takeover</div>
                <div className="status-card-value">
                  {formatPercentForCount(
                    sessionRouteSelection.guardedTakeoverRate,
                    sessionRouteSelection.guardedAttemptCount,
                  )}
                </div>
                <div className="status-card-meta">
                  {sessionRouteSelection.takeoverCount} of{' '}
                  {sessionRouteSelection.guardedAttemptCount} attempts
                </div>
              </div>
              <div className="status-card">
                <div className="status-card-title">Expected Fallbacks</div>
                <div className="status-card-value">
                  {sessionRouteSelection.expectedFallbackCount}
                </div>
                <div className="status-card-meta">Protected legacy mutations</div>
              </div>
              <div
                className={`status-card ${
                  sessionRouteSelection.systemFailureCount === 0 &&
                  sessionRouteSelection.unknownFallbackCount === 0
                    ? 'status-card-good'
                    : 'status-card-warn'
                }`}
              >
                <div className="status-card-title">Session Safety Blocks</div>
                <div className="status-card-value">
                  {sessionRouteSelection.safetyFallbackCount}
                </div>
                <div className="status-card-meta">
                  All-time: {recordedRouteSelection?.safetyFallbackCount ?? 0} safety ·{' '}
                  {recordedRouteSelection?.systemFailureCount ?? 0} system
                </div>
              </div>
            </div>
            <div className="status-detail-list">
              <div className="status-detail-row">
                <span>Route mode</span>
                <strong>{formatLabel(status?.routeMode || 'shadow')}</strong>
              </div>
              <div className="status-detail-row">
                <span>Latest session route</span>
                <strong>{formatDecision(routeLatest)}</strong>
              </div>
              <div className="status-detail-row">
                <span>Route detail</span>
                <strong>{routeAgreementDetail(routeLatest)}</strong>
              </div>
              <div className="status-detail-row">
                <span>Session route time</span>
                <strong>
                  {routeLatest ? formatDecisionTime(routeLatest.createdAt) : '—'}
                </strong>
              </div>
              <div className="status-detail-row">
                <span>Recorded route history</span>
                <strong>
                  {recordedRouteSelection?.decisionCount ?? 0} decisions ·{' '}
                  {recordedRouteSelection?.systemFailureCount ?? 0} system failures
                </strong>
              </div>
              <div className="status-detail-row">
                <span>Focus events</span>
                <strong>{status?.eventCount ?? '—'}</strong>
              </div>
              {error && (
                <div className="status-detail-row">
                  <span>Refresh</span>
                  <strong>Showing last data · {error}</strong>
                </div>
              )}
            </div>
          </>
        ) : (
          <p className="panel-section-text">
            Route-selection metrics are unavailable. Restart the backend after enabling
            Phase 19 guarded routing.
          </p>
        )}
      </div>
    </>
  );

}
