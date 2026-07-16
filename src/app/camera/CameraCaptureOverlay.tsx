import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';

export type QMeetCameraCommandAction = 'open' | 'close' | 'snapshot';

export const QMEET_CAMERA_COMMAND_EVENT = 'qmeet-camera-command';

type CameraStatus = 'closed' | 'opening' | 'ready' | 'captured' | 'error';

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
  padding: 20,
  background: 'rgba(2, 8, 18, 0.76)',
  backdropFilter: 'blur(18px)',
};

const panelStyle: CSSProperties = {
  width: 'min(920px, 96vw)',
  maxHeight: '92vh',
  border: '1px solid rgba(124, 219, 255, 0.32)',
  borderRadius: 28,
  background: 'linear-gradient(180deg, rgba(8, 18, 36, 0.96), rgba(5, 10, 22, 0.96))',
  color: '#e9f7ff',
  boxShadow: '0 24px 100px rgba(0, 0, 0, 0.52), 0 0 48px rgba(47, 213, 255, 0.12)',
  overflow: 'hidden',
};

const headerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'space-between',
  gap: 16,
  padding: '20px 22px 14px',
  borderBottom: '1px solid rgba(124, 219, 255, 0.16)',
};

const titleStyle: CSSProperties = {
  margin: 0,
  fontSize: 18,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
};

const subtitleStyle: CSSProperties = {
  margin: '6px 0 0',
  color: 'rgba(233, 247, 255, 0.68)',
  fontSize: 13,
  lineHeight: 1.4,
};

const bodyStyle: CSSProperties = {
  padding: 18,
};

const previewWrapStyle: CSSProperties = {
  position: 'relative',
  display: 'grid',
  placeItems: 'center',
  minHeight: 360,
  borderRadius: 22,
  overflow: 'hidden',
  background: 'radial-gradient(circle at center, rgba(30, 85, 120, 0.24), rgba(2, 8, 18, 0.96))',
  border: '1px solid rgba(124, 219, 255, 0.18)',
};

const mediaStyle: CSSProperties = {
  width: '100%',
  maxHeight: '58vh',
  objectFit: 'contain',
  background: '#020812',
};

const footerStyle: CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 12,
  padding: '14px 22px 20px',
};

const buttonRowStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  flexWrap: 'wrap',
};

const buttonStyle: CSSProperties = {
  border: '1px solid rgba(124, 219, 255, 0.32)',
  borderRadius: 999,
  background: 'rgba(124, 219, 255, 0.10)',
  color: '#e9f7ff',
  padding: '10px 16px',
  fontSize: 13,
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

export function CameraCaptureOverlay() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<CameraStatus>('closed');
  const [statusMessage, setStatusMessage] = useState('Camera preview is closed.');
  const [snapshotDataUrl, setSnapshotDataUrl] = useState<string | null>(null);

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
    setSnapshotDataUrl(null);
    setOpen(false);
    setStatus('closed');
    setStatusMessage('Camera preview is closed.');
  }, [clearCanvas, stopStream]);

  const startCamera = useCallback(async () => {
    setOpen(true);
    setStatus('opening');
    setStatusMessage('Requesting camera permission...');
    setSnapshotDataUrl(null);
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
      setStatusMessage('Camera preview is live. Snapshots stay in memory only and are not uploaded or saved.');
    } catch (error) {
      stopStream();
      setStatus('error');
      setStatusMessage(getCameraErrorMessage(error));
    }
  }, [clearCanvas, stopStream]);

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
    setStatus('captured');
    setStatusMessage('Snapshot captured in memory only. It has not been uploaded or saved.');
  }, [open, startCamera]);

  const clearSnapshot = useCallback(() => {
    setSnapshotDataUrl(null);
    clearCanvas();
    setStatus(streamRef.current ? 'ready' : 'closed');
    setStatusMessage(streamRef.current ? 'Camera preview is live.' : 'Snapshot cleared. Camera preview is closed.');
  }, [clearCanvas]);

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
      }
    };

    window.addEventListener(QMEET_CAMERA_COMMAND_EVENT, handleCameraCommand);
    return () => {
      window.removeEventListener(QMEET_CAMERA_COMMAND_EVENT, handleCameraCommand);
    };
  }, [captureSnapshot, closeCamera, startCamera]);

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
              Phase 14E one-shot capture. Preview and snapshots remain in browser memory only.
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
        </div>

        <div style={footerStyle}>
          <div aria-live="polite" style={{ color: status === 'error' ? '#ffb3b3' : 'rgba(233, 247, 255, 0.72)', fontSize: 13 }}>
            {statusMessage}
          </div>
          <div style={buttonRowStyle}>
            <button
              type="button"
              style={status === 'opening' ? disabledButtonStyle : buttonStyle}
              disabled={status === 'opening'}
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
              Snapshot
            </button>
            {snapshotDataUrl && (
              <button type="button" style={buttonStyle} onClick={clearSnapshot}>
                Clear snapshot
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
