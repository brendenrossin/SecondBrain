"use client";

import { useEffect, useState, useRef, useCallback } from "react";

const HEARTBEAT_MS = 30_000;
const RETRY_MS = 3_000;

export function ConnectionMonitor(): React.ReactElement | null {
  const [disconnected, setDisconnected] = useState(false);
  const polling = useRef(false);
  const timer = useRef<ReturnType<typeof setInterval>>(undefined);

  const checkHealth = useCallback(async (): Promise<boolean> => {
    try {
      const res = await fetch("/api/v1/health", { cache: "no-store" });
      return res.ok;
    } catch {
      return false;
    }
  }, []);

  const startPolling = useCallback(() => {
    if (polling.current) return;
    polling.current = true;
    setDisconnected(true);

    clearInterval(timer.current);
    timer.current = setInterval(async () => {
      if (await checkHealth()) {
        window.location.reload();
      }
    }, RETRY_MS);
  }, [checkHealth]);

  useEffect(() => {
    // Periodic heartbeat — detect server going down even without user action
    const heartbeat = setInterval(async () => {
      if (polling.current) return;
      if (!(await checkHealth())) {
        startPolling();
      }
    }, HEARTBEAT_MS);

    // Check immediately when tab becomes visible
    function onVisibility() {
      if (document.visibilityState !== "visible") return;
      checkHealth().then((ok) => {
        if (!ok) startPolling();
        else if (polling.current) window.location.reload();
      });
    }
    document.addEventListener("visibilitychange", onVisibility);

    // Browser offline/online events
    function onOffline() {
      startPolling();
    }
    function onOnline() {
      checkHealth().then((ok) => {
        if (ok) window.location.reload();
        else startPolling();
      });
    }
    window.addEventListener("offline", onOffline);
    window.addEventListener("online", onOnline);

    return () => {
      clearInterval(heartbeat);
      clearInterval(timer.current);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("offline", onOffline);
      window.removeEventListener("online", onOnline);
    };
  }, [checkHealth, startPolling]);

  if (!disconnected) return null;

  return (
    <div className="fixed inset-0 z-[9999] flex flex-col items-center justify-center bg-bg/95 backdrop-blur-sm">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-text-dim border-t-accent" />
      <p className="mt-4 text-sm text-text-muted">Server restarting...</p>
      <p className="mt-1 text-xs text-text-dim">
        Will reconnect automatically
      </p>
    </div>
  );
}
