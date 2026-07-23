import { createRoot } from 'react-dom/client';
import App from './app/App.tsx';
import { CameraCaptureOverlay } from './app/camera/CameraCaptureOverlay';
import { ChatLogToggle } from './app/components/ChatLogToggle';
import { FocusConversationBridge } from './app/components/FocusConversationBridge';
import { WorkContextMemoryBridge } from './app/components/WorkContextMemoryBridge';
import { installQMeetFocusTurnHeaders } from './app/lib/focusTurnHeaders';
import './styles/index.css';

installQMeetFocusTurnHeaders();

createRoot(document.getElementById('root')!).render(
  <>
    <App />
    <CameraCaptureOverlay />
    <ChatLogToggle />
    <WorkContextMemoryBridge />
    <FocusConversationBridge />
  </>,
);
