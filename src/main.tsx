import { createRoot } from "react-dom/client";
import App from "./app/App.tsx";
import { CameraCaptureOverlay } from "./app/camera/CameraCaptureOverlay";
import "./styles/index.css";

createRoot(document.getElementById("root")!).render(
  <>
    <App />
    <CameraCaptureOverlay />
  </>,
);
