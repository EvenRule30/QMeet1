import AppCore from './AppCore';
import { installNativeReadSurfaceCapture } from './lib/nativeReadSurfaceBridge';

installNativeReadSurfaceCapture();

export default AppCore;
