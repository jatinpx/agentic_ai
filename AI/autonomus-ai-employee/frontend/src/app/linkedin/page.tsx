"use client";

import { useMemo, useState, useEffect } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { GlassCard } from "../components/GlassCard";
import { Header } from "../components/Header";
import { StatPill } from "../components/StatPill";
import { StatusStepper } from "../components/StatusStepper";
import { LiveStatusPanel } from "../components/LiveStatusPanel";
import { useLinkedInWebSocket } from "./useLinkedInWebSocket";

// ==========================================
// TYPES
// ==========================================

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

const API_BASE = "http://127.0.0.1:8000";

// ==========================================
// COMPONENT
// ==========================================

export default function LinkedInPage() {
  // --- Form State ---
  const [topic, setTopic] = useState("");
  const [tone, setTone] = useState("professional");
  const [audience, setAudience] = useState("tech professionals");
  const [goal, setGoal] = useState("engagement");
  const [includeEmojis, setIncludeEmojis] = useState(false);
  const [autoPublish, setAutoPublish] = useState(false);

  // --- Pipeline State ---
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

  // --- Edit Mode ---
  const [editMode, setEditMode] = useState(false);
  const [editedPost, setEditedPost] = useState("");

  // --- History ---
  const [history, setHistory] = useState<HistoryPost[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  // --- Auth ---
  const [linkedInAuth, setLinkedInAuth] = useState(false);

  // --- WebSocket for live pipeline status ---
  const { status: pipelineStatus, connect: connectWebSocket, disconnect: disconnectWebSocket } = useLinkedInWebSocket();

  const steps = ["Input", "Research", "Draft", "Review", "Publish"];

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

  // ==========================================
  // FETCH HISTORY
  // ==========================================
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
    } catch {
      setLinkedInAuth(false);
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

  const generatePost = async () => {
    if (!topic.trim()) return;

    setLoading(true);
    setStatusMessage("Starting LinkedIn pipeline...");
    setFinalPost(null);
    setHooks([]);
    setViralScore(0);
    setTrends("");
    setAwaitingApproval(false);
    setPublishUrl("");
    setIteration(0);
    setEditMode(false);
    setEditedPost("");

    try {
      const res = await fetch(`${API_BASE}/linkedin/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: topic.trim(),
          tone,
          audience,
          goal,
          include_emojis: includeEmojis,
          auto_publish: autoPublish,
        }),
      });

      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        const errorMsg = payload?.detail || "Post generation failed.";
        setStatusMessage(`❌ ${errorMsg}`);
        setLoading(false);
        return;
      }

      const data = await res.json();
      const newThreadId = data.thread_id;
      
      if (!newThreadId) {
        throw new Error("No thread_id received from backend");
      }

      setThreadId(newThreadId);
      setStatusMessage("Pipeline running - watch live status below");

      // Connect WebSocket for live updates
      connectWebSocket(newThreadId);

      // Keep loading state - will be cleared when pipeline completes or errors
    } catch (error) {
      const message = error instanceof Error ? error.message : "Post generation failed.";
      setStatusMessage(message);
      setLoading(false);
    }
  };

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
        setStatusMessage(data.publish_url ? "✅ Published to LinkedIn." : "✅ Workflow complete.");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Action failed.";
      
      // Make error messages more user-friendly
      let displayMessage = message;
      if (message.includes("Research quality score too low") || message.includes("Cannot publish")) {
        displayMessage = message; // Already user-friendly from backend
      } else if (message.includes("rejected_due_to_low_realism")) {
        displayMessage = "Cannot publish: Research quality score too low. Try regenerating or editing the topic.";
      }
      
      setStatusMessage(`❌ ${displayMessage}`);
    } finally {
      setLoading(false);
    }
  };

  const handleAbort = async () => {
    if (!threadId) {
      // No active pipeline, just reset UI
      disconnectWebSocket();
      setLoading(false);
      setStatusMessage("⚠️ No active pipeline to abort.");
      return;
    }

    try {
      // Call backend abort endpoint
      await fetch(`${API_BASE}/linkedin/abort`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ thread_id: threadId }),
      });
    } catch (error) {
      console.error("Abort request failed:", error);
    } finally {
      // Always clean up frontend state
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
    const handler = (event: MessageEvent) => {
      if (!event.data || event.data.type !== "linkedin-auth") return;
      if (event.data.status === "success") {
        setStatusMessage("✅ LinkedIn connected successfully.");
        checkAuthStatus();
        return;
      }
      setStatusMessage(`❌ ${event.data.message || "LinkedIn authentication failed."}`);
      setLinkedInAuth(false);
    };

    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  // Poll for final state when pipeline completes
  useEffect(() => {
    if (pipelineStatus.isComplete && threadId && !finalPost) {
      // First try to use final_post from WebSocket metadata
      const postData = pipelineStatus.metadata.final_post || pipelineStatus.metadata.generated_post;
      
      if (postData && typeof postData === "object" && "post" in postData && postData.post) {
        // We have the post data from WebSocket - use it directly
        setFinalPost(postData as PostOutput);
        const viralScoreValue = typeof pipelineStatus.metadata.viral_score === "number" 
          ? pipelineStatus.metadata.viral_score 
          : 0;
        setViralScore(viralScoreValue);
        
        // Extract hooks if available
        if (Array.isArray(pipelineStatus.metadata.hooks)) {
          setHooks(pipelineStatus.metadata.hooks);
        }
        
        setAwaitingApproval(true);
        setStatusMessage("✅ Draft ready for review.");
        setLoading(false);
        disconnectWebSocket();
        return;
      }
      
      // Pipeline completed - fetch final state from backend as fallback
      const fetchFinalState = async () => {
        try {
          const res = await fetch(`${API_BASE}/linkedin/status/${threadId}`);
          
          if (!res.ok) {
            console.error("Failed to fetch final state");
            setLoading(false);
            return;
          }

          const data = await res.json();
          
          // Use final_post from backend response
          if (data.final_post && typeof data.final_post === "object" && "post" in data.final_post && data.final_post.post) {
            setFinalPost(data.final_post as PostOutput);
            setViralScore(data.viral_score || 0);
            setAwaitingApproval(true);
            setStatusMessage("✅ Draft ready for review.");
          }
          
          setLoading(false);
          disconnectWebSocket();
        } catch (error) {
          console.error("Error fetching final state:", error);
          setLoading(false);
        }
      };

      fetchFinalState();
    }
  }, [pipelineStatus.isComplete, threadId, finalPost, pipelineStatus.metadata, disconnectWebSocket]);

  // Handle WebSocket errors
  useEffect(() => {
    if (pipelineStatus.error && loading) {
      setStatusMessage(`❌ Error: ${pipelineStatus.error}`);
      setLoading(false);
    }
  }, [pipelineStatus.error, loading]);

  // Auto-dismiss success messages after 5 seconds
  useEffect(() => {
    if (statusMessage.startsWith('✅')) {
      const timer = setTimeout(() => {
        setStatusMessage('');
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [statusMessage]);

  // Sync iteration count from WebSocket metadata
  useEffect(() => {
    const iterationFromSocket = pipelineStatus.metadata.iteration_count;
    if (typeof iterationFromSocket === "number" && iterationFromSocket !== iteration) {
      setIteration(iterationFromSocket);
    }
  }, [pipelineStatus.metadata.iteration_count, iteration]);

  return (
    <main className="app-shell">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <Header
          title="LinkedIn Content Agent"
          subtitle="Generate authority-first posts with research, verification, and human approval in one loop."
          actions={
            <div className="flex items-center gap-3">
              <motion.button
                onClick={() => {
                  setShowHistory(!showHistory);
                  if (!showHistory) fetchHistory();
                }}
                className="ghost-button text-xs"
                whileHover={{ scale: 1.05, y: -2 }}
                whileTap={{ scale: 0.95 }}
                transition={{ duration: 0.2 }}
              >
                {showHistory ? "Hide History" : "Show History"}
              </motion.button>
              {!linkedInAuth && (
                <motion.button
                  onClick={startLinkedInAuth}
                  className="primary-button text-xs"
                  whileHover={{ scale: 1.05, y: -2 }}
                  whileTap={{ scale: 0.95 }}
                  transition={{ duration: 0.2 }}
                >
                  Connect LinkedIn
                </motion.button>
              )}
              <Link href="/" className="ghost-button text-xs">
                Research Agent
              </Link>
            </div>
          }
        />

        <motion.div
          className="section-grid two-column"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <GlassCard className="p-6">
            <StatusStepper steps={steps} currentStep={currentStep} status={statusText} />
            <div className="mt-4 flex flex-wrap gap-3">
              <StatPill label="Viral Score" value={viralScore ? viralScore.toFixed(1) : "--"} />
              <StatPill label="Iteration" value={String(iteration)} />
              <StatPill label="Auth" value={linkedInAuth ? "Connected" : "Offline"} />
            </div>
          </GlassCard>

          <GlassCard className="p-6">
            <p className="eyebrow">Campaign Input</p>
            <h2 className="text-lg font-semibold">Define the brief</h2>
            <div className="mt-4 grid gap-4">
              <div className="grid gap-2">
                <label className="text-xs uppercase tracking-widest muted-text">Topic</label>
                <input
                  type="text"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="e.g., AI agents replacing SaaS tools"
                  className="glass-input"
                />
              </div>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="grid gap-2 min-w-0">
                  <label className="text-xs uppercase tracking-widest muted-text">Tone</label>
                  <select
                    value={tone}
                    onChange={(e) => setTone(e.target.value)}
                    className="glass-input w-full"
                  >
                    <option value="professional">Professional</option>
                    <option value="contrarian">Contrarian</option>
                    <option value="personal">Personal</option>
                    <option value="storytelling">Storytelling</option>
                  </select>
                </div>
                <div className="grid gap-2 min-w-0">
                  <label className="text-xs uppercase tracking-widest muted-text">Audience</label>
                  <input
                    type="text"
                    value={audience}
                    onChange={(e) => setAudience(e.target.value)}
                    placeholder="tech professionals"
                    className="glass-input w-full min-w-0 overflow-hidden text-ellipsis"
                  />
                </div>
                <div className="grid gap-2 min-w-0">
                  <label className="text-xs uppercase tracking-widest muted-text">Goal</label>
                  <select
                    value={goal}
                    onChange={(e) => setGoal(e.target.value)}
                    className="glass-input w-full"
                  >
                    <option value="engagement">Engagement</option>
                    <option value="authority">Authority</option>
                    <option value="leads">Lead Generation</option>
                    <option value="brand">Brand Awareness</option>
                  </select>
                </div>
                <div className="flex flex-col gap-3">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={includeEmojis}
                      onChange={(e) => setIncludeEmojis(e.target.checked)}
                    />
                    Include emojis
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={autoPublish}
                      onChange={(e) => setAutoPublish(e.target.checked)}
                    />
                    Auto publish
                  </label>
                </div>
              </div>
            </div>
            <motion.button
              onClick={generatePost}
              disabled={loading || !topic.trim()}
              className="primary-button w-full mt-6 disabled:opacity-50"
              whileHover={{ scale: 1.02, y: -2 }}
              whileTap={{ scale: 0.98 }}
              transition={{ duration: 0.2 }}
            >
              {loading ? "Generating..." : "Generate Post"}
            </motion.button>
            
            {/* Abort button shown during pipeline execution */}
            {loading && !awaitingApproval && (
              <motion.button
                onClick={handleAbort}
                className="ghost-button w-full mt-3 border-red-500/30 text-red-400 hover:border-red-500/50 hover:bg-red-500/10"
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                whileHover={{ scale: 1.02, y: -2 }}
                whileTap={{ scale: 0.98 }}
                transition={{ duration: 0.2 }}
              >
                ⏹️ Abort Pipeline
              </motion.button>
            )}
          </GlassCard>
        </motion.div>

        {/* Live Pipeline Status - Shown when WebSocket is active */}
        <LiveStatusPanel status={pipelineStatus} />

        <AnimatePresence mode="wait">
          {statusMessage && (
            <motion.div
              key="status"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.3 }}
            >
              <GlassCard 
                className={`p-4 relative ${
                  statusMessage.startsWith('❌') 
                    ? 'border-2 border-red-500/50 bg-red-500/5' 
                    : statusMessage.startsWith('✅') 
                      ? 'border-2 border-green-500/50 bg-green-500/5'
                      : ''
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="text-sm flex-1">
                    {statusMessage}
                    {publishUrl && (
                      <a
                        href={publishUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="ml-2 underline"
                      >
                        View on LinkedIn
                      </a>
                    )}
                  </div>
                  <motion.button
                    onClick={() => setStatusMessage('')}
                    className="text-xs opacity-60 hover:opacity-100 transition-opacity"
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.9 }}
                    aria-label="Dismiss"
                  >
                    ✕
                  </motion.button>
                </div>
              </GlassCard>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence mode="wait">
          {finalPost && (
            <motion.div
              key="post"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              transition={{ duration: 0.35 }}
              className="section-grid"
            >
              <GlassCard className="p-6">
                <p className="eyebrow">Hook</p>
                <h3 className="text-xl font-semibold">{finalPost.hook}</h3>
              </GlassCard>

              <GlassCard className="p-6">
                <p className="eyebrow">Post Preview</p>
                {!editMode ? (
                  <p className="whitespace-pre-wrap leading-relaxed text-sm">
                    {finalPost.post}
                  </p>
                ) : (
                  <textarea
                    className="glass-input w-full h-64"
                    value={editedPost}
                    onChange={(e) => setEditedPost(e.target.value)}
                  />
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

              <GlassCard className="p-6">
                <p className="eyebrow">CTA</p>
                <p className="text-sm">{finalPost.cta}</p>
              </GlassCard>

              {finalPost.hashtags && finalPost.hashtags.length > 0 && (
                <GlassCard className="p-6">
                  <p className="eyebrow">Hashtags</p>
                  <div className="flex flex-wrap gap-2">
                    {finalPost.hashtags.map((tag, i) => (
                      <span key={`${tag}-${i}`} className="status-pill">
                        #{tag.replace(/^#/, "")}
                      </span>
                    ))}
                  </div>
                </GlassCard>
              )}

              {finalPost.reasoning && (
                <GlassCard className="p-6">
                  <p className="eyebrow">Reasoning</p>
                  <p className="text-sm muted-text leading-relaxed">
                    {finalPost.reasoning}
                  </p>
                </GlassCard>
              )}

              {finalPost.score_breakdown && Object.keys(finalPost.score_breakdown).length > 0 && (
                <GlassCard className="p-6">
                  <p className="eyebrow">Score Breakdown</p>
                  <div className="mt-3 space-y-2">
                    {Object.entries(finalPost.score_breakdown).map(([key, value]) => (
                      <div key={key} className="flex justify-between text-sm">
                        <span className="muted-text capitalize">{key.replace(/_/g, ' ')}:</span>
                        <span className="font-medium">{typeof value === 'number' ? value.toFixed(1) : value}</span>
                      </div>
                    ))}
                  </div>
                </GlassCard>
              )}

              {hooks.length > 0 && (
                <GlassCard className="p-6">
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
                <GlassCard className="p-6">
                  <p className="eyebrow">Research Trends</p>
                  <div className="whitespace-pre-wrap text-sm muted-text">
                    {trends}
                  </div>
                </GlassCard>
              )}

              {awaitingApproval && (
                <div className="flex flex-wrap gap-3">
                  <motion.button
                    onClick={() => handleAction("approved")}
                    className="primary-button flex-1"
                    whileHover={{ scale: 1.02, y: -2 }}
                    whileTap={{ scale: 0.98 }}
                    transition={{ duration: 0.2 }}
                  >
                    Approve
                  </motion.button>
                  <motion.button
                    onClick={() => handleAction("regenerate")}
                    className="ghost-button flex-1"
                    whileHover={{ scale: 1.02, y: -2 }}
                    whileTap={{ scale: 0.98 }}
                    transition={{ duration: 0.2 }}
                  >
                    Regenerate
                  </motion.button>
                  <motion.button
                    onClick={() => handleAction("rejected")}
                    className="ghost-button flex-1"
                    whileHover={{ scale: 1.02, y: -2 }}
                    whileTap={{ scale: 0.98 }}
                    transition={{ duration: 0.2 }}
                  >
                    Reject
                  </motion.button>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence mode="wait">
          {showHistory && (
            <motion.div
              key="history"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              transition={{ duration: 0.3 }}
            >
              <GlassCard className="p-6">
                <div className="flex items-center justify-between">
                  <p className="eyebrow">Post History</p>
                  <motion.button
                    onClick={fetchHistory}
                    className="ghost-button text-xs"
                    whileHover={{ scale: 1.05, y: -2 }}
                    whileTap={{ scale: 0.95 }}
                    transition={{ duration: 0.2 }}
                  >
                    🔄 Refresh
                  </motion.button>
                </div>
                <div className="mt-4 space-y-3 max-h-[320px] overflow-y-auto">
                  {history.map((post) => (
                    <div key={post.id} className="glass-card p-4">
                      <p className="text-xs muted-text uppercase tracking-widest">
                        {post.topic}
                      </p>
                      <p className="text-sm mt-2 line-clamp-3">{post.content}</p>
                      <div className="mt-3 flex justify-between text-xs muted-text">
                        <span>{post.viral_score.toFixed(1)}/10</span>
                        <span>{post.status}</span>
                      </div>
                    </div>
                  ))}
                  {history.length === 0 && (
                    <p className="text-xs muted-text text-center py-4">
                      No posts yet
                    </p>
                  )}
                </div>
              </GlassCard>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </main>
  );
}
