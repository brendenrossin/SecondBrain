"use client";

import { useState, useRef, useEffect } from "react";
import {
  Send,
  Check,
  AlertCircle,
  Link,
  Globe,
  Youtube,
  FileText,
  Loader2,
  ShieldCheck,
  ShieldX,
} from "lucide-react";
import { captureText, wikiIngest, wikiIngestStatus } from "@/lib/api";
import type { CaptureConnection } from "@/lib/types";

type Status = "idle" | "sending" | "success" | "error";
type ContentType = "web_article" | "youtube" | "pdf" | null;
type UrlStatus = "idle" | "loading" | "success" | "error";

const STAGE_LABELS: Record<string, string> = {
  fetching: "Fetching content...",
  auditing: "Running safety audit...",
  compiling: "Compiling wiki page...",
  indexing: "Indexing...",
  complete: "Done!",
  failed: "Failed",
};

function detectContentType(url: string): ContentType {
  if (!url.trim()) return null;
  try {
    const parsed = new URL(url);
    if (parsed.hostname.includes("youtube.com") || parsed.hostname === "youtu.be") return "youtube";
    if (parsed.pathname.toLowerCase().endsWith(".pdf")) return "pdf";
    if (parsed.protocol === "http:" || parsed.protocol === "https:") return "web_article";
  } catch { /* not a valid URL */ }
  return null;
}

function ContentTypeBadge({ type }: { type: ContentType }): React.JSX.Element | null {
  if (!type) return null;
  const configs = {
    web_article: { icon: Globe, label: "Web Article" },
    youtube: { icon: Youtube, label: "YouTube" },
    pdf: { icon: FileText, label: "PDF" },
  };
  const { icon: Icon, label } = configs[type];
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-accent/15 text-accent">
      <Icon className="w-3 h-3" />
      {label}
    </span>
  );
}

export function CaptureForm(): React.JSX.Element {
  // --- Text capture state ---
  const [text, setText] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState("");
  const [connections, setConnections] = useState<CaptureConnection[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const resetTimerRef = useRef<ReturnType<typeof setTimeout>>(null);

  // --- URL ingest state ---
  const [url, setUrl] = useState("");
  const [urlStatus, setUrlStatus] = useState<UrlStatus>("idle");
  const [urlStage, setUrlStage] = useState<string>("");
  const [urlMessage, setUrlMessage] = useState("");
  const [auditPassed, setAuditPassed] = useState<boolean | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval>>(null);

  // Clean up timers on unmount
  useEffect(() => {
    return () => {
      if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // Clear stale text feedback when user starts typing
  useEffect(() => {
    if (text.length > 0) {
      setConnections([]);
      if (resetTimerRef.current) {
        clearTimeout(resetTimerRef.current);
        resetTimerRef.current = null;
        setStatus("idle");
        setMessage("");
      }
    }
  }, [text]);

  // --- Text capture ---
  async function handleSubmit(): Promise<void> {
    const trimmed = text.trim();
    if (!trimmed || status === "sending") return;

    setStatus("sending");
    setMessage("");
    setConnections([]);

    try {
      const res = await captureText(trimmed);
      setStatus("success");
      setMessage(res.message);
      setConnections(res.connections ?? []);
      setText("");
      resetTimerRef.current = setTimeout(() => {
        setStatus("idle");
        setMessage("");
        setConnections([]);
        textareaRef.current?.focus();
      }, 3000);
    } catch (err) {
      setStatus("error");
      setMessage(err instanceof Error ? err.message : "Failed to capture");
    }
  }

  function handleKeyDown(e: React.KeyboardEvent): void {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
    }
  }

  // --- URL ingest ---
  const contentType = detectContentType(url);

  async function handleUrlIngest(): Promise<void> {
    const trimmed = url.trim();
    if (!trimmed || urlStatus === "loading") return;

    setUrlStatus("loading");
    setUrlStage("fetching");
    setUrlMessage("");
    setAuditPassed(null);

    if (pollRef.current) clearInterval(pollRef.current);

    try {
      const res = await wikiIngest(trimmed);
      const jobId = res.job_id;

      pollRef.current = setInterval(async () => {
        try {
          const statusRes = await wikiIngestStatus(jobId);
          setUrlStage(statusRes.status);

          if (statusRes.status === "auditing") {
            // audit in progress — no verdict yet
          } else if (statusRes.status === "compiling") {
            setAuditPassed(true);
          }

          if (statusRes.status === "complete") {
            clearInterval(pollRef.current!);
            pollRef.current = null;
            setUrlStatus("success");
            setAuditPassed(true);
            setUrlMessage(
              statusRes.result_title
                ? `Saved: ${statusRes.result_title}`
                : "Successfully ingested"
            );
            setUrl("");
          } else if (statusRes.status === "failed") {
            clearInterval(pollRef.current!);
            pollRef.current = null;
            setUrlStatus("error");
            setAuditPassed(statusRes.error?.includes("audit") ? false : null);
            setUrlMessage(statusRes.error || "Ingestion failed");
          }
        } catch (pollErr) {
          clearInterval(pollRef.current!);
          pollRef.current = null;
          setUrlStatus("error");
          setUrlMessage(pollErr instanceof Error ? pollErr.message : "Failed to check status");
        }
      }, 1000);
    } catch (err) {
      setUrlStatus("error");
      setUrlStage("failed");
      setUrlMessage(err instanceof Error ? err.message : "Failed to start ingestion");
    }
  }

  function handleUrlKeyDown(e: React.KeyboardEvent): void {
    if (e.key === "Enter") {
      e.preventDefault();
      handleUrlIngest();
    }
  }

  const isUrlLoading = urlStatus === "loading";
  const stageLabel = STAGE_LABELS[urlStage] ?? urlStage;

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      {/* URL Ingest Card */}
      <div className="glass-card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Link className="w-4 h-4 text-accent" />
          <h2 className="text-sm font-semibold text-text">Ingest External Content</h2>
        </div>

        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <input
              type="url"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                if (urlStatus !== "idle") {
                  setUrlStatus("idle");
                  setUrlStage("");
                  setUrlMessage("");
                  setAuditPassed(null);
                }
              }}
              onKeyDown={handleUrlKeyDown}
              placeholder="https://..."
              className="w-full bg-transparent text-text placeholder:text-text-dim text-sm leading-relaxed focus:outline-none border border-border rounded-lg px-3 py-2 pr-24"
              disabled={isUrlLoading}
            />
            {contentType && (
              <div className="absolute right-2 top-1/2 -translate-y-1/2">
                <ContentTypeBadge type={contentType} />
              </div>
            )}
          </div>

          <button
            onClick={handleUrlIngest}
            disabled={!url.trim() || isUrlLoading}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
          >
            {isUrlLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Globe className="w-4 h-4" />
            )}
            {isUrlLoading ? "Ingesting..." : "Ingest"}
          </button>
        </div>

        {/* URL status feedback */}
        {(isUrlLoading || urlMessage) && (
          <div className="mt-3">
            {isUrlLoading && (
              <div className="flex items-center gap-2 text-xs text-accent">
                <Loader2 className="w-3 h-3 animate-spin" />
                <span>{stageLabel}</span>
                {urlStage === "auditing" && (
                  <span className="text-text-dim">— checking content safety</span>
                )}
              </div>
            )}
            {!isUrlLoading && urlMessage && (
              <div
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs ${
                  urlStatus === "success"
                    ? "bg-success/10 text-success"
                    : "bg-red-500/10 text-red-400"
                }`}
              >
                {urlStatus === "success" ? (
                  auditPassed === false ? (
                    <ShieldX className="w-3.5 h-3.5 shrink-0" />
                  ) : (
                    <ShieldCheck className="w-3.5 h-3.5 shrink-0" />
                  )
                ) : auditPassed === false ? (
                  <ShieldX className="w-3.5 h-3.5 shrink-0" />
                ) : (
                  <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                )}
                {urlMessage}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Text Capture Card */}
      <div className="glass-card p-6">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="What's on your mind? Capture a thought, task, or note..."
          className="w-full h-40 bg-transparent text-text placeholder:text-text-dim text-sm leading-relaxed resize-none focus:outline-none"
          disabled={status === "sending"}
          autoFocus
        />

        <div className="flex items-center justify-between mt-4 pt-4 border-t border-border">
          <span className="text-xs text-text-dim">
            {text.length > 0 ? `${text.length.toLocaleString()} chars` : ""}
            {text.length > 0 && (
              <span className="ml-3 opacity-60">
                {/Mac|iPhone|iPad/.test(navigator.userAgent) ? "\u2318" : "Ctrl"}
                +Enter to send
              </span>
            )}
          </span>

          <button
            onClick={handleSubmit}
            disabled={!text.trim() || status === "sending"}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Send className="w-4 h-4" />
            {status === "sending" ? "Sending..." : "Capture"}
          </button>
        </div>
      </div>

      {/* Text capture status feedback */}
      {message && (
        <div
          className={`flex items-center gap-2 px-4 py-3 rounded-lg text-sm ${
            status === "success"
              ? "bg-success/10 text-success"
              : "bg-red-500/10 text-red-400"
          }`}
        >
          {status === "success" ? (
            <Check className="w-4 h-4 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0" />
          )}
          {message}
        </div>
      )}

      {/* Connection cards */}
      {connections.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-text-dim font-medium">
            Related in your vault:
          </p>
          {connections.map((conn) => {
            const folder = conn.note_path.includes("/")
              ? conn.note_path.split("/")[0]
              : "";
            return (
              <div
                key={conn.note_path}
                className="glass-card px-4 py-3 space-y-1"
              >
                {folder && (
                  <span className="text-[10px] font-medium text-accent/70 uppercase tracking-wider">
                    {folder}
                  </span>
                )}
                <p className="text-sm font-medium text-text">
                  {conn.note_title}
                </p>
                <p className="text-xs text-text-dim line-clamp-2">
                  {conn.snippet}
                </p>
              </div>
            );
          })}
        </div>
      )}

      <p className="text-xs text-text-dim text-center leading-relaxed">
        Paste a URL above to fetch and index external content into your wiki.
        <br />
        Use the text area to capture quick thoughts — saved to your Inbox and routed on next sync.
      </p>
    </div>
  );
}
