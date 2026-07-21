import { useCallback, useEffect, useRef, useState } from 'react';

import { ResultToast } from '../lib/toastUtils';

type ResultToastInput = Omit<ResultToast, 'id' | 'createdAt'> | null;

const MAX_VISIBLE_TOASTS = 2;
const NORMAL_TOAST_MS = 3600;
const ERROR_TOAST_MS = 7200;
const WARNING_TOAST_MS = 5200;

function getToastDuration(kind: ResultToast['kind']) {
  if (kind === 'error') return ERROR_TOAST_MS;
  if (kind === 'warning') return WARNING_TOAST_MS;
  return NORMAL_TOAST_MS;
}

function compactDetail(detail: string) {
  const cleaned = detail.replace(/\s+/g, ' ').trim();
  return cleaned.length > 112 ? `${cleaned.slice(0, 109).trim()}…` : cleaned;
}

export function useResultToasts() {
  const [resultToasts, setResultToasts] = useState<ResultToast[]>([]);
  const resultToastTimeoutsRef = useRef<number[]>([]);

  const dismissResultToast = useCallback((toastId: string) => {
    setResultToasts((prev) => prev.filter((toast) => toast.id !== toastId));
  }, []);

  const clearResultToasts = useCallback(() => {
    resultToastTimeoutsRef.current.forEach((timeoutId) =>
      window.clearTimeout(timeoutId),
    );
    resultToastTimeoutsRef.current = [];
    setResultToasts([]);
  }, []);

  const pushResultToast = useCallback((toastInput: ResultToastInput) => {
    if (!toastInput) return;

    const toastId = `toast-${Date.now()}-${Math.random()
      .toString(36)
      .slice(2)}`;
    const nextToast: ResultToast = {
      ...toastInput,
      detail: compactDetail(toastInput.detail),
      id: toastId,
      createdAt: Date.now(),
    };

    setResultToasts((prev) => {
      const withoutDuplicates = prev.filter(
        (toast) =>
          !(
            toast.kind === nextToast.kind &&
            toast.title === nextToast.title &&
            toast.detail === nextToast.detail
          ),
      );
      return [nextToast, ...withoutDuplicates].slice(0, MAX_VISIBLE_TOASTS);
    });

    const timeoutId = window.setTimeout(() => {
      setResultToasts((prev) => prev.filter((toast) => toast.id !== toastId));
    }, getToastDuration(toastInput.kind));

    resultToastTimeoutsRef.current.push(timeoutId);
  }, []);

  useEffect(() => {
    return () => {
      resultToastTimeoutsRef.current.forEach((timeoutId) =>
        window.clearTimeout(timeoutId),
      );
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
