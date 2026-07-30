import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

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

type ExactRouteObservation = {
  sourceTurnId: string;
  command: string;
  routeClass: string;
  category: string;
  requiresConfirmation: boolean;
  source: string;
  createdAt: string;
};

type ExactRouteObservationSummary = {
  observationCount: number;
  readCount: number;
  mutationCount: number;
  focusActionCount: number;
  uiCount: number;
  voiceCount: number;
  guideCount: number;
  conversationCount: number;
  unknownCount: number;
  confirmationRequiredCount: number;
  categoryCounts: Record<string, number>;
  routeClasses: Record<string, number>;
  commands: Record<string, number>;
  latestObservation: ExactRouteObservation | null;
  windowStart?: string;
};

type SuccessfulValidation = {
  kind: 'active_validation' | 'promotion_readiness' | string;
  plannerMode: string;
  validatedAt: string;
  sessionStartedAt: string;
  routeDecisions: number;
  responseGuardedAttempts: number;
  exactRouteObservations: number;
  routeHealthyRate: number;
  responseHealthyRate: number;
};

type PromotionReadiness = {
  status: 'ready' | 'collecting' | 'blocked' | string;
  ready: boolean;
  promotionTarget: string;
  automaticPromotion: boolean;
  recommendation: string;
  blockers: string[];
  missingEvidence: string[];
  stage?: 'active_validation' | 'promotion_readiness' | 'planner_setup' | string;
  panelTitle?: string;
  statusLabel?: string;
  statusMeta?: string;
  evidenceLabel?: string;
  automaticActionLabel?: string;
  lastSuccessfulValidation?: SuccessfulValidation | null;
  sampleRequirements: {
    routeDecisions: number;
    responseGuardedAttempts: number;
    exactRouteObservations: number;
    healthyRate: number;
  };
  currentSamples: {
    routeDecisions: number;
    responseGuardedAttempts: number;
    exactRouteObservations: number;
    routeHealthyRate: number;
    responseHealthyRate: number;
  };
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
  exactRouteObservation?: ExactRouteObservationSummary;
  promotionReadiness?: PromotionReadiness;
  currentSession?: {
    startedAt: string;
    responseSelection: GuardSelection<FocusResponseDecision>;
    routeSelection?: GuardSelection<FocusRouteDecision>;
    exactRouteObservation?: ExactRouteObservationSummary;
  };
};

type StatusCardProps = {
  title: string;
  value: ReactNode;
  meta: ReactNode;
  className?: string;
};

type DetailRowProps = {
  label: string;
  value: ReactNode;
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
  const normalized = value.trim().replace(/[_-]+/g, ' ');
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

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unknown time';
  return date.toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
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
  if (decision.outcome === 'takeover') return formatLabel(decision.responseSource);
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

function StatusCard({ title, value, meta, className = 'status-card' }: StatusCardProps) {
  return (
    <div className={className}>
      <div className="status-card-title">{title}</div>
      <div className="status-card-value">{value}</div>
      <div className="status-card-meta">{meta}</div>
    </div>
  );
}

function DetailRow({ label, value }: DetailRowProps) {
  return (
    <div className="status-detail-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
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
  const recordedExactRouteObservation = status?.exactRouteObservation ?? null;
  const sessionExactRouteObservation =
    status?.currentSession?.exactRouteObservation ?? recordedExactRouteObservation;
  const responseLatest = sessionResponseSelection?.latestDecision ?? null;
  const routeLatest = sessionRouteSelection?.latestDecision ?? null;
  const exactRouteLatest = sessionExactRouteObservation?.latestObservation ?? null;
  const validation = status?.promotionReadiness ?? null;
  const lastSuccessfulValidation = validation?.lastSuccessfulValidation ?? null;
  const isActiveMode = status?.mode.trim().toLowerCase() === 'active';

  const validationTitle =
    validation?.panelTitle ||
    (isActiveMode ? 'Active Planner Validation' : 'Planner Promotion Readiness');
  const validationStatusLabel =
    validation?.statusLabel || formatLabel(validation?.status || 'unknown');
  const validationStatusMeta =
    validation?.statusMeta || (isActiveMode ? 'Current-session guarded health' : 'Manual review only');
  const evidenceLabel =
    validation?.evidenceLabel ||
    (isActiveMode ? 'Health evidence still needed' : 'Evidence still needed');
  const automaticActionLabel =
    validation?.automaticActionLabel ||
    (isActiveMode ? 'Automatic mode changes' : 'Automatic promotion');

  const validationClass = validation?.status === 'ready'
    ? 'status-card status-card-good'
    : validation?.status === 'blocked'
      ? 'status-card status-card-warn'
      : 'status-card';

  const exactLocalActionCount = sessionExactRouteObservation
    ? Math.max(
        0,
        sessionExactRouteObservation.observationCount -
          sessionExactRouteObservation.readCount,
      )
    : 0;

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
              <StatusCard
                className={responseHealthClass}
                title="Healthy This Session"
                value={formatPercentForCount(
                  sessionResponseSelection.healthyDecisionRate,
                  sessionResponseSelection.decisionCount,
                )}
                meta={`${sessionResponseSelection.healthyDecisionCount} of ${sessionResponseSelection.decisionCount} decisions`}
              />
              <StatusCard
                className="status-card status-card-good"
                title="Guarded Takeover"
                value={formatPercentForCount(
                  sessionResponseSelection.guardedTakeoverRate,
                  sessionResponseSelection.guardedAttemptCount,
                )}
                meta={`${sessionResponseSelection.takeoverCount} of ${sessionResponseSelection.guardedAttemptCount} attempts`}
              />
              <StatusCard
                title="Expected Fallbacks"
                value={sessionResponseSelection.expectedFallbackCount}
                meta="Current backend session"
              />
              <StatusCard
                className={healthCardClass(
                  sessionResponseSelection.systemFailureCount,
                  sessionResponseSelection.unknownFallbackCount,
                )}
                title="Session Failures"
                value={sessionResponseSelection.systemFailureCount}
                meta={`All-time: ${recordedResponseSelection.systemFailureCount} system · ${recordedResponseSelection.unknownFallbackCount} unknown`}
              />
            </div>
            <div className="status-detail-list">
              <DetailRow
                label="Session started"
                value={sessionStartedAt ? formatDecisionTime(sessionStartedAt) : 'Legacy metrics'}
              />
              <DetailRow label="Planner mode" value={formatLabel(status?.mode || 'unknown')} />
              <DetailRow
                label="Visible response mode"
                value={formatLabel(status?.responseMode || 'unknown')}
              />
              <DetailRow
                label="Session safety fallbacks"
                value={sessionResponseSelection.safetyFallbackCount}
              />
              <DetailRow label="Latest session decision" value={formatDecision(responseLatest)} />
              <DetailRow
                label="Session decision detail"
                value={responseDecisionDetail(responseLatest)}
              />
              <DetailRow
                label="Session decision time"
                value={responseLatest ? formatDecisionTime(responseLatest.createdAt) : '—'}
              />
              <DetailRow
                label="Recorded response history"
                value={`${recordedResponseSelection.decisionCount} decisions · ${recordedResponseSelection.systemFailureCount} system failures`}
              />
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
              <StatusCard
                className={routeHealthClass}
                title="Healthy This Session"
                value={formatPercentForCount(
                  sessionRouteSelection.healthyDecisionRate,
                  sessionRouteSelection.decisionCount,
                )}
                meta={`${sessionRouteSelection.healthyDecisionCount} of ${sessionRouteSelection.decisionCount} decisions`}
              />
              <StatusCard
                className="status-card status-card-good"
                title="Guarded Takeover"
                value={formatPercentForCount(
                  sessionRouteSelection.guardedTakeoverRate,
                  sessionRouteSelection.guardedAttemptCount,
                )}
                meta={`${sessionRouteSelection.takeoverCount} of ${sessionRouteSelection.guardedAttemptCount} attempts`}
              />
              <StatusCard
                title="Expected Fallbacks"
                value={sessionRouteSelection.expectedFallbackCount}
                meta="Protected legacy mutations"
              />
              <StatusCard
                className={healthCardClass(
                  sessionRouteSelection.systemFailureCount,
                  sessionRouteSelection.unknownFallbackCount,
                )}
                title="Session Safety Blocks"
                value={sessionRouteSelection.safetyFallbackCount}
                meta={`All-time: ${recordedRouteSelection?.safetyFallbackCount ?? 0} safety · ${recordedRouteSelection?.systemFailureCount ?? 0} system`}
              />
            </div>
            <div className="status-detail-list">
              <DetailRow
                label="Route mode"
                value={formatLabel(status?.routeMode || 'shadow')}
              />
              <DetailRow label="Latest session route" value={formatDecision(routeLatest)} />
              <DetailRow label="Route detail" value={routeAgreementDetail(routeLatest)} />
              <DetailRow
                label="Session route time"
                value={routeLatest ? formatDecisionTime(routeLatest.createdAt) : '—'}
              />
              <DetailRow
                label="Recorded route history"
                value={`${recordedRouteSelection?.decisionCount ?? 0} decisions · ${recordedRouteSelection?.systemFailureCount ?? 0} system failures`}
              />
              <DetailRow label="Focus events" value={status?.eventCount ?? '—'} />
              {error && <DetailRow label="Refresh" value={`Showing last data · ${error}`} />}
            </div>
          </>
        ) : (
          <p className="panel-section-text">
            Route-selection metrics are unavailable. Restart the backend after enabling
            Phase 19 guarded routing.
          </p>
        )}
      </div>

      <div className="panel-section status-detail-section" aria-live="polite">
        <div className="panel-section-title">{validationTitle}</div>
        {validation ? (
          <>
            <div className="status-grid">
              <StatusCard
                className={validationClass}
                title={isActiveMode ? 'Current Health' : 'Current Status'}
                value={validationStatusLabel}
                meta={validationStatusMeta}
              />
              <StatusCard
                title="Guarded Routes"
                value={`${validation.currentSamples.routeDecisions} / ${validation.sampleRequirements.routeDecisions}`}
                meta="Current-session decisions"
              />
              <StatusCard
                title="Guarded Responses"
                value={`${validation.currentSamples.responseGuardedAttempts} / ${validation.sampleRequirements.responseGuardedAttempts}`}
                meta="Eligible takeover attempts"
              />
              <StatusCard
                title="Exact Routes"
                value={`${validation.currentSamples.exactRouteObservations} / ${validation.sampleRequirements.exactRouteObservations}`}
                meta="Frontend route observations"
              />
            </div>
            <div className="status-detail-list">
              <DetailRow label="Recommendation" value={validation.recommendation} />
              <DetailRow
                label="Blocking evidence"
                value={validation.blockers.length ? validation.blockers.join(' ') : 'None'}
              />
              <DetailRow
                label={evidenceLabel}
                value={
                  validation.missingEvidence.length
                    ? validation.missingEvidence.join(' ')
                    : 'Thresholds satisfied'
                }
              />
              <DetailRow
                label="Required healthy rate"
                value={formatPercent(validation.sampleRequirements.healthyRate)}
              />
              <DetailRow label={automaticActionLabel} value="Disabled" />
              <DetailRow
                label="Last successful validation"
                value={
                  lastSuccessfulValidation
                    ? formatDateTime(lastSuccessfulValidation.validatedAt)
                    : 'No successful validation recorded yet'
                }
              />
              {lastSuccessfulValidation && (
                <>
                  <DetailRow
                    label="Validated mode"
                    value={formatLabel(lastSuccessfulValidation.plannerMode)}
                  />
                  <DetailRow
                    label="Validated evidence"
                    value={`${lastSuccessfulValidation.routeDecisions} guarded routes · ${lastSuccessfulValidation.responseGuardedAttempts} guarded responses · ${lastSuccessfulValidation.exactRouteObservations} exact routes`}
                  />
                  <DetailRow
                    label="Validated health"
                    value={`${formatPercent(lastSuccessfulValidation.routeHealthyRate)} routing · ${formatPercent(lastSuccessfulValidation.responseHealthyRate)} responses`}
                  />
                </>
              )}
            </div>
          </>
        ) : (
          <p className="panel-section-text">
            Validation metrics are unavailable. Restart the backend after installing the
            readiness evaluator.
          </p>
        )}
      </div>

      <div className="panel-section status-detail-section" aria-live="polite">
        <div className="panel-section-title">Exact Local Routing</div>
        {sessionExactRouteObservation ? (
          <>
            <div className="status-grid">
              <StatusCard
                title="Observed This Session"
                value={sessionExactRouteObservation.observationCount}
                meta="Frontend exact-command routes"
              />
              <StatusCard
                className="status-card status-card-good"
                title="Read Routes"
                value={sessionExactRouteObservation.readCount}
                meta="Deterministic local readouts"
              />
              <StatusCard
                title="Local Actions"
                value={exactLocalActionCount}
                meta="UI, voice, writes, and Focus actions"
              />
              <StatusCard
                className={
                  sessionExactRouteObservation.unknownCount === 0
                    ? 'status-card status-card-good'
                    : 'status-card status-card-warn'
                }
                title="Unclassified"
                value={sessionExactRouteObservation.unknownCount}
                meta={`${sessionExactRouteObservation.confirmationRequiredCount} confirmation gates`}
              />
            </div>
            <div className="status-detail-list">
              <DetailRow
                label="Latest exact command"
                value={exactRouteLatest ? formatLabel(exactRouteLatest.command) : 'No exact routes yet'}
              />
              <DetailRow
                label="Exact route class"
                value={exactRouteLatest ? formatLabel(exactRouteLatest.routeClass) : '—'}
              />
              <DetailRow
                label="Exact route category"
                value={exactRouteLatest ? formatLabel(exactRouteLatest.category) : '—'}
              />
              <DetailRow
                label="Confirmation gate"
                value={
                  exactRouteLatest
                    ? exactRouteLatest.requiresConfirmation
                      ? 'Required'
                      : 'Not required'
                    : '—'
                }
              />
              <DetailRow
                label="Session exact-route time"
                value={exactRouteLatest ? formatDecisionTime(exactRouteLatest.createdAt) : '—'}
              />
              <DetailRow
                label="Session route mix"
                value={`${sessionExactRouteObservation.mutationCount} mutations · ${sessionExactRouteObservation.focusActionCount} Focus actions · ${sessionExactRouteObservation.uiCount} UI`}
              />
              <DetailRow
                label="Recorded exact-route history"
                value={`${recordedExactRouteObservation?.observationCount ?? 0} observations`}
              />
            </div>
          </>
        ) : (
          <p className="panel-section-text">
            Exact local-route metrics are unavailable. Restart the backend after installing
            the route-observation endpoint.
          </p>
        )}
      </div>
    </>
  );
}
