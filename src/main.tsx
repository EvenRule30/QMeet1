import { createRoot } from 'react-dom/client';
import App from './app/App.tsx';
import { CameraCaptureOverlay } from './app/camera/CameraCaptureOverlay';
import { ChatLogToggle } from './app/components/ChatLogToggle';
import { WorkContextMemoryBridge } from './app/components/WorkContextMemoryBridge';
import './styles/index.css';

createRoot(document.getElementById('root')!).render(
  <>
    <App />
    <CameraCaptureOverlay />
    <ChatLogToggle />
    <WorkContextMemoryBridge />
  </>,
);
