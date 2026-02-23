"use client";

import { useMemo, useState, useEffect, useCallback } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { GlassCard } from "../components/GlassCard";
import { StatPill } from "../components/StatPill";
import { StatusStepper } from "../components/StatusStepper";
import { LiveStatusPanel } from "../components/LiveStatusPanel";
import { LinkedInConfigForm } from "../components/LinkedInConfigForm";
import { ThemeToggle } from "../components/ThemeToggle";
import { useLinkedInWebSocket } from "./useLinkedInWebSocket";

interface PostOutput {
  post_id?: string;
  hook: string;
  post: string;
  cta: string;
  hashtags: string[];
  viral_score_prediction: number;
  reasoning: string;
  tone?: string;
  audience?: string;
  topic?: string;
  status?: string;
  score_breakdown?: Record<string, number>;
}

interface Hook {
  type: string;
  text: string;
  strength_score: number;
}

interface HistoryPost {
  id: string;
  content: string;
  hook: string;
  viral_score: number;
  topic: string;
  status: string;
  created_at: string;
}

interface LinkedInAuthInfo {
  name?: string;
  email?: string;
  authorTarget?: unknown;
}

interface PipelineEventLike {
  type?: unknown;
  key?: unknown;
  value?: unknown;
  summary?: unknown;
  metadata?: Record<string, unknown>;
}

const API_BASE = "http://127.0.0.1:8000";

export default function LinkedInPage() {
  const [loading, setLoading] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [finalPost, setFinalPost] = useState<PostOutput | null>(null);
  const [hooks, setHooks] = useState<Hook[]>([]);
  const [viralScore, setViralScore] = useState(0);
  const [trends, setTrends] = useState("");
  const [awaitingApproval, setAwaitingApproval] = useState(false);
  const [publishUrl, setPublishUrl] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [iteration, setIteration] = useState(0);

  const [editMode, setEditMode] = useState(false);
  const [editedPost, setEditedPost] = useState("");

  const [history, setHistory] = useState<HistoryPost[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [selectedHistoryPost, setSelectedHistoryPost] = useState<HistoryPost | null>(null);
  const [historyPanelWidth, setHistoryPanelWidth] = useState(640);
  const [isResizingHistoryPanel, setIsResizingHistoryPanel] = useState(false);

  const [linkedInAuth, setLinkedInAuth] = useState(false);
  const [linkedInAuthInfo, setLinkedInAuthInfo] = useState<LinkedInAuthInfo | null>(null);

  const { status: pipelineStatus, connect: connectWebSocket, disconnect: disconnectWebSocket } = useLinkedInWebSocket();

  const steps = ["Input", "Research", "Draft", "Review", "Publish"];

  const formatAuthorTarget = (target: unknown): string => {
    if (!target) return "";
    if (typeof target === "string") return target;
    if (typeof target === "object") {
      try {
        return JSON.stringify(target);
      } catch {
        return "[configured]";
      }
    }
    return String(target);
  };

  const parseIterationNumber = (value: unknown): number | null => {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string") {
      const parsed = Number(value);
      if (!Number.isNaN(parsed)) return parsed;
    }
    return null;
  };

  const getIterationFromPipeline = (): number | null => {
    const metadata = pipelineStatus.metadata || {};
    const directCandidates = [
      metadata.iteration_count,
      metadata.iteration,
      metadata.iterationCount,
      metadata.current_iteration,
    ];

    for (const candidate of directCandidates) {
      const parsed = parseIterationNumber(candidate);
      if (parsed !== null) return parsed;
    }

    const events = pipelineStatus.events as PipelineEventLike[];
    for (let i = events.length - 1; i >= 0; i -= 1) {
      const event = events[i];
      if (!event) continue;

      if (event.type === "state_update") {
        if (typeof event.key === "string" && event.key.includes("iteration")) {
          const parsed = parseIterationNumber(event.value);
          if (parsed !== null) return parsed;
        }
        if (typeof event.summary === "string") {
          const match = event.summary.match(/iter(?:ation)?\s*(\d+)/i);
          if (match) return Number(match[1]);
        }
      }

      if (event.metadata) {
        const parsed =
          parseIterationNumber(event.metadata.iteration_count) ??
          parseIterationNumber(event.metadata.iteration) ??
          parseIterationNumber(event.metadata.iterationCount);
        if (parsed !== null) return parsed;
      }
    }

    return null;
  };

  const currentStep = useMemo(() => {
    if (publishUrl) return 4;
    if (awaitingApproval) return 3;
    if (finalPost) return 2;
    if (loading) return 1;
    return 0;
  }, [awaitingApproval, finalPost, loading, publishUrl]);

  const statusText = useMemo(() => {
    if (loading) return "Researching";
    if (awaitingApproval) return "Awaiting approval";
    if (publishUrl) return "Published";
    if (finalPost) return "Draft ready";
    return "Standing by";
  }, [awaitingApproval, finalPost, loading, publishUrl]);

  const fetchHistory = async () => {
    try {
      const res = await fetch(`${API_BASE}/linkedin/posts?limit=20`);
      const data = await res.json();
      setHistory(data.posts || []);
    } catch {
      console.error("Failed to fetch history");
    }
  };

  const checkAuthStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/linkedin/auth/status`, { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      setLinkedInAuth(Boolean(data.authenticated));
      if (data.authenticated) {
        setLinkedInAuthInfo({
          name: data?.profile?.name || "",
          email: data?.profile?.email || "",
          authorTarget: data?.author_target || "",
        });
      } else {
        setLinkedInAuthInfo(null);
      }
    } catch {
      setLinkedInAuth(false);
      setLinkedInAuthInfo(null);
    }
  };

  const startLinkedInAuth = async () => {
    setStatusMessage("Opening LinkedIn authentication...");
    try {
      const res = await fetch(`${API_BASE}/linkedin/auth/url`, { cache: "no-store" });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload?.detail || "Failed to get LinkedIn auth URL.");
      }

      const data = await res.json();
      const popup = window.open(data.auth_url, "linkedin-auth", "width=520,height=640");
      if (!popup) {
        setStatusMessage("Popup blocked. Allow popups to connect LinkedIn.");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "LinkedIn auth failed.";
      setStatusMessage(`❌ ${message}`);
    }
  };

  const handlePostGenerated = useCallback((newThreadId: string) => {
    setLoading(true);
    setFinalPost(null);
    setHooks([]);
    setViralScore(0);
    setTrends("");
    setAwaitingApproval(false);
    setPublishUrl("");
    setIteration(0);
    setEditMode(false);
    setEditedPost("");

    setThreadId(newThreadId);
    setStatusMessage("Pipeline running - watch live status below");
    connectWebSocket(newThreadId);
  }, [connectWebSocket]);

  const handleConfigFormError = useCallback((error: string) => {
    setStatusMessage(`❌ ${error}`);
  }, []);

  const handleAction = async (action: "approved" | "regenerate" | "rejected") => {
    if (!threadId) return;

    setLoading(true);
    setStatusMessage(
      action === "approved"
        ? "Approving draft..."
        : action === "regenerate"
          ? "Regenerating draft..."
          : "Rejecting draft..."
    );

    try {
      const res = await fetch(`${API_BASE}/linkedin/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          thread_id: threadId,
          action,
          edited_post: editMode ? editedPost : undefined,
        }),
      });

      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload?.detail || "Approval action failed.");
      }

      const data = await res.json();
      if (data.status === "awaiting_approval") {
        setFinalPost(data.final_post || null);
        setHooks(data.hooks || []);
        setViralScore(data.viral_score || 0);
        setIteration(data.iteration || 0);
        setAwaitingApproval(true);
        setPublishUrl("");
        setEditMode(false);
        setEditedPost(data.final_post?.post || "");
        setStatusMessage("✅ New draft ready for review.");
      } else {
        setAwaitingApproval(false);
        setPublishUrl(data.publish_url || "");
        setFinalPost(data.final_post || finalPost);
        if (data.status === "publish_failed" || data.status === "approved_not_published") {
          setStatusMessage(`⚠️ ${data.message || data.error || "Post approved, but publishing failed."}`);
        } else {
          setStatusMessage(data.publish_url ? "✅ Published to LinkedIn." : "✅ Workflow complete.");
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Action failed.";
      let displayMessage = message;
      if (message.includes("rejected_due_to_low_realism")) {
        displayMessage = "Cannot publish: Research quality score too low. Try regenerating or editing the topic.";
      }
      setStatusMessage(`❌ ${displayMessage}`);
    } finally {
      setLoading(false);
    }
  };

  const handleAbort = async () => {
    if (!threadId) {
      disconnectWebSocket();
      setLoading(false);
      setStatusMessage("⚠️ No active pipeline to abort.");
      return;
    }

    try {
      await fetch(`${API_BASE}/linkedin/abort`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ thread_id: threadId }),
      });
    } catch (error) {
      console.error("Abort request failed:", error);
    } finally {
      disconnectWebSocket();
      setLoading(false);
      setAwaitingApproval(false);
      setFinalPost(null);
      setThreadId(null);
      setStatusMessage("⚠️ Pipeline aborted. You can start a new generation.");
    }
  };

  useEffect(() => {
    checkAuthStatus();
  }, []);

  useEffect(() => {
    if (!isResizingHistoryPanel) return;

    const onMouseMove = (event: MouseEvent) => {
      const minWidth = 420;
      const maxWidth = Math.max(minWidth, window.innerWidth - 24);
      const nextWidth = window.innerWidth - event.clientX;
      setHistoryPanelWidth(Math.min(maxWidth, Math.max(minWidth, nextWidth)));
    };

    const onMouseUp = () => {
      setIsResizingHistoryPanel(false);
    };

    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);

    return () => {
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [isResizingHistoryPanel]);

  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (!event.data || event.data.type !== "linkedin-auth") return;
      if (event.data.status === "success") {
        setStatusMessage("✅ LinkedIn connected successfully.");
        checkAuthStatus();
        return;
      }
      setStatusMessage(`❌ ${event.data.message || "LinkedIn authentication failed."}`);
      setLinkedInAuth(false);
      setLinkedInAuthInfo(null);
    };

    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  useEffect(() => {
    if (pipelineStatus.isComplete && threadId && !finalPost) {
      const postData = pipelineStatus.metadata.final_post || pipelineStatus.metadata.generated_post;

      if (postData && typeof postData === "object" && "post" in postData && postData.post) {
        setFinalPost(postData as unknown as PostOutput);
        const viralScoreValue = typeof pipelineStatus.metadata.viral_score === "number" ? pipelineStatus.metadata.viral_score : 0;
        setViralScore(viralScoreValue);
        if (Array.isArray(pipelineStatus.metadata.hooks)) {
          setHooks(pipelineStatus.metadata.hooks as Hook[]);
        }
        setAwaitingApproval(true);
        setStatusMessage("✅ Draft ready for review.");
        setLoading(false);
        disconnectWebSocket();
        return;
      }

      const fetchFinalState = async () => {
        try {
          const res = await fetch(`${API_BASE}/linkedin/status/${threadId}`);
          if (!res.ok) {
            setLoading(false);
            return;
          }

          const data = await res.json();
          if (data.final_post && typeof data.final_post === "object" && "post" in data.final_post && data.final_post.post) {
            setFinalPost(data.final_post as PostOutput);
            setViralScore(data.viral_score || 0);
            setIteration(data.iteration_count || 0);
            setAwaitingApproval(true);
            setStatusMessage("✅ Draft ready for review.");
          }

          setLoading(false);
          disconnectWebSocket();
        } catch {
          setLoading(false);
        }
      };

      fetchFinalState();
    }
  }, [pipelineStatus.isComplete, threadId, finalPost, pipelineStatus.metadata, disconnectWebSocket]);

  useEffect(() => {
    if (pipelineStatus.error && loading) {
      setStatusMessage(`❌ Error: ${pipelineStatus.error}`);
      setLoading(false);
    }
  }, [pipelineStatus.error, loading]);

  useEffect(() => {
    if (statusMessage.startsWith("✅")) {
      const timer = setTimeout(() => {
        setStatusMessage("");
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [statusMessage]);

  useEffect(() => {
    const nextIteration = getIterationFromPipeline();
    if (nextIteration !== null && nextIteration !== iteration) {
      setIteration(nextIteration);
    }
  }, [pipelineStatus.metadata, pipelineStatus.events, iteration]);

  useEffect(() => {
    if (!selectedHistoryPost) return;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, [selectedHistoryPost]);

  const shouldShowPipelinePanel =
    loading ||
    pipelineStatus.isRunning ||
    pipelineStatus.isComplete ||
    Boolean(threadId) ||
    awaitingApproval ||
    Boolean(finalPost);
  const shouldLiftPipeline = loading || pipelineStatus.isRunning;

  const pipelineCard = (
    <GlassCard className="p-5">
      <StatusStepper steps={steps} currentStep={currentStep} status={statusText} />
      <div className="mt-4 flex flex-wrap gap-3">
      </div>

      <LiveStatusPanel status={pipelineStatus} embedded className="mt-4" />

      {loading && !awaitingApproval && (
        <motion.button
          onClick={handleAbort}
          className="ghost-button mt-4 w-full border-red-500/30 text-red-400 hover:border-red-500/50 hover:bg-red-500/10"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          whileHover={{ scale: 1.01, y: -1 }}
          whileTap={{ scale: 0.99 }}
          transition={{ duration: 0.2 }}
        >
          ⏹️ Abort Pipeline
        </motion.button>
      )}
    </GlassCard>
  );

  return (
    <main>
      <motion.nav
        className="top-nav"
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <div className="top-nav__brand">
          <span className="eyebrow !mb-0">Autonomous Suite</span>
          <strong>LinkedIn Content Agent</strong>
        </div>

        <div className="top-nav__actions">
          <ThemeToggle />

          {!linkedInAuth ? (
            <motion.button
              onClick={startLinkedInAuth}
              className="primary-button text-xs"
              whileHover={{ scale: 1.04, y: -1 }}
              whileTap={{ scale: 0.96 }}
              transition={{ duration: 0.2 }}
            >
              Connect LinkedIn
            </motion.button>
          ) : (
            <div className="group relative">
              <div className="status-pill cursor-default !text-sm">LinkedIn Connected <span className="ml-1 text-green-400">●</span></div>
              {(linkedInAuthInfo?.name || linkedInAuthInfo?.email || Boolean(linkedInAuthInfo?.authorTarget)) && (
                <div className="pointer-events-none absolute right-0 top-[calc(100%+8px)] z-20 hidden min-w-[260px] rounded-xl border border-[var(--glass-border)] bg-[var(--surface-strong)] p-3 text-xs shadow-lg group-hover:block">
                  <p className="mb-1 text-[10px] uppercase tracking-wider muted-text">Account</p>
                  {linkedInAuthInfo?.name && <p className="mb-1">Name: {linkedInAuthInfo.name}</p>}
                  {linkedInAuthInfo?.email && <p className="mb-1 break-all">Email: {linkedInAuthInfo.email}</p>}
                  {Boolean(linkedInAuthInfo?.authorTarget) && <p className="break-all muted-text">Target: {formatAuthorTarget(linkedInAuthInfo?.authorTarget)}</p>}
                </div>
              )}
            </div>
          )}

          <motion.button
            onClick={() => {
              setShowHistory(!showHistory);
              if (!showHistory) fetchHistory();
            }}
            className="ghost-button text-xs"
            whileHover={{ scale: 1.04, y: -1 }}
            whileTap={{ scale: 0.96 }}
            transition={{ duration: 0.2 }}
          >
            {showHistory ? "Hide History" : "Show History"}
          </motion.button>
        </div>
      </motion.nav>

      <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 py-5 px-4">
        <motion.section
          className="hero-panel"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.32, delay: 0.04 }}
        >
          <h2 className="display-text !text-[clamp(1.7rem,1.9vw+0.9rem,2.3rem)]">Enterprise Content Workflow</h2>
          <p className="header-subtitle">
            Generate authority-first LinkedIn posts with verifiable research, guided approvals, and production-ready control.
          </p>
        </motion.section>

        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
          <LinkedInConfigForm
            baseUrl={API_BASE}
            onPostGenerated={handlePostGenerated}
            onError={handleConfigFormError}
            minimized={loading || pipelineStatus.isRunning}
          />
        </motion.div>

        {shouldShowPipelinePanel && shouldLiftPipeline && pipelineCard}

        <AnimatePresence mode="wait">
          {statusMessage && (
            <motion.div key="status" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }} transition={{ duration: 0.3 }}>
              <GlassCard className={`p-4 ${statusMessage.startsWith("❌") ? "border-2 border-red-500/50 bg-red-500/5" : statusMessage.startsWith("✅") ? "border-2 border-green-500/50 bg-green-500/5" : ""}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="text-sm flex-1">
                    {statusMessage}
                    {publishUrl && (
                      <a href={publishUrl} target="_blank" rel="noopener noreferrer" className="ml-2 underline">
                        View on LinkedIn
                      </a>
                    )}
                  </div>
                  <motion.button onClick={() => setStatusMessage("")} className="text-xs opacity-60 hover:opacity-100 transition-opacity" whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }} aria-label="Dismiss">
                    ✕
                  </motion.button>
                </div>
              </GlassCard>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence mode="wait">
          {finalPost && (
            <motion.div key="post" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }} transition={{ duration: 0.35 }} className="section-grid">
              <GlassCard className="p-5">
                <p className="eyebrow">Hook</p>
                <h3 className="text-xl font-semibold">{finalPost.hook}</h3>
              </GlassCard>

              <GlassCard className="p-5">
                <p className="eyebrow">Post Preview</p>
                {!editMode ? (
                  <p className="whitespace-pre-wrap leading-relaxed text-sm">{finalPost.post}</p>
                ) : (
                  <textarea className="glass-input w-full h-64" value={editedPost} onChange={(e) => setEditedPost(e.target.value)} />
                )}
                <motion.button
                  onClick={() => {
                    setEditMode(!editMode);
                    setEditedPost(finalPost.post);
                  }}
                  className="ghost-button text-xs mt-4"
                  whileHover={{ scale: 1.05, y: -2 }}
                  whileTap={{ scale: 0.95 }}
                  transition={{ duration: 0.2 }}
                >
                  {editMode ? "Cancel Edit" : "Edit Post"}
                </motion.button>
              </GlassCard>

              <GlassCard className="p-5">
                <p className="eyebrow">CTA</p>
                <p className="text-sm">{finalPost.cta}</p>
              </GlassCard>

              {finalPost.hashtags && finalPost.hashtags.length > 0 && (
                <GlassCard className="p-5">
                  <p className="eyebrow">Hashtags</p>
                  <div className="flex flex-wrap gap-2">
                    {finalPost.hashtags.map((tag, i) => (
                      <span key={`${tag}-${i}`} className="status-pill">#{tag.replace(/^#/, "")}</span>
                    ))}
                  </div>
                </GlassCard>
              )}

              {finalPost.reasoning && (
                <GlassCard className="p-5">
                  <p className="eyebrow">Reasoning</p>
                  <p className="text-sm muted-text leading-relaxed">{finalPost.reasoning}</p>
                </GlassCard>
              )}

              {finalPost.score_breakdown && Object.keys(finalPost.score_breakdown).length > 0 && (
                <GlassCard className="p-5">
                  <p className="eyebrow">Score Breakdown</p>
                  <div className="mt-3 space-y-2">
                    {Object.entries(finalPost.score_breakdown).map(([key, value]) => (
                      <div key={key} className="flex justify-between text-sm">
                        <span className="muted-text capitalize">{key.replace(/_/g, " ")}:</span>
                        <span className="font-medium">{typeof value === "number" ? value.toFixed(1) : value}</span>
                      </div>
                    ))}
                  </div>
                </GlassCard>
              )}

              {hooks.length > 0 && (
                <GlassCard className="p-5">
                  <p className="eyebrow">Generated Hooks</p>
                  <div className="mt-3 space-y-2 text-sm">
                    {hooks.map((hook, i) => (
                      <div key={i}>
                        <span className="muted-text">{hook.type}:</span> {hook.text}
                      </div>
                    ))}
                  </div>
                </GlassCard>
              )}

              {trends && (
                <GlassCard className="p-5">
                  <p className="eyebrow">Research Trends</p>
                  <div className="whitespace-pre-wrap text-sm muted-text">{trends}</div>
                </GlassCard>
              )}

              {awaitingApproval && (
                <div className="flex flex-wrap gap-3">
                  <motion.button onClick={() => handleAction("approved")} className="primary-button flex-1" whileHover={{ scale: 1.02, y: -2 }} whileTap={{ scale: 0.98 }} transition={{ duration: 0.2 }}>
                    Approve
                  </motion.button>
                  <motion.button onClick={() => handleAction("regenerate")} className="ghost-button flex-1" whileHover={{ scale: 1.02, y: -2 }} whileTap={{ scale: 0.98 }} transition={{ duration: 0.2 }}>
                    Regenerate
                  </motion.button>
                  <motion.button onClick={() => handleAction("rejected")} className="ghost-button flex-1" whileHover={{ scale: 1.02, y: -2 }} whileTap={{ scale: 0.98 }} transition={{ duration: 0.2 }}>
                    Reject
                  </motion.button>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {shouldShowPipelinePanel && !shouldLiftPipeline && pipelineCard}

        <AnimatePresence mode="wait">
          {showHistory && (
            <motion.div key="history" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }} transition={{ duration: 0.3 }}>
              <GlassCard className="p-5">
                <div className="flex items-center justify-between">
                  <p className="eyebrow">Post History</p>
                  <motion.button onClick={fetchHistory} className="ghost-button text-xs" whileHover={{ scale: 1.05, y: -2 }} whileTap={{ scale: 0.95 }} transition={{ duration: 0.2 }}>
                    🔄 Refresh
                  </motion.button>
                </div>
                <div className="mt-4 space-y-3 max-h-[320px] overflow-y-auto">
                  {history.map((post) => (
                    <button
                      key={post.id}
                      type="button"
                      onClick={() => setSelectedHistoryPost(post)}
                      className="glass-card w-full p-4 text-left transition-transform hover:-translate-y-0.5"
                    >
                      <p className="text-xs muted-text uppercase tracking-widest">{post.topic}</p>
                      <p className="text-sm mt-2 line-clamp-3">{post.content}</p>
                      <div className="mt-3 flex justify-between text-xs muted-text">
                        <span>{post.viral_score.toFixed(1)}/10</span>
                        <span>{post.status}</span>
                      </div>
                    </button>
                  ))}
                  {history.length === 0 && <p className="text-xs muted-text text-center py-4">No posts yet</p>}
                </div>
              </GlassCard>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {selectedHistoryPost && (
            <motion.div className="fixed inset-x-0 bottom-0 top-[4.5rem] z-50 flex justify-end bg-black/35" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setSelectedHistoryPost(null)}>
              <motion.aside
                className="relative h-full rounded-none border-l border-[var(--glass-border)] bg-[var(--background)] p-6 shadow-2xl"
                style={{ width: `${historyPanelWidth}px`, maxWidth: "100vw" }}
                initial={{ x: 460 }}
                animate={{ x: 0 }}
                exit={{ x: 460 }}
                transition={{ type: "spring", stiffness: 260, damping: 28 }}
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  type="button"
                  className="absolute left-0 top-0 h-full w-2 -translate-x-1/2 cursor-col-resize"
                  aria-label="Resize history panel"
                  onMouseDown={(event) => {
                    event.preventDefault();
                    setIsResizingHistoryPanel(true);
                  }}
                />
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div>
                    <p className="eyebrow">History Detail</p>
                    <h3 className="text-lg font-semibold">{selectedHistoryPost.topic}</h3>
                  </div>
                  <button type="button" onClick={() => setSelectedHistoryPost(null)} className="ghost-button px-3 py-1.5 text-xs">
                    Close
                  </button>
                </div>

                <div className="h-[calc(100%-5.5rem)] overflow-y-auto pr-1">
                  <div className="mb-4 flex flex-wrap gap-2 text-xs">
                    <span className="status-pill">Score: {selectedHistoryPost.viral_score.toFixed(1)}/10</span>
                    <span className="status-pill">Status: {selectedHistoryPost.status}</span>
                    <span className="status-pill">{new Date(selectedHistoryPost.created_at).toLocaleString()}</span>
                  </div>

                  <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--surface-strong)] p-4">
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">{selectedHistoryPost.content}</p>
                  </div>
                </div>
              </motion.aside>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </main>
  );
}
