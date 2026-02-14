"use client";

import { useEffect, useState, useRef, useCallback } from "react";

const HEARTBEAT_MS = 30_000;
const RETRY_MS = 3_000;
const HEALTH_TIMEOUT_MS = 5_000;
const FAILURES_BEFORE_DISCONNECT = 2;

export function ConnectionMonitor(): React.ReactElement | null {
  const [disconnected, setDisconnected] = useState(false);
  const polling = useRef(false);
  const timer = useRef<ReturnType<typeof setInterval>>(undefined);
  const failCount = useRef(0);

  const checkHealth = useCallback(async (): Promise<boolean> => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
    try {
      const res = await fetch("/api/v1/health", {
        cache: "no-store",
        signal: controller.signal,
      });
      return res.ok;
    } catch {
      return false;
    } finally {
      clearTimeout(timeout);
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
      const ok = await checkHealth();
      if (!ok) {
        failCount.current += 1;
        if (failCount.current >= FAILURES_BEFORE_DISCONNECT) {
          startPolling();
        }
      } else {
        failCount.current = 0;
      }
    }, HEARTBEAT_MS);

    // Check immediately when tab becomes visible
    function onVisibility() {
      if (document.visibilityState !== "visible") return;
      checkHealth().then((ok) => {
        if (!ok && !polling.current) {
          // On tab switch-back, give it one more try before showing overlay
          setTimeout(() => {
            checkHealth().then((ok2) => {
              if (!ok2) startPolling();
            });
          }, 1_000);
        } else if (ok && polling.current) {
          window.location.reload();
        }
      });
    }
    document.addEventListener("visibilitychange", onVisibility);

    // Browser offline/online events
    function onOnline() {
      checkHealth().then((ok) => {
        if (ok) window.location.reload();
        else startPolling();
      });
    }
    window.addEventListener("offline", startPolling);
    window.addEventListener("online", onOnline);

    return () => {
      clearInterval(heartbeat);
      clearInterval(timer.current);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("offline", startPolling);
      window.removeEventListener("online", onOnline);
    };
  }, [checkHealth, startPolling]);

  if (!disconnected) return null;

  return (
    <div className="fixed inset-0 z-[9999] flex flex-col items-center justify-center bg-bg/95 backdrop-blur-sm">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-text-dim border-t-accent" />
      <p className="mt-4 text-sm text-text-muted">Reconnecting to server...</p>
      <p className="mt-1 text-xs text-text-dim">
        Will reconnect automatically
      </p>
    </div>
  );
}
