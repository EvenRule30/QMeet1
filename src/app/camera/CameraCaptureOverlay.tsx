import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type CSSProperties,
} from 'react';

import { analyzeVisualSnapshot, createVisualObservation } from '../api';
import type { ActiveSession, VisualContext } from '../types';

export type QMeetCameraCommandAction = 'open' | 'close' | 'snapshot' | 'analyze';

export const QMEET_CAMERA_COMMAND_EVENT = 'qmeet-camera-command';

const ACTIVE_SESSION_SESSION_STORAGE_KEY = 'qmeet-active-session-live';
const ACTIVE_SESSION_STORAGE_KEY = 'qmeet-active-session';
const VISUAL_CONTEXT_STORAGE_KEY = 'qmeet-visual-context';
const VISUAL_CONTEXT_STATE_EVENT = 'qmeet-visual-context-state';

const SUPPORTED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

const delay = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

type CameraStatus = 'closed' | 'opening' | 'ready' | 'captured' | 'analyzing' | 'error';
type SnapshotSource = 'camera' | 'upload' | null;

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
  padding: 8,
  background: 'rgba(2, 8, 18, 0.76)',
  backdropFilter: 'blur(18px)',
};

const panelStyle: CSSProperties = {
  width: 'min(780px, 96vw)',
  maxHeight: 'calc(100vh - 20px)',
  display: 'flex',
  flexDirection: 'column',
  border: '1px solid rgba(124, 219, 255, 0.32)',
  borderRadius: 12,
  background: 'linear-gradient(180deg, rgba(8, 18, 36, 0.96), rgba(5, 10, 22, 0.96))',
  color: '#e9f7ff',
  boxShadow: '0 24px 100px rgba(0, 0, 0, 0.52), 0 0 48px rgba(47, 213, 255, 0.12)',
  overflow: 'hidden',
};

const headerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'space-between',
  gap: 10,
  padding: '10px 14px 8px',
  borderBottom: '1px solid rgba(124, 219, 255, 0.16)',
  flex: '0 0 auto',
};

const titleStyle: CSSProperties = {
  margin: 0,
  fontSize: 13,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
};

const subtitleStyle: CSSProperties = {
  margin: '4px 0 0',
  color: 'rgba(233, 247, 255, 0.68)',
  fontSize: 11,
  lineHeight: 1.35,
};

const bodyStyle: CSSProperties = {
  padding: 10,
  flex: '1 1 auto',
  minHeight: 0,
  overflowY: 'auto',
};

const previewWrapStyle: CSSProperties = {
  position: 'relative',
  display: 'grid',
  placeItems: 'center',
  minHeight: 180,
  maxHeight: 'min(280px, 46vh)',
  borderRadius: 12,
  overflow: 'hidden',
  background: 'radial-gradient(circle at center, rgba(30, 85, 120, 0.24), rgba(2, 8, 18, 0.96))',
  border: '1px solid rgba(124, 219, 255, 0.18)',
  isolation: 'isolate',
};

const uploadedPreviewWrapStyle: CSSProperties = {
  ...previewWrapStyle,
  minHeight: 132,
  maxHeight: 'none',
  placeItems: 'center',
  alignItems: 'center',
  overflow: 'hidden',
  padding: 6,
  background: 'rgba(2, 8, 18, 0.98)',
  overscrollBehavior: 'contain',
};

const mediaStyle: CSSProperties = {
  width: '100%',
  height: 'min(280px, 46vh)',
  objectFit: 'contain',
  background: '#020812',
};

const capturedCameraImageStyle: CSSProperties = {
  ...mediaStyle,
  display: 'block',
  filter: 'none',
  transform: 'none',
  imageRendering: 'auto',
};


const uploadFrameStyle: CSSProperties = {
  width: '100%',
  minHeight: 260,
  height: 'min(420px, 56vh)',
  border: 'none',
  borderRadius: 12,
  background: '#020812',
  display: 'block',
  flex: '0 0 auto',
};

const uploadCardStyle: CSSProperties = {
  width: '100%',
  minHeight: 106,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 6,
  padding: '10px 12px',
  borderRadius: 12,
  background: 'linear-gradient(180deg, rgba(12, 28, 52, 0.82), rgba(4, 10, 22, 0.96))',
  border: '1px solid rgba(124, 219, 255, 0.18)',
  textAlign: 'center',
};

const uploadIconStyle: CSSProperties = {
  width: 42,
  height: 42,
  borderRadius: 12,
  display: 'grid',
  placeItems: 'center',
  border: '1px solid rgba(124, 219, 255, 0.24)',
  background: 'rgba(124, 219, 255, 0.08)',
  fontSize: 20,
};

const uploadNameStyle: CSSProperties = {
  maxWidth: '100%',
  margin: 0,
  fontSize: 13,
  fontWeight: 800,
  color: '#e9f7ff',
  wordBreak: 'break-word',
};

const uploadMetaStyle: CSSProperties = {
  margin: 0,
  color: 'rgba(233, 247, 255, 0.66)',
  fontSize: 11,
  lineHeight: 1.45,
};

const footerStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'stretch',
  justifyContent: 'flex-start',
  gap: 10,
  padding: '8px 14px 10px',
  borderTop: '1px solid rgba(124, 219, 255, 0.14)',
  flex: '0 0 auto',
};

const buttonRowStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'flex-end',
  gap: 6,
  flexWrap: 'wrap',
};

const footerButtonRowStyle: CSSProperties = {
  ...buttonRowStyle,
  justifyContent: 'flex-end',
};

const buttonStyle: CSSProperties = {
  border: '1px solid rgba(124, 219, 255, 0.32)',
  borderRadius: 999,
  background: 'rgba(124, 219, 255, 0.10)',
  color: '#e9f7ff',
  padding: '7px 10px',
  fontSize: 11,
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
  gap: 6,
  flexWrap: 'wrap',
  marginTop: 6,
  padding: '6px 8px',
  borderRadius: 12,
  background: 'rgba(8, 22, 42, 0.72)',
  border: '1px solid rgba(124, 219, 255, 0.16)',
};

const snapshotLabelStyle: CSSProperties = {
  color: 'rgba(233, 247, 255, 0.72)',
  fontSize: 11,
  lineHeight: 1.35,
};

const uploadHintStyle: CSSProperties = {
  color: 'rgba(233, 247, 255, 0.56)',
  fontSize: 11,
  lineHeight: 1.35,
  marginTop: 6,
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
  marginTop: 6,
  border: '1px solid rgba(255, 214, 128, 0.24)',
  borderRadius: 12,
  background: 'rgba(255, 214, 128, 0.08)',
  color: 'rgba(255, 241, 205, 0.88)',
  padding: '6px 8px',
  fontSize: 11,
  lineHeight: 1.35,
};

const analysisStyle: CSSProperties = {
  marginTop: 6,
  border: '1px solid rgba(124, 219, 255, 0.22)',
  borderRadius: 12,
  background: 'rgba(124, 219, 255, 0.08)',
  padding: '8px 10px',
  color: 'rgba(233, 247, 255, 0.86)',
  fontSize: 11,
  lineHeight: 1.4,
};

function getCameraErrorMessage(error: unknown): string {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
    return 'Camera access is not available in this browser.\nTry Chrome/Chromium on localhost or HTTPS.';
  }

  if (error instanceof DOMException) {
    if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
      return 'Camera permission was denied.\nAllow camera access in the browser, then try again.';
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

function revokeObjectUrl(url: string | null): void {
  if (url?.startsWith('blob:')) {
    URL.revokeObjectURL(url);
  }
}


function formatFileSize(bytes: number | null): string | null {
  if (!bytes || bytes <= 0) return null;
  if (bytes < 1024) return `${bytes} B`;
  const kib = bytes / 1024;
  if (kib < 1024) return `${kib.toFixed(kib >= 10 ? 0 : 1)} KB`;
  const mib = kib / 1024;
  return `${mib.toFixed(mib >= 10 ? 1 : 2)} MB`;
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


function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function buildIsolatedUploadPreviewHtml(imageUrl: string, mode: 'fit' | 'actual' | 'zoom150' | 'zoom200' | 'crisp'): string {
  const safeUrl = escapeHtml(imageUrl);
  const zoom = mode === 'zoom200' ? 2 : mode === 'zoom150' ? 1.5 : 1;
  const fitCss = mode === 'fit'
    ? `
      html, body { width: 100%; height: 100%; overflow: hidden; }
      body { display: grid; place-items: center; }
      img { max-width: 100%; max-height: 100%; width: auto; height: auto; }
    `
    : `
      html, body { min-width: 100%; min-height: 100%; overflow: auto; }
      img { width: auto; height: auto; max-width: none; max-height: none; transform: scale(${zoom}); transform-origin: top left; }
    `;
  const renderingCss = mode === 'crisp' ? 'image-rendering: pixelated; image-rendering: crisp-edges;' : 'image-rendering: auto;';

  return `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    padding: 0;
    background: #020812;
    color: #e9f7ff;
  }
  body {
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  img {
    display: block;
    margin: 0;
    border: 0;
    background: transparent;
    filter: none !important;
    transform-style: flat;
    ${renderingCss}
  }
  ${fitCss}
</style>
</head>
<body>
  <img src="${safeUrl}" alt="Uploaded visual preview" />
</body>
</html>`;
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
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const previewUrlRef = useRef<string | null>(null);

  const [open, setOpen] = useState(false);
  const [videoSurfaceKey, setVideoSurfaceKey] = useState(0);
  const [snapshotSurfaceKey, setSnapshotSurfaceKey] = useState(0);
  const [status, setStatus] = useState<CameraStatus>('closed');
  const [statusMessage, setStatusMessage] = useState('Camera preview is closed.');
  const [snapshotPreviewUrl, setSnapshotPreviewUrl] = useState<string | null>(null);
  const [snapshotBlob, setSnapshotBlob] = useState<Blob | null>(null);
  const [snapshotSource, setSnapshotSource] = useState<SnapshotSource>(null);
  const [uploadedImageSize, setUploadedImageSize] = useState<{ width: number; height: number } | null>(null);
  const [uploadFileName, setUploadFileName] = useState<string | null>(null);
  const [uploadFileSizeBytes, setUploadFileSizeBytes] = useState<number | null>(null);
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

  const clearSnapshotState = useCallback(() => {
    revokeObjectUrl(previewUrlRef.current);
    previewUrlRef.current = null;
    setSnapshotPreviewUrl(null);
    setSnapshotBlob(null);
    setSnapshotSource(null);
    setUploadedImageSize(null);
    setUploadFileName(null);
    setUploadFileSizeBytes(null);
    setSnapshotSurfaceKey((current) => current + 1);
    clearAnalysis();
    clearCanvas();
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [clearAnalysis, clearCanvas]);

  const stopStream = useCallback(() => {
    const stream = streamRef.current;
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.srcObject = null;
      videoRef.current.load();
    }
  }, []);

  const closeCamera = useCallback(() => {
    stopStream();
    clearSnapshotState();
    setOpen(false);
    setStatus('closed');
    setStatusMessage('Camera preview is closed.');
  }, [clearSnapshotState, stopStream]);

  const startCamera = useCallback(async () => {
    setOpen(true);
    setStatus('opening');
    setStatusMessage('Requesting camera permission...');
    clearSnapshotState();

    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setStatus('error');
      setStatusMessage('Camera access is not available in this browser.\nTry Chrome/Chromium on localhost or HTTPS.');
      return;
    }

    try {
      stopStream();
      setVideoSurfaceKey((current) => current + 1);
      await delay(40);

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });

      streamRef.current = stream;

      await delay(0);
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => undefined);
      }

      setStatus('ready');
      setStatusMessage('Camera preview is live. Snapshot stays local until Analyze is tapped.');
    } catch (error) {
      stopStream();
      setStatus('error');
      setStatusMessage(getCameraErrorMessage(error));
    }
  }, [clearSnapshotState, stopStream]);

  const resetPreview = useCallback(async () => {
    setStatus('opening');
    setStatusMessage('Resetting the camera preview...');
    stopStream();
    setOpen(false);
    setVideoSurfaceKey((current) => current + 1);
    await delay(120);
    await startCamera();
  }, [startCamera, stopStream]);

  const captureSnapshot = useCallback(async () => {
    if (!open) {
      await startCamera();
      setStatusMessage('Camera opened.\nPress Snapshot once the preview is visible.');
      return;
    }

    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !video.videoWidth || !video.videoHeight) {
      setStatusMessage('Camera frame is not ready yet.\nTry Snapshot again in a moment.');
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

    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob(resolve, 'image/jpeg', 0.92);
    });

    if (!blob) {
      setStatus('error');
      setStatusMessage('Could not create a snapshot image.');
      return;
    }

    clearSnapshotState();
    const nextPreviewUrl = URL.createObjectURL(blob);
    previewUrlRef.current = nextPreviewUrl;
    setSnapshotPreviewUrl(nextPreviewUrl);
    setSnapshotBlob(blob);
    setSnapshotSource('camera');
    setStatus('captured');
    setStatusMessage('Snapshot captured locally. Analyze when ready.');
  }, [clearSnapshotState, open, startCamera]);

  const openUploadPicker = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const openOriginalUpload = useCallback(() => {
    if (!snapshotPreviewUrl || snapshotSource !== 'upload') {
      return;
    }

    window.open(snapshotPreviewUrl, '_blank', 'noopener,noreferrer');
  }, [snapshotPreviewUrl, snapshotSource]);

  const handleUploadImage = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    if (!SUPPORTED_IMAGE_TYPES.has(file.type)) {
      event.target.value = '';
      setStatus('error');
      setStatusMessage('Upload a JPEG, PNG, or WebP image.');
      return;
    }

    stopStream();
    clearSnapshotState();
    setOpen(false);
    setVideoSurfaceKey((current) => current + 1);
    setSnapshotSurfaceKey((current) => current + 1);

    const previewUrl = URL.createObjectURL(file);
    previewUrlRef.current = previewUrl;
    setUploadedImageSize(null);
    setUploadFileName(file.name);
    setUploadFileSizeBytes(file.size);
    const image = new Image();
    image.onload = () => {
      setUploadedImageSize({ width: image.naturalWidth, height: image.naturalHeight });
    };
    image.src = previewUrl;
    setSnapshotPreviewUrl(previewUrl);
    setSnapshotBlob(file);
    setSnapshotSource('upload');
    setOpen(true);
    setStatus('captured');
    setStatusMessage('Image loaded from your computer. Analyze sends the original file; QMeet saves only text.');
  }, [clearSnapshotState, stopStream]);


  const analyzeSnapshot = useCallback(async () => {
    if (!snapshotBlob || !snapshotSource) {
      setStatusMessage('Take or upload a snapshot before analyzing it.');
      return;
    }

    setStatus('analyzing');
    setStatusMessage('Sending this one image to OpenAI through the backend for description...');

    try {
      const analysis = await analyzeVisualSnapshot(snapshotBlob);
      const summary = analysis.summary.trim();
      if (!summary) {
        throw new Error('OpenAI returned an empty visual description.');
      }

      const activeSession = readActiveSessionFromStorage();
      const observationResponse = await createVisualObservation({
        source: snapshotSource === 'camera' ? 'camera' : 'manual',
        summary,
        confidence: analysis.confidence,
        relatedFocusId: activeSession?.id,
      });

      publishVisualContext(observationResponse.visualContext);
      setAnalysisSummary(summary);
      setAnalysisModel(analysis.model);
      setAnalysisSaved(true);
      setStatus('captured');
      setStatusMessage('Image analyzed.\nQMeet saved only the returned text observation, not the image.');
    } catch (error) {
      setStatus('captured');
      setStatusMessage(
        error instanceof Error
          ? `Snapshot analysis failed: ${error.message}`
          : 'Snapshot analysis failed.',
      );
    }
  }, [snapshotBlob, snapshotSource]);

  const clearSnapshot = useCallback(async () => {
    const clearedUpload = snapshotSource === 'upload';
    clearSnapshotState();

    if (open) {
      if (clearedUpload || !streamRef.current) {
        setStatus('opening');
        setStatusMessage('Cleared uploaded image. Restarting camera preview...');
        await startCamera();
      } else {
        setStatus('ready');
        setStatusMessage('Camera preview is live.');
      }
    } else {
      setStatus('closed');
      setStatusMessage('Snapshot cleared.\nCamera preview is closed.');
    }
  }, [clearSnapshotState, open, snapshotSource, startCamera]);

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
    if (!open && !snapshotPreviewUrl) {
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
  }, [closeCamera, open, snapshotPreviewUrl]);

  useEffect(() => {
    return () => {
      stopStream();
      clearCanvas();
      revokeObjectUrl(previewUrlRef.current);
    };
  }, [clearCanvas, stopStream]);

  if (!open && !snapshotPreviewUrl) {
    return (
      <button
        type="button"
        style={launcherStyle}
        aria-label="Open camera"
        title="Open camera"
        onClick={() => void startCamera()}
      >
        ◉
      </button>
    );
  }

  const canCapture = status === 'ready' || status === 'captured';
  const canAnalyze = Boolean(snapshotBlob) && status !== 'analyzing';
  const isUploadedSnapshot = snapshotSource === 'upload';
  const uploadedIsPortrait = Boolean(
    uploadedImageSize && uploadedImageSize.height > uploadedImageSize.width,
  );
  const uploadFileSizeLabel = formatFileSize(uploadFileSizeBytes);
  const activeOverlayStyle: CSSProperties = isUploadedSnapshot
    ? { ...overlayStyle, backdropFilter: 'none' }
    : overlayStyle;
  const previewLabel = isUploadedSnapshot
    ? 'Uploaded image ready. Preview is hidden; analyze uses the original file.'
    : 'Snapshot ready. Analyze saves a text-only camera observation.';

  return (
    <div style={activeOverlayStyle} onClick={closeCamera}>
      <div style={panelStyle} onClick={(event) => event.stopPropagation()}>
        <div style={headerStyle}>
          <div>
            <h2 style={titleStyle}>Camera Preview</h2>
            <p style={subtitleStyle}>
              One-shot visual analysis. Analyze sends one image; QMeet stores only text.
            </p>
          </div>
          <button type="button" style={buttonStyle} onClick={closeCamera}>
            Close
          </button>
        </div>

        <div style={bodyStyle}>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            style={{ display: 'none' }}
            onChange={handleUploadImage}
          />

          <div
            key={snapshotPreviewUrl && snapshotSource === 'upload' ? `upload-surface-${snapshotSurfaceKey}` : 'camera-surface'}
            style={snapshotSource === 'upload' ? uploadedPreviewWrapStyle : previewWrapStyle}
          >
            {snapshotPreviewUrl && isUploadedSnapshot ? (
              <div key={`upload-card-${snapshotSurfaceKey}-${snapshotPreviewUrl}`} style={uploadCardStyle}>
                <div style={uploadIconStyle}>▧</div>
                <p style={uploadNameStyle}>{uploadFileName ?? 'Uploaded image'}</p>
                <p style={uploadMetaStyle}>
                  {uploadedImageSize
                    ? `${uploadedImageSize.width}×${uploadedImageSize.height}`
                    : 'Reading dimensions'}
                  {uploadFileSizeLabel ? ` · ${uploadFileSizeLabel}` : ''}
                  {uploadedIsPortrait ? ' · Portrait' : uploadedImageSize ? ' · Landscape/square' : ''}
                </p>
                <p style={uploadMetaStyle}>Preview hidden to avoid blur. Use Open original to inspect; Analyze uses the original file.</p>
              </div>
            ) : snapshotPreviewUrl ? (
              <img
                key={`${snapshotSource ?? 'snapshot'}-${snapshotSurfaceKey}-${snapshotPreviewUrl}`}
                src={snapshotPreviewUrl}
                alt="Captured camera snapshot"
                style={capturedCameraImageStyle}
                decoding="sync"
                draggable={false}
              />
            ) : (
              <video
                key={videoSurfaceKey}
                ref={videoRef}
                style={mediaStyle}
                autoPlay
                muted
                playsInline
              />
            )}
          </div>



          {snapshotPreviewUrl && (
            <div style={snapshotActionsStyle}>
              <span style={snapshotLabelStyle}>{previewLabel}</span>
              <div style={buttonRowStyle}>
                {isUploadedSnapshot && (
                  <button type="button" style={buttonStyle} onClick={openOriginalUpload}>
                    Open original
                  </button>
                )}
                <button
                  type="button"
                  style={canAnalyze ? primaryButtonStyle : disabledButtonStyle}
                  disabled={!canAnalyze}
                  onClick={() => void analyzeSnapshot()}
                >
                  {status === 'analyzing' ? 'Analyzing...' : isUploadedSnapshot ? 'Analyze image' : 'Analyze Snapshot'}
                </button>
                {isUploadedSnapshot && (
                  <button type="button" style={buttonStyle} onClick={openUploadPicker}>
                    Replace
                  </button>
                )}
                <button type="button" style={buttonStyle} onClick={() => void clearSnapshot()}>
                  {isUploadedSnapshot ? 'Back to camera' : 'Clear'}
                </button>
              </div>
            </div>
          )}

          {snapshotPreviewUrl && (
            <div style={privacyStyle}>
              Analyze sends this image to OpenAI through your backend. QMeet stores only the returned text observation.
            </div>
          )}

          {analysisSummary && (
            <div style={analysisStyle}>
              <strong>Visual observation saved{analysisModel ? ` via ${analysisModel}` : ''}:</strong>
              <div style={{ marginTop: 6 }}>{analysisSummary}</div>
              {analysisSaved && (
                <div style={{ marginTop: 6, color: 'rgba(155, 255, 205, 0.86)' }}>
                  Saved to Visual Context as a {snapshotSource === 'camera' ? 'camera' : 'manual'} observation.
                </div>
              )}
            </div>
          )}
        </div>

        <div style={footerStyle}>
          <div style={snapshotLabelStyle}>{statusMessage}</div>
          <div style={footerButtonRowStyle}>
            {isUploadedSnapshot ? (
              <>
                <button type="button" style={buttonStyle} onClick={openUploadPicker}>
                  Upload another
                </button>
                <button type="button" style={buttonStyle} onClick={() => void clearSnapshot()}>
                  Back to camera
                </button>
              </>
            ) : (
              <>
                <button type="button" style={buttonStyle} onClick={() => void resetPreview()}>
                  Reset preview
                </button>
                <button type="button" style={buttonStyle} onClick={openUploadPicker}>
                  Upload image
                </button>
                <button
                  type="button"
                  style={canCapture ? primaryButtonStyle : disabledButtonStyle}
                  disabled={!canCapture}
                  onClick={() => void captureSnapshot()}
                >
                  {snapshotPreviewUrl && snapshotSource === 'camera' ? 'Retake' : 'Snapshot'}
                </button>
              </>
            )}
          </div>
        </div>

        <canvas ref={canvasRef} style={{ display: 'none' }} />
      </div>
    </div>
  );
}
