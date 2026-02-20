"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

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
  const [selectedHook, setSelectedHook] = useState("");
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

  // ==========================================
  // CHECK AUTH
  // ==========================================
  const checkAuth = async () => {
    try {
      const res = await fetch(`${API_BASE}/linkedin/auth/status`);
      const data = await res.json();
      setLinkedInAuth(data.authenticated || false);
    } catch {
      setLinkedInAuth(false);
    }
  };

  useEffect(() => {
    checkAuth();
  }, []);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      if (!event.data || event.data.type !== "linkedin-auth") return;

      if (event.data.status === "success") {
        setStatusMessage("LinkedIn connected successfully.");
        checkAuth();
      } else {
        setStatusMessage(event.data.message || "LinkedIn authentication failed.");
      }
    };

    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  // ==========================================
  // GENERATE POST
  // ==========================================
  const generatePost = async () => {
    if (!topic.trim()) return;
    setLoading(true);
    setFinalPost(null);
    setHooks([]);
    setPublishUrl("");
    setStatusMessage("");
    setEditMode(false);
    setIteration(0);

    try {
      const res = await fetch(`${API_BASE}/linkedin/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic,
          tone,
          audience,
          goal,
          include_emojis: includeEmojis,
          auto_publish: autoPublish,
        }),
      });
      const data = await res.json();

      if (!res.ok) {
        setStatusMessage(`Error: ${data.detail || "Generation failed"}`);
        return;
      }

      setThreadId(data.thread_id);
      setFinalPost(data.final_post);
      setHooks(data.hooks || []);
      setSelectedHook(data.selected_hook || "");
      setViralScore(data.viral_score || 0);
      setTrends(data.trends || "");
      setAwaitingApproval(true);
      setStatusMessage("Post generated. Review and approve below.");
    } catch {
      setStatusMessage("Error connecting to backend");
    } finally {
      setLoading(false);
    }
  };

  // ==========================================
  // APPROVE / REGENERATE / REJECT
  // ==========================================
  const handleAction = async (action: "approved" | "regenerate" | "rejected") => {
    if (!threadId) return;
    setLoading(true);
    setStatusMessage("");

    try {
      const body: Record<string, unknown> = {
        thread_id: threadId,
        action,
      };
      if (editMode && editedPost) {
        body.edited_post = editedPost;
      }

      const res = await fetch(`${API_BASE}/linkedin/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();

      if (data.status === "awaiting_approval") {
        setFinalPost(data.final_post);
        setHooks(data.hooks || hooks);
        setSelectedHook(data.selected_hook || selectedHook);
        setViralScore(data.viral_score || 0);
        setIteration(data.iteration || 0);
        setAwaitingApproval(true);
        setEditMode(false);
        setStatusMessage("New version generated. Review below.");
      } else {
        setFinalPost(data.final_post);
        setPublishUrl(data.publish_url || "");
        setViralScore(data.viral_score || viralScore);
        setAwaitingApproval(false);
        setEditMode(false);

        if (data.publish_url) {
          setStatusMessage("Published to LinkedIn!");
        } else if (data.status === "approved_not_published") {
          setStatusMessage("Approved. Connect LinkedIn to publish.");
        } else if (data.status === "rejected") {
          setStatusMessage("Post rejected.");
        } else {
          setStatusMessage(`Status: ${data.status}`);
        }
        fetchHistory();
      }
    } catch {
      setStatusMessage("Action failed. Try again.");
    } finally {
      setLoading(false);
    }
  };

  // ==========================================
  // LINKEDIN AUTH
  // ==========================================
  const startLinkedInAuth = async () => {
    try {
      const res = await fetch(`${API_BASE}/linkedin/auth/url`);
      const data = await res.json();
      if (data.auth_url) {
        const popup = window.open(data.auth_url, "_blank", "width=600,height=700");
        if (!popup) {
          setStatusMessage("Popup blocked. Please allow popups and try again.");
          return;
        }

        setStatusMessage("Complete LinkedIn login in the popup window...");

        const poll = window.setInterval(() => {
          if (popup.closed) {
            window.clearInterval(poll);
            checkAuth();
          }
        }, 1000);
      }
    } catch {
      setStatusMessage("Failed to get auth URL");
    }
  };

  // ==========================================
  // SCORE COLOR
  // ==========================================
  const scoreColor = (score: number) => {
    if (score >= 7) return "text-green-400";
    if (score >= 4) return "text-yellow-400";
    return "text-red-400";
  };

  const scoreBg = (score: number) => {
    if (score >= 7) return "bg-green-900/30 border-green-700";
    if (score >= 4) return "bg-yellow-900/30 border-yellow-700";
    return "bg-red-900/30 border-red-700";
  };

  // ==========================================
  // RENDER
  // ==========================================
  return (
    <main className="min-h-screen bg-[#0a0a0a] text-gray-100 flex font-mono">
      {/* ========== SIDEBAR: POST HISTORY ========== */}
      <aside
        className={`${
          showHistory ? "w-80" : "w-0"
        } transition-all duration-300 overflow-hidden border-r border-gray-800 bg-[#0f0f0f]`}
      >
        <div className="p-4 w-80">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider">
              Post History
            </h2>
            <button
              onClick={() => setShowHistory(false)}
              className="text-gray-500 hover:text-gray-300 text-lg"
            >
              &times;
            </button>
          </div>
          <button
            onClick={fetchHistory}
            className="w-full mb-4 px-3 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 rounded transition"
          >
            Refresh
          </button>
          <div className="space-y-3 max-h-[calc(100vh-140px)] overflow-y-auto">
            {history.map((post) => (
              <div
                key={post.id}
                className="p-3 bg-gray-900 rounded border border-gray-800 hover:border-gray-600 transition cursor-pointer"
              >
                <div className="flex justify-between items-start mb-1">
                  <span className="text-xs text-gray-500">{post.topic}</span>
                  <span
                    className={`text-xs font-bold ${scoreColor(post.viral_score)}`}
                  >
                    {post.viral_score.toFixed(1)}
                  </span>
                </div>
                <p className="text-xs text-gray-300 line-clamp-3">
                  {post.hook || post.content?.slice(0, 100)}
                </p>
                <div className="flex justify-between mt-2">
                  <span className="text-[10px] text-gray-600">
                    {post.created_at?.slice(0, 10)}
                  </span>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded ${
                      post.status === "published"
                        ? "bg-green-900/50 text-green-400"
                        : post.status === "approved"
                        ? "bg-blue-900/50 text-blue-400"
                        : "bg-gray-800 text-gray-500"
                    }`}
                  >
                    {post.status}
                  </span>
                </div>
              </div>
            ))}
            {history.length === 0 && (
              <p className="text-xs text-gray-600 text-center py-4">
                No posts yet
              </p>
            )}
          </div>
        </div>
      </aside>

      {/* ========== MAIN CONTENT ========== */}
      <div className="flex-1 flex flex-col items-center p-6 md:p-12 max-w-4xl mx-auto w-full">
        {/* HEADER */}
        <div className="w-full flex justify-between items-center mb-8 border-b border-gray-800 pb-4">
          <div className="flex items-center gap-4">
            <button
              onClick={() => {
                setShowHistory(!showHistory);
                if (!showHistory) fetchHistory();
              }}
              className="text-gray-500 hover:text-gray-300 text-sm"
            >
              {showHistory ? "Hide" : "History"}
            </button>
            <h1 className="text-2xl font-bold">
              <span className="text-blue-500">LINKEDIN</span> CONTENT AGENT
            </h1>
          </div>
          <div className="flex gap-3 items-center">
            <div
              className={`w-2 h-2 rounded-full ${
                linkedInAuth ? "bg-green-500" : "bg-red-500"
              }`}
              title={linkedInAuth ? "LinkedIn Connected" : "LinkedIn Not Connected"}
            />
            {!linkedInAuth && (
              <button
                onClick={startLinkedInAuth}
                className="text-xs px-3 py-1.5 bg-blue-700 hover:bg-blue-600 rounded transition"
              >
                Connect LinkedIn
              </button>
            )}
            <Link
              href="/"
              className="text-xs text-gray-500 hover:text-gray-300 transition"
            >
              Research Agent
            </Link>
          </div>
        </div>

        {/* ========== INPUT FORM ========== */}
        <div className="w-full bg-gray-900/50 border border-gray-800 rounded-lg p-6 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            {/* Topic */}
            <div className="md:col-span-2">
              <label className="text-xs text-gray-500 uppercase tracking-wider mb-1 block">
                Topic / Idea
              </label>
              <input
                type="text"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="e.g., AI agents replacing SaaS tools"
                className="w-full bg-gray-800 border border-gray-700 rounded px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition placeholder-gray-600"
              />
            </div>

            {/* Tone */}
            <div>
              <label className="text-xs text-gray-500 uppercase tracking-wider mb-1 block">
                Tone
              </label>
              <select
                value={tone}
                onChange={(e) => setTone(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition"
              >
                <option value="professional">Professional</option>
                <option value="casual">Casual</option>
                <option value="contrarian">Contrarian</option>
                <option value="storytelling">Storytelling</option>
                <option value="debate">Debate-Sparking</option>
              </select>
            </div>

            {/* Audience */}
            <div>
              <label className="text-xs text-gray-500 uppercase tracking-wider mb-1 block">
                Audience
              </label>
              <input
                type="text"
                value={audience}
                onChange={(e) => setAudience(e.target.value)}
                placeholder="tech professionals"
                className="w-full bg-gray-800 border border-gray-700 rounded px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition placeholder-gray-600"
              />
            </div>

            {/* Goal */}
            <div>
              <label className="text-xs text-gray-500 uppercase tracking-wider mb-1 block">
                Goal
              </label>
              <select
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition"
              >
                <option value="engagement">Engagement</option>
                <option value="authority">Authority</option>
                <option value="leads">Leads</option>
                <option value="awareness">Awareness</option>
              </select>
            </div>

            {/* Toggles */}
            <div className="flex items-center gap-6">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeEmojis}
                  onChange={(e) => setIncludeEmojis(e.target.checked)}
                  className="accent-blue-500"
                />
                <span className="text-xs text-gray-400">Include Emojis</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoPublish}
                  onChange={(e) => setAutoPublish(e.target.checked)}
                  className="accent-blue-500"
                />
                <span className="text-xs text-gray-400">Auto-Publish</span>
              </label>
            </div>
          </div>

          <button
            onClick={generatePost}
            disabled={loading || !topic.trim()}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-bold py-3 rounded transition text-sm uppercase tracking-wider"
          >
            {loading ? "GENERATING..." : "GENERATE POST"}
          </button>
        </div>

        {/* ========== STATUS ========== */}
        {statusMessage && (
          <div className="w-full mb-4 px-4 py-2 bg-gray-900 border border-gray-700 rounded text-sm text-gray-300">
            {statusMessage}
            {publishUrl && (
              <a
                href={publishUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="ml-2 text-blue-400 hover:text-blue-300 underline"
              >
                View on LinkedIn
              </a>
            )}
          </div>
        )}

        {/* ========== LOADING ========== */}
        {loading && (
          <div className="w-full mb-6 flex items-center justify-center gap-2 py-8">
            <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
            <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse delay-100" />
            <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse delay-200" />
            <span className="text-sm text-gray-500 ml-2">
              Running pipeline (this may take 30-60s)...
            </span>
          </div>
        )}

        {/* ========== POST PREVIEW ========== */}
        {finalPost && (
          <div className="w-full space-y-4">
            {/* Viral Score Badge */}
            <div
              className={`flex items-center justify-between p-4 rounded-lg border ${scoreBg(
                viralScore
              )}`}
            >
              <div>
                <span className="text-xs text-gray-400 uppercase tracking-wider">
                  Viral Score
                </span>
                <div className={`text-3xl font-bold ${scoreColor(viralScore)}`}>
                  {viralScore.toFixed(1)}
                  <span className="text-sm text-gray-500">/10</span>
                </div>
              </div>
              {finalPost.score_breakdown && (
                <div className="grid grid-cols-5 gap-2 text-center">
                  {Object.entries(finalPost.score_breakdown).map(
                    ([key, val]) => (
                      <div key={key}>
                        <div className="text-[10px] text-gray-500 capitalize">
                          {key.replace("_", " ")}
                        </div>
                        <div className={`text-sm font-bold ${scoreColor(val * 5)}`}>
                          {(val as number).toFixed(1)}
                        </div>
                      </div>
                    )
                  )}
                </div>
              )}
              {iteration > 0 && (
                <span className="text-xs text-gray-500">
                  Iteration #{iteration + 1}
                </span>
              )}
            </div>

            {/* Hook */}
            <div className="p-4 bg-gray-900 border border-gray-800 rounded-lg">
              <div className="text-xs text-blue-400 uppercase tracking-wider mb-2">
                Hook
              </div>
              <p className="text-lg font-semibold leading-relaxed whitespace-pre-wrap">
                {finalPost.hook}
              </p>
            </div>

            {/* Full Post Preview */}
            <div className="p-6 bg-gray-900 border border-gray-800 rounded-lg">
              <div className="flex justify-between items-center mb-3">
                <span className="text-xs text-gray-400 uppercase tracking-wider">
                  Full Post
                </span>
                {awaitingApproval && (
                  <button
                    onClick={() => {
                      setEditMode(!editMode);
                      setEditedPost(finalPost.post || "");
                    }}
                    className="text-xs text-blue-400 hover:text-blue-300 transition"
                  >
                    {editMode ? "Cancel Edit" : "Edit"}
                  </button>
                )}
              </div>
              {editMode ? (
                <textarea
                  value={editedPost}
                  onChange={(e) => setEditedPost(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded p-4 text-sm leading-relaxed focus:outline-none focus:border-blue-500 transition min-h-[300px] resize-y font-mono"
                />
              ) : (
                <div className="whitespace-pre-wrap text-sm leading-relaxed text-gray-200">
                  {finalPost.post}
                </div>
              )}
            </div>

            {/* CTA */}
            <div className="p-4 bg-gray-900 border border-gray-800 rounded-lg">
              <div className="text-xs text-green-400 uppercase tracking-wider mb-2">
                Call to Action
              </div>
              <p className="text-sm font-medium">{finalPost.cta}</p>
            </div>

            {/* Hashtags */}
            {finalPost.hashtags && finalPost.hashtags.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {finalPost.hashtags.map((tag, i) => (
                  <span
                    key={i}
                    className="px-2 py-1 bg-gray-800 border border-gray-700 rounded text-xs text-blue-400"
                  >
                    #{tag.replace(/^#/, "")}
                  </span>
                ))}
              </div>
            )}

            {/* Reasoning */}
            {finalPost.reasoning && (
              <div className="p-4 bg-gray-900/50 border border-gray-800 rounded-lg">
                <div className="text-xs text-gray-500 uppercase tracking-wider mb-2">
                  AI Reasoning
                </div>
                <p className="text-xs text-gray-400 whitespace-pre-wrap leading-relaxed">
                  {finalPost.reasoning}
                </p>
              </div>
            )}

            {/* Generated Hooks */}
            {hooks.length > 0 && (
              <details className="bg-gray-900/30 border border-gray-800 rounded-lg">
                <summary className="px-4 py-3 cursor-pointer text-xs text-gray-500 uppercase tracking-wider hover:text-gray-300 transition">
                  All Generated Hooks ({hooks.length})
                </summary>
                <div className="px-4 pb-4 space-y-2">
                  {hooks.map((hook, i) => (
                    <div
                      key={i}
                      className={`p-3 rounded border text-xs ${
                        hook.text === selectedHook
                          ? "border-blue-600 bg-blue-900/20"
                          : "border-gray-800 bg-gray-900"
                      }`}
                    >
                      <div className="flex justify-between mb-1">
                        <span className="text-gray-400 uppercase">
                          {hook.type}
                        </span>
                        <span className={scoreColor(hook.strength_score)}>
                          {hook.strength_score}/10
                        </span>
                      </div>
                      <p className="text-gray-200 whitespace-pre-wrap">
                        {hook.text}
                      </p>
                    </div>
                  ))}
                </div>
              </details>
            )}

            {/* Trends */}
            {trends && (
              <details className="bg-gray-900/30 border border-gray-800 rounded-lg">
                <summary className="px-4 py-3 cursor-pointer text-xs text-gray-500 uppercase tracking-wider hover:text-gray-300 transition">
                  Trend Research
                </summary>
                <div className="px-4 pb-4">
                  <p className="text-xs text-gray-400 whitespace-pre-wrap leading-relaxed">
                    {trends}
                  </p>
                </div>
              </details>
            )}

            {/* ========== ACTION BUTTONS ========== */}
            {awaitingApproval && (
              <div className="flex gap-3 pt-2">
                <button
                  onClick={() => handleAction("approved")}
                  disabled={loading}
                  className="flex-1 bg-green-700 hover:bg-green-600 disabled:bg-gray-700 text-white font-bold py-3 rounded transition text-sm uppercase tracking-wider"
                >
                  Approve{linkedInAuth ? " & Publish" : ""}
                </button>
                <button
                  onClick={() => handleAction("regenerate")}
                  disabled={loading}
                  className="flex-1 bg-yellow-700 hover:bg-yellow-600 disabled:bg-gray-700 text-white font-bold py-3 rounded transition text-sm uppercase tracking-wider"
                >
                  Regenerate
                </button>
                <button
                  onClick={() => handleAction("rejected")}
                  disabled={loading}
                  className="flex-1 bg-red-800 hover:bg-red-700 disabled:bg-gray-700 text-white font-bold py-3 rounded transition text-sm uppercase tracking-wider"
                >
                  Reject
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
