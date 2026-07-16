import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import { analyzeVisualSnapshot, createVisualObservation } from '../api';
import type { ActiveSession, VisualContext } from '../types';

export type QMeetCameraCommandAction = 'open' | 'close' | 'snapshot' | 'analyze';

export const QMEET_CAMERA_COMMAND_EVENT = 'qmeet-camera-command';

const ACTIVE_SESSION_SESSION_STORAGE_KEY = 'qmeet-active-session-live';
const ACTIVE_SESSION_STORAGE_KEY = 'qmeet-active-session';
const VISUAL_CONTEXT_STORAGE_KEY = 'qmeet-visual-context';
const VISUAL_CONTEXT_STATE_EVENT = 'qmeet-visual-context-state';

type CameraStatus = 'closed' | 'opening' | 'ready' | 'captured' | 'analyzing' | 'error';

type CameraCommandDetail = {
  action?: QMeetCameraCommandAction;
  source?: string;
};

const overlayStyle: CSSProperties = {
  position: 'fixed',
  inset: 0,
  zIndex: 1200,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: 10,
  background: 'rgba(2, 8, 18, 0.76)',
  backdropFilter: 'blur(18px)',
};

const panelStyle: CSSProperties = {
  width: 'min(880px, 96vw)',
  maxHeight: 'calc(100vh - 20px)',
  display: 'flex',
  flexDirection: 'column',
  border: '1px solid rgba(124, 219, 255, 0.32)',
  borderRadius: 22,
  background: 'linear-gradient(180deg, rgba(8, 18, 36, 0.96), rgba(5, 10, 22, 0.96))',
  color: '#e9f7ff',
  boxShadow: '0 24px 100px rgba(0, 0, 0, 0.52), 0 0 48px rgba(47, 213, 255, 0.12)',
  overflow: 'hidden',
};

const headerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'space-between',
  gap: 14,
  padding: '14px 18px 10px',
  borderBottom: '1px solid rgba(124, 219, 255, 0.16)',
  flex: '0 0 auto',
};

const titleStyle: CSSProperties = {
  margin: 0,
  fontSize: 16,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
};

const subtitleStyle: CSSProperties = {
  margin: '4px 0 0',
  color: 'rgba(233, 247, 255, 0.68)',
  fontSize: 12,
  lineHeight: 1.35,
};

const bodyStyle: CSSProperties = {
  padding: 12,
  flex: '1 1 auto',
  minHeight: 0,
  overflowY: 'auto',
};

const previewWrapStyle: CSSProperties = {
  position: 'relative',
  display: 'grid',
  placeItems: 'center',
  minHeight: 220,
  maxHeight: 'min(330px, 50vh)',
  borderRadius: 18,
  overflow: 'hidden',
  background: 'radial-gradient(circle at center, rgba(30, 85, 120, 0.24), rgba(2, 8, 18, 0.96))',
  border: '1px solid rgba(124, 219, 255, 0.18)',
};

const mediaStyle: CSSProperties = {
  width: '100%',
  height: 'min(330px, 50vh)',
  objectFit: 'contain',
  background: '#020812',
};

const footerStyle: CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 10,
  padding: '10px 18px 14px',
  borderTop: '1px solid rgba(124, 219, 255, 0.14)',
  flex: '0 0 auto',
};

const buttonRowStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'flex-end',
  gap: 8,
  flexWrap: 'wrap',
};

const buttonStyle: CSSProperties = {
  border: '1px solid rgba(124, 219, 255, 0.32)',
  borderRadius: 999,
  background: 'rgba(124, 219, 255, 0.10)',
  color: '#e9f7ff',
  padding: '8px 13px',
  fontSize: 12,
  fontWeight: 700,
  letterSpacing: '0.03em',
  cursor: 'pointer',
};

const primaryButtonStyle: CSSProperties = {
  ...buttonStyle,
  background: 'linear-gradient(135deg, rgba(72, 216, 255, 0.92), rgba(125, 118, 255, 0.88))',
  color: '#02101d',
  border: 'none',
};

const disabledButtonStyle: CSSProperties = {
  ...buttonStyle,
  opacity: 0.45,
  cursor: 'not-allowed',
};

const snapshotActionsStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 8,
  flexWrap: 'wrap',
  marginTop: 8,
  padding: '8px 10px',
  borderRadius: 14,
  background: 'rgba(8, 22, 42, 0.72)',
  border: '1px solid rgba(124, 219, 255, 0.16)',
};

const snapshotLabelStyle: CSSProperties = {
  color: 'rgba(233, 247, 255, 0.72)',
  fontSize: 12,
  lineHeight: 1.35,
};

const launcherStyle: CSSProperties = {
  position: 'fixed',
  right: 18,
  bottom: 88,
  zIndex: 1000,
  width: 54,
  height: 54,
  borderRadius: 999,
  border: '1px solid rgba(124, 219, 255, 0.38)',
  background: 'rgba(6, 18, 34, 0.82)',
  color: '#e9f7ff',
  boxShadow: '0 10px 36px rgba(0, 0, 0, 0.35), 0 0 28px rgba(47, 213, 255, 0.12)',
  cursor: 'pointer',
  fontSize: 22,
};

const privacyStyle: CSSProperties = {
  marginTop: 8,
  border: '1px solid rgba(255, 214, 128, 0.24)',
  borderRadius: 14,
  background: 'rgba(255, 214, 128, 0.08)',
  color: 'rgba(255, 241, 205, 0.88)',
  padding: '8px 10px',
  fontSize: 11,
  lineHeight: 1.35,
};

const analysisStyle: CSSProperties = {
  marginTop: 8,
  border: '1px solid rgba(124, 219, 255, 0.22)',
  borderRadius: 14,
  background: 'rgba(124, 219, 255, 0.08)',
  padding: '10px 12px',
  color: 'rgba(233, 247, 255, 0.86)',
  fontSize: 12,
  lineHeight: 1.4,
};

function getCameraErrorMessage(error: unknown): string {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
    return 'Camera access is not available in this browser. Try Chrome/Chromium on localhost or HTTPS.';
  }

  if (error instanceof DOMException) {
    if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
      return 'Camera permission was denied. Allow camera access in the browser, then try again.';
    }

    if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
      return 'No camera device was found.';
    }

    if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
      return 'The camera is already in use or could not be started.';
    }
  }

  return error instanceof Error ? error.message : 'Camera could not be started.';
}

async function dataUrlToBlob(dataUrl: string): Promise<Blob> {
  const response = await fetch(dataUrl);
  return response.blob();
}

function readActiveSessionFromStorage(): ActiveSession | null {
  if (typeof window === 'undefined') return null;

  const candidates = [
    window.sessionStorage.getItem(ACTIVE_SESSION_SESSION_STORAGE_KEY),
    window.localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY),
  ];

  for (const rawValue of candidates) {
    if (!rawValue) continue;
    try {
      const parsed = JSON.parse(rawValue) as Partial<ActiveSession> | null;
      if (
        parsed &&
        typeof parsed.id === 'string' &&
        parsed.id.trim() &&
        typeof parsed.title === 'string' &&
        parsed.title.trim()
      ) {
        return parsed as ActiveSession;
      }
    } catch {
      // Ignore malformed browser fallback state.
    }
  }

  return null;
}

function publishVisualContext(visualContext: VisualContext): void {
  if (typeof window === 'undefined') return;

  try {
    window.localStorage.setItem(
      VISUAL_CONTEXT_STORAGE_KEY,
      JSON.stringify(visualContext),
    );
  } catch {
    // The backend save already succeeded; browser fallback is best effort.
  }

  window.dispatchEvent(
    new CustomEvent(VISUAL_CONTEXT_STATE_EVENT, {
      detail: { visualContext },
    }),
  );
}

export function CameraCaptureOverlay() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<CameraStatus>('closed');
  const [statusMessage, setStatusMessage] = useState('Camera preview is closed.');
  const [snapshotDataUrl, setSnapshotDataUrl] = useState<string | null>(null);
  const [analysisSummary, setAnalysisSummary] = useState<string | null>(null);
  const [analysisModel, setAnalysisModel] = useState<string | null>(null);
  const [analysisSaved, setAnalysisSaved] = useState(false);

  const clearAnalysis = useCallback(() => {
    setAnalysisSummary(null);
    setAnalysisModel(null);
    setAnalysisSaved(false);
  }, []);

  const clearCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const context = canvas.getContext('2d');
    if (context) {
      context.clearRect(0, 0, canvas.width, canvas.height);
    }

    canvas.width = 0;
    canvas.height = 0;
  }, []);

  const stopStream = useCallback(() => {
    const stream = streamRef.current;
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }, []);

  const closeCamera = useCallback(() => {
    stopStream();
    clearCanvas();
    clearAnalysis();
    setSnapshotDataUrl(null);
    setOpen(false);
    setStatus('closed');
    setStatusMessage('Camera preview is closed.');
  }, [clearAnalysis, clearCanvas, stopStream]);

  const startCamera = useCallback(async () => {
    setOpen(true);
    setStatus('opening');
    setStatusMessage('Requesting camera permission...');
    setSnapshotDataUrl(null);
    clearAnalysis();
    clearCanvas();

    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setStatus('error');
      setStatusMessage('Camera access is not available in this browser. Try Chrome/Chromium on localhost or HTTPS.');
      return;
    }

    try {
      stopStream();
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });

      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => undefined);
      }

      setStatus('ready');
      setStatusMessage('Camera preview is live. Snapshots stay in memory only and are not uploaded or saved until Analyze Snapshot is tapped.');
    } catch (error) {
      stopStream();
      setStatus('error');
      setStatusMessage(getCameraErrorMessage(error));
    }
  }, [clearAnalysis, clearCanvas, stopStream]);

  const captureSnapshot = useCallback(async () => {
    if (!open) {
      await startCamera();
      setStatusMessage('Camera opened. Press Snapshot once the preview is visible.');
      return;
    }

    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !video.videoWidth || !video.videoHeight) {
      setStatusMessage('Camera frame is not ready yet. Try Snapshot again in a moment.');
      return;
    }

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext('2d');
    if (!context) {
      setStatus('error');
      setStatusMessage('Could not create a canvas context for the snapshot.');
      return;
    }

    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    setSnapshotDataUrl(canvas.toDataURL('image/jpeg', 0.92));
    clearAnalysis();
    setStatus('captured');
    setStatusMessage('Snapshot captured in memory only. It has not been uploaded or saved.');
  }, [clearAnalysis, open, startCamera]);

  const analyzeSnapshot = useCallback(async () => {
    if (!snapshotDataUrl) {
      setStatusMessage('Take a snapshot before analyzing it.');
      return;
    }

    setStatus('analyzing');
    setStatusMessage('Sending this one snapshot to OpenAI through the backend for description...');

    try {
      const snapshot = await dataUrlToBlob(snapshotDataUrl);
      const analysis = await analyzeVisualSnapshot(snapshot);
      const summary = analysis.summary.trim();
      if (!summary) {
        throw new Error('OpenAI returned an empty visual description.');
      }

      const activeSession = readActiveSessionFromStorage();
      const observationResponse = await createVisualObservation({
        source: 'camera',
        summary,
        confidence: analysis.confidence,
        relatedFocusId: activeSession?.id,
      });

      publishVisualContext(observationResponse.visualContext);
      setAnalysisSummary(summary);
      setAnalysisModel(analysis.model);
      setAnalysisSaved(true);
      setStatus('captured');
      setStatusMessage('Snapshot analyzed. QMeet saved only the returned text observation, not the image.');
    } catch (error) {
      setStatus('captured');
      setStatusMessage(
        error instanceof Error
          ? `Snapshot analysis failed: ${error.message}`
          : 'Snapshot analysis failed.',
      );
    }
  }, [snapshotDataUrl]);

  const clearSnapshot = useCallback(() => {
    setSnapshotDataUrl(null);
    clearAnalysis();
    clearCanvas();
    setStatus(streamRef.current ? 'ready' : 'closed');
    setStatusMessage(streamRef.current ? 'Camera preview is live.' : 'Snapshot cleared. Camera preview is closed.');
  }, [clearAnalysis, clearCanvas]);

  useEffect(() => {
    const handleCameraCommand = (event: Event) => {
      const detail = (event as CustomEvent<CameraCommandDetail>).detail;
      const action = detail?.action;
      if (action === 'open') {
        void startCamera();
      } else if (action === 'close') {
        closeCamera();
      } else if (action === 'snapshot') {
        void captureSnapshot();
      } else if (action === 'analyze') {
        void analyzeSnapshot();
      }
    };

    window.addEventListener(QMEET_CAMERA_COMMAND_EVENT, handleCameraCommand);
    return () => {
      window.removeEventListener(QMEET_CAMERA_COMMAND_EVENT, handleCameraCommand);
    };
  }, [analyzeSnapshot, captureSnapshot, closeCamera, startCamera]);

  useEffect(() => {
    if (!open && !snapshotDataUrl) {
      return undefined;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeCamera();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [closeCamera, open, snapshotDataUrl]);

  useEffect(() => {
    return () => {
      stopStream();
      clearCanvas();
    };
  }, [clearCanvas, stopStream]);

  if (!open && !snapshotDataUrl) {
    return (
      <button
        type="button"
        style={launcherStyle}
        aria-label="Open camera preview"
        title="Open camera preview"
        onClick={() => void startCamera()}
      >
        ◉
      </button>
    );
  }

  const canCapture = status === 'ready' || status === 'captured';
  const canAnalyze = Boolean(snapshotDataUrl) && status !== 'analyzing';

  return (
    <div
      style={overlayStyle}
      role="dialog"
      aria-modal="true"
      aria-label="QMeet camera preview"
      onClick={closeCamera}
    >
      <div style={panelStyle} onClick={(event) => event.stopPropagation()}>
        <div style={headerStyle}>
          <div>
            <h2 style={titleStyle}>Camera Preview</h2>
            <p style={subtitleStyle}>
              Phase 14F one-shot analysis. Preview and snapshots stay local until you tap Analyze Snapshot.
            </p>
          </div>
          <button type="button" style={buttonStyle} onClick={closeCamera}>
            Close
          </button>
        </div>

        <div style={bodyStyle}>
          <div style={previewWrapStyle}>
            {snapshotDataUrl ? (
              <img src={snapshotDataUrl} alt="Captured camera snapshot" style={mediaStyle} />
            ) : (
              <video ref={videoRef} autoPlay muted playsInline style={mediaStyle} />
            )}
            <canvas ref={canvasRef} style={{ display: 'none' }} />
          </div>

          {snapshotDataUrl && (
            <div style={snapshotActionsStyle}>
              <div style={snapshotLabelStyle}>
                Snapshot ready. Analyze saves a text-only camera observation.
              </div>
              <div style={buttonRowStyle}>
                <button
                  type="button"
                  style={canAnalyze ? primaryButtonStyle : disabledButtonStyle}
                  disabled={!canAnalyze}
                  onClick={() => void analyzeSnapshot()}
                >
                  {status === 'analyzing' ? 'Analyzing...' : 'Analyze Snapshot'}
                </button>
                <button
                  type="button"
                  style={status === 'analyzing' ? disabledButtonStyle : buttonStyle}
                  disabled={status === 'analyzing'}
                  onClick={clearSnapshot}
                >
                  Clear
                </button>
              </div>
            </div>
          )}

          {snapshotDataUrl && (
            <div style={privacyStyle}>
              Analyze Snapshot sends this image to OpenAI through your backend for description.
              QMeet stores only the returned text observation in visual context, not the raw image.
            </div>
          )}

          {analysisSummary && (
            <div style={analysisStyle}>
              <strong>Visual observation saved{analysisModel ? ` via ${analysisModel}` : ''}:</strong>
              <div style={{ marginTop: 6 }}>{analysisSummary}</div>
              {analysisSaved && (
                <div style={{ marginTop: 8, color: 'rgba(179, 255, 216, 0.82)' }}>
                  Saved to Visual Context as a camera observation.
                </div>
              )}
            </div>
          )}
        </div>

        <div style={footerStyle}>
          <div
            aria-live="polite"
            style={{
              color: status === 'error' ? '#ffb3b3' : 'rgba(233, 247, 255, 0.72)',
              fontSize: 12,
              lineHeight: 1.35,
              minWidth: 220,
              flex: '1 1 280px',
            }}
          >
            {statusMessage}
          </div>
          <div style={buttonRowStyle}>
            <button
              type="button"
              style={status === 'opening' || status === 'analyzing' ? disabledButtonStyle : buttonStyle}
              disabled={status === 'opening' || status === 'analyzing'}
              onClick={() => void startCamera()}
            >
              Restart preview
            </button>
            <button
              type="button"
              style={canCapture ? primaryButtonStyle : disabledButtonStyle}
              disabled={!canCapture}
              onClick={() => void captureSnapshot()}
            >
              {snapshotDataUrl ? 'Retake' : 'Snapshot'}
            </button>

          </div>
        </div>
      </div>
    </div>
  );
}
