import { useCallback, useEffect, useRef, useState } from 'react';
import { ResultToast } from '../lib/toastUtils';

type ResultToastInput = Omit<ResultToast, 'id' | 'createdAt'> | null;

export function useResultToasts() {
  const [resultToasts, setResultToasts] = useState<ResultToast[]>([]);
  const resultToastTimeoutsRef = useRef<number[]>([]);

  const dismissResultToast = useCallback((toastId: string) => {
    setResultToasts((prev) => prev.filter((toast) => toast.id !== toastId));
  }, []);

  const clearResultToasts = useCallback(() => {
    resultToastTimeoutsRef.current.forEach((timeoutId) => window.clearTimeout(timeoutId));
    resultToastTimeoutsRef.current = [];
    setResultToasts([]);
  }, []);

  const pushResultToast = useCallback((toastInput: ResultToastInput) => {
    if (!toastInput) return;

    const toastId = `toast-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const nextToast: ResultToast = {
      ...toastInput,
      id: toastId,
      createdAt: Date.now(),
    };

    setResultToasts((prev) => [nextToast, ...prev].slice(0, 3));

    const timeoutId = window.setTimeout(() => {
      setResultToasts((prev) => prev.filter((toast) => toast.id !== toastId));
    }, toastInput.kind === 'error' ? 7000 : 4400);

    resultToastTimeoutsRef.current.push(timeoutId);
  }, []);

  useEffect(() => {
    return () => {
      resultToastTimeoutsRef.current.forEach((timeoutId) => window.clearTimeout(timeoutId));
      resultToastTimeoutsRef.current = [];
    };
  }, []);

  return {
    resultToasts,
    pushResultToast,
    dismissResultToast,
    clearResultToasts,
  };
}
