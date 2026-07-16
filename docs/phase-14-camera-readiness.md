# Phase 14 Camera Readiness Plan

Phase 14 prepares QMeet for camera support without making live video a hard dependency yet.

The goal is to make camera input feel like a natural extension of QMeet's existing context system:

```text
voice/text input -> command/chat routing -> memory/context update
camera/manual visual input -> visual observation -> memory/context update -> focus-aware chat
```

Phase 14A and 14B already established the `visualContext` model and frontend display. Phase 14C proved the observation pipeline with manual visual notes. Phase 14D defines the implementation boundary for actual camera support.

## Current foundation

QMeet now has a persistent visual context model:

```ts
type VisualContext = {
  enabled: boolean;
  lastObservation: VisualObservation | null;
  recentObservations: VisualObservation[];
};

type VisualObservation = {
  id: string;
  source: 'camera' | 'screen' | 'manual';
  summary: string;
  capturedAt: string;
  confidence?: number;
  relatedFocusId?: string;
};
```

Current sources:

```text
manual -> user says something like "note visually that the tablet is on the desk"
camera -> planned one-shot snapshot support
screen -> planned future screen/context observation support
```

The important design decision is that QMeet should store **observations**, not raw camera feeds.

## Product principle

Camera support should not be a separate gimmick. It should feed the same context engine as focus sessions, tasks, notes, and recaps.

A good camera flow should feel like this:

```text
User: look at this prototype
QMeet: captures one frame with permission
Backend/model: describes the frame
QMeet: stores a visual observation
Chat: can refer to the observation while helping with the active focus
```

The camera becomes another context source, not a separate app mode.

## Recommended camera rollout

### Phase 14E — one-shot browser camera snapshot UI

Add explicit, user-triggered browser camera capture.

Target commands:

```text
take a visual snapshot
look at this
capture what I am looking at
use the camera once
```

Target behavior:

```text
- Opens a lightweight camera preview or capture overlay.
- Browser asks for camera permission if needed.
- User confirms capture.
- Frontend captures a single frame.
- No automatic repeated capture.
- No backend camera hardware assumptions yet.
```

Recommended frontend path:

```text
navigator.mediaDevices.getUserMedia({ video: true })
video preview -> canvas snapshot -> Blob/File -> backend analyze endpoint
```

Likely frontend files:

```text
src/app/commands.ts
src/app/commandHandlers/memory.ts or new commandHandlers/visual.ts
src/app/components/CameraCaptureOverlay.tsx
src/app/hooks/useCameraCapture.ts
src/app/panels/MemoryOverlay.tsx
src/app/types.ts
src/app/api.ts
backend/app/routers/command.py
```

### Phase 14F — backend image analysis endpoint

Add a backend route that accepts a one-shot image and returns a visual observation.

Suggested route:

```text
POST /api/visual/analyze-snapshot
```

Suggested request:

```text
multipart/form-data
- image: file
- source: camera
- relatedFocusId?: string
- prompt?: optional user instruction such as "describe this prototype"
```

Suggested response:

```ts
type AnalyzeSnapshotResponse = {
  observation: VisualObservation;
};
```

Backend flow:

```text
receive image -> send to vision-capable model -> create concise summary -> save as visual observation -> return observation
```

Recommended default: do not save raw images in `backend/data`. Store only the generated text observation unless a future setting explicitly enables image retention.

Likely backend files:

```text
backend/app/main.py
backend/app/routers/visual.py
backend/app/schemas.py
backend/app/memory_store.py
backend/app/agent.py or new vision_service.py
backend/requirements.txt if image parsing helpers are needed
```

### Phase 14G — save camera observations into visualContext

After a successful snapshot analysis, QMeet should append the result to `visualContext.recentObservations` and set `visualContext.lastObservation`.

If an active focus exists, the observation should link to it:

```ts
relatedFocusId: activeSession.id
```

Example saved observation:

```json
{
  "id": "visual-...",
  "source": "camera",
  "summary": "A small prototype tablet is on a desk next to a laptop and charging cable.",
  "capturedAt": "2026-07-16T16:20:00.000Z",
  "confidence": 0.82,
  "relatedFocusId": "session-..."
}
```

### Phase 14H — focus-aware camera use

Once snapshots work, QMeet can use active focus context when interpreting images.

Examples:

```text
Active focus: QMeet prototype hardware
User: look at this
QMeet: focuses description on the tablet, cable, desk setup, and prototype state
```

```text
Active focus: meeting prep
User: capture the whiteboard
QMeet: extracts visible agenda items into a visual observation and can turn them into notes/tasks
```

### Phase 14I — optional continuous visual awareness

Continuous or periodic camera awareness should come later and remain explicitly opt-in.

Potential modes:

```text
manual only       user triggers every snapshot
session assisted  user enables snapshots during the active focus only
interval mode     QMeet captures every N minutes while focus is active
always-on         not recommended for the prototype default
```

Recommended default for prototype:

```text
manual only
```

If interval mode is added later, it should have visible status, a quick stop control, and clear memory behavior.

## Browser camera vs backend camera

### Browser camera first

Recommended first implementation:

```text
React frontend uses browser getUserMedia
```

Reasons:

```text
- Works on laptop and Chromium kiosk paths.
- Browser owns permission prompts.
- No need to configure Raspberry Pi camera drivers yet.
- Easier to test during normal Vite development.
```

### Backend/Pi camera later

A backend camera path may be useful later for a final tablet build, especially if the camera should be controlled by the device backend rather than browser APIs.

Possible future route:

```text
POST /api/visual/capture-device-camera
```

But this should wait until hardware constraints are clearer:

```text
- Pi model
- camera module type
- Chromium permissions
- kiosk deployment method
- whether the frontend and backend run on the same device
```

## Privacy and storage defaults

Recommended defaults:

```text
- Camera capture is user-triggered.
- No continuous capture in Phase 14E/F.
- Do not save raw images by default.
- Store text observations only.
- Show visual context in the Memory panel.
- Allow clear visual context and delete individual observations.
```

Optional future settings:

```text
visual context enabled/disabled
camera snapshots enabled/disabled
retain raw images never/session/manual
maximum recent observations
continuous capture interval
```

## Chat integration

Once camera observations exist, normal chat context can include a compact visual block.

Suggested injected context:

```text
Current visual context:
Last observation: A small prototype tablet is on a desk next to a laptop.
Captured: 4:20 PM
Related focus: QMeet hardware setup
Recent observations: 2
```

The chat stream should keep this short. It should not dump the full visual history unless the user asks.

Useful prompts after camera support:

```text
what am I looking at
use what you just saw
turn the whiteboard into tasks
summarize the visual context
what changed visually since earlier
```

## Command routing plan

Add local command actions:

```text
capture-visual-snapshot
describe-last-visual-observation
clear-visual-context
delete-last-visual-observation
```

Existing Phase 14C commands already cover manual observations:

```text
create-visual-observation
read-visual-context
clear-visual-context
delete-last-visual-observation
```

The backend fuzzy command router should map natural camera phrases before falling back to ChatGPT:

```text
look at this -> capture visual snapshot
take a visual snapshot -> capture visual snapshot
what do you see -> describe last visual observation, or request a snapshot if none exists
```

## UI plan

Minimum 14E UI:

```text
- temporary camera overlay
- preview area
- Capture button
- Cancel button
- status text for permission/capture/analyze states
```

Memory panel Visual Context section should show:

```text
- last observation
- recent observations
- source badge: manual/camera/screen
- related focus title if available
- remove / clear controls
```

Top status bar could later show a subtle camera-ready indicator, but not required for 14E.

## Error handling

Camera support should handle:

```text
- browser does not support getUserMedia
- user denies camera permission
- no camera found
- capture failed
- backend unavailable
- model analysis failed
- image too large
```

Recommended user-facing messages:

```text
Camera permission was blocked. Enable camera permission in the browser and try again.
I could not find a camera on this device.
I captured the image, but analysis failed. Try again or add a manual visual note.
```

## Regression checklist

Before shipping camera snapshot support, test:

```text
Manual visual context still works:
- note visually that the tablet is on the desk
- what was the last visual observation
- delete last visual observation
- clear visual context

Focus link still works:
- start a coding focus session for camera support
- note visually that the prototype is on the desk
- verify relatedFocusId is set or visible in memory JSON

Camera permission states:
- allow camera
- deny camera
- no camera device
- reload page after permission

Snapshot flow:
- open camera overlay
- cancel without capture
- capture image
- analyze image
- save observation
- open Memory panel and verify observation

Memory safety:
- visualContext survives debounced memory saves
- export includes visualContext
- import restores visualContext
- clear all memory clears visualContext
```

## Definition of done for Phase 14E/F

A first real camera implementation is complete when:

```text
- user can explicitly trigger a one-shot camera capture
- browser permission is handled gracefully
- the snapshot is analyzed by the backend/model
- a camera VisualObservation is saved into visualContext
- Memory panel updates immediately
- chat can refer to the latest visual observation
- no raw image is persisted by default
```

## Open decisions

```text
- Should the camera overlay live in App.tsx state or its own hook/panel?
- Should images be resized/compressed frontend-side before upload?
- Which model should analyze images?
- Should image analysis be a separate backend service module?
- Should visual observations be included in enhanced work recaps?
- How many visual observations should be retained by default?
- Should camera be available when no active focus exists, or should QMeet encourage starting a focus first?
```

Recommended next step:

```text
Phase 14E: browser one-shot camera overlay and capture plumbing.
```
