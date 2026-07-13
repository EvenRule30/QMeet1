import { useEffect, useState } from 'react';
import { getBackendStatus } from '../api';
import { BackendStatus } from '../types';

export function useBackendStatus(pollMs = 10000): BackendStatus | null {
  const [backendStatus, setBackendStatus] = useState<BackendStatus | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchStatus = async () => {
      try {
        const status = await getBackendStatus();
        if (!cancelled) {
          setBackendStatus(status);
        }
      } catch {
        if (!cancelled) {
          setBackendStatus(null);
        }
      }
    };

    fetchStatus();
    const interval = window.setInterval(fetchStatus, pollMs);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [pollMs]);

  return backendStatus;
}
