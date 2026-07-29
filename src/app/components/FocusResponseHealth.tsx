import { useEffect, useMemo, useState } from 'react';

import { QMEET_API_BASE_URL } from '../api';

type FocusResponseDecision = {
  sourceTurnId: string;
  focusId: string;
  outcome: 'takeover' | 'fallback' | string;
  reason: string;
  category: 'takeover' | 'expected' | 'safety' | 'system_failure' | 'unknown' | string;
  healthy: boolean;
  details: string[];
  candidateEligible: boolean | null;
  responseSource: string;
  createdAt: string;
};

type FocusResponseSelection = {
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
  latestDecision: FocusResponseDecision | null;
};

type FocusStatusResponse = {
  ok: boolean;
  mode: string;
  responseMode: string;
  plannerEnabled: boolean;
  model: string;
  eventCount: number;
  responseSelection: FocusResponseSelection;
};

const REFRESH_INTERVAL_MS = 10_000;

function formatPercent(value: number): string {
  if (!Number.isFinite(value)) return '—';
  const percentage = Math.max(0, Math.min(1, value)) * 100;
  return `${percentage >= 99.95 ? percentage.toFixed(0) : percentage.toFixed(1)}%`;
}

function formatLabel(value: string): string {
  const normalized = value.trim().replace(/_/g, ' ');
  if (!normalized) return 'None';
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function formatDecision(decision: FocusResponseDecision | null): string {
  if (!decision) return 'No guarded decisions yet';
  if (decision.outcome === 'takeover') return 'Canonical takeover';
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
            : 'Focus response health is unavailable.',
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

  const selection = status?.responseSelection ?? null;
  const latestDecision = selection?.latestDecision ?? null;
  const healthCardClass = useMemo(() => {
    if (!selection) return 'status-card';
    return selection.systemFailureCount === 0 && selection.unknownFallbackCount === 0
      ? 'status-card status-card-good'
      : 'status-card status-card-warn';
  }, [selection]);

  if (loading && !selection) {
    return (
      <div className="panel-section status-detail-section" aria-live="polite">
        <div className="panel-section-title">Focus Response Health</div>
        <p className="panel-section-text">Loading guarded-response metrics…</p>
      </div>
    );
  }

  if (!selection) {
    return (
      <div className="panel-section status-detail-section" aria-live="polite">
        <div className="panel-section-title">Focus Response Health</div>
        <p className="panel-section-text">
          {error || 'No guarded-response metrics are available yet.'}
        </p>
      </div>
    );
  }

  return (
    <div className="panel-section status-detail-section" aria-live="polite">
      <div className="panel-section-title">Focus Response Health</div>
      <div className="status-grid">
        <div className={healthCardClass}>
          <div className="status-card-title">Healthy Decisions</div>
          <div className="status-card-value">
            {formatPercent(selection.healthyDecisionRate)}
          </div>
          <div className="status-card-meta">
            {selection.healthyDecisionCount} of {selection.decisionCount} decisions
          </div>
        </div>
        <div className="status-card status-card-good">
          <div className="status-card-title">Guarded Takeover</div>
          <div className="status-card-value">
            {formatPercent(selection.guardedTakeoverRate)}
          </div>
          <div className="status-card-meta">
            {selection.takeoverCount} of {selection.guardedAttemptCount} attempts
          </div>
        </div>
        <div className="status-card">
          <div className="status-card-title">Expected Fallbacks</div>
          <div className="status-card-value">{selection.expectedFallbackCount}</div>
          <div className="status-card-meta">Correct off-focus or tool routing</div>
        </div>
        <div
          className={`status-card ${
            selection.systemFailureCount === 0
              ? 'status-card-good'
              : 'status-card-warn'
          }`}
        >
          <div className="status-card-title">System Failures</div>
          <div className="status-card-value">{selection.systemFailureCount}</div>
          <div className="status-card-meta">
            {selection.unknownFallbackCount} unknown fallback
            {selection.unknownFallbackCount === 1 ? '' : 's'}
          </div>
        </div>
      </div>
      <div className="status-detail-list">
        <div className="status-detail-row">
          <span>Planner mode</span>
          <strong>{formatLabel(status?.mode || 'unknown')}</strong>
        </div>
        <div className="status-detail-row">
          <span>Visible response mode</span>
          <strong>{formatLabel(status?.responseMode || 'unknown')}</strong>
        </div>
        <div className="status-detail-row">
          <span>Safety fallbacks</span>
          <strong>{selection.safetyFallbackCount}</strong>
        </div>
        <div className="status-detail-row">
          <span>Latest decision</span>
          <strong>{formatDecision(latestDecision)}</strong>
        </div>
        <div className="status-detail-row">
          <span>Latest decision time</span>
          <strong>
            {latestDecision ? formatDecisionTime(latestDecision.createdAt) : '—'}
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
    </div>
  );
}
