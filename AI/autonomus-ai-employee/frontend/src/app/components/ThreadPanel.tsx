import { useEffect, useRef, useState } from "react";
import { ScrollArea } from "./ui/scroll-area";
import { Skeleton } from "./ui/skeleton";

interface ThreadPanelProps {
  baseUrl: string;
  onSelectThread: (threadId: string) => void;
  selectedThreadId?: string;
}

interface Thread {
  id: string;
  topic?: string;
  status?: string;
  viral_score?: number;
  created_at?: string;
}

export function ThreadPanel({ baseUrl, onSelectThread, selectedThreadId }: ThreadPanelProps) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(false);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [isHovered, setIsHovered] = useState(false);
  const [isPinnedOpen, setIsPinnedOpen] = useState(false);
  const limit = 20;
  const scrollRef = useRef<HTMLDivElement>(null);
  const isExpanded = isPinnedOpen || isHovered;

  useEffect(() => {
    fetchMoreThreads();
    // eslint-disable-next-line
  }, []);

  const fetchMoreThreads = async () => {
    if (loading || !hasMore) return;
    setLoading(true);
    try {
      const res = await fetch(`${baseUrl}/linkedin/posts?offset=${offset}&limit=${limit}`, { cache: "no-store" });
      if (!res.ok) {
        throw new Error("Failed to load threads");
      }
      const data = await res.json();
      const posts = Array.isArray(data.posts) ? data.posts : [];

      if (posts.length > 0) {
        setThreads((prev) => [
          ...prev,
          ...posts.map((post: Thread) => ({
            id: String(post.id),
            topic: post.topic,
            status: post.status,
            viral_score: post.viral_score,
            created_at: post.created_at,
          })),
        ]);
        setOffset((prev) => prev + posts.length);
        if (posts.length < limit) setHasMore(false);
      } else {
        setHasMore(false);
      }
    } catch {
      setHasMore(false);
    } finally {
      setLoading(false);
    }
  };

  // Infinite scroll handler
  useEffect(() => {
    const handleScroll = () => {
      const el = scrollRef.current;
      if (!el || loading || !hasMore) return;
      if (el.scrollTop + el.clientHeight >= el.scrollHeight - 40) {
        fetchMoreThreads();
      }
    };
    const el = scrollRef.current;
    if (el) el.addEventListener("scroll", handleScroll);
    return () => {
      if (el) el.removeEventListener("scroll", handleScroll);
    };
    // eslint-disable-next-line
  }, [loading, hasMore]);

  // Deduplicate threads by id to avoid duplicate React keys
  const uniqueThreads = Array.from(
    threads.reduce((map, thread) => map.set(thread.id, thread), new Map<string, Thread>()).values()
  );

  return (
    <aside
      className={`h-full border-r border-[var(--glass-border)] bg-[var(--surface)]/60 backdrop-blur-xl transition-[width] duration-300 ${
        isExpanded ? "w-90" : "w-14"
      }`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div className={`pt-3 pb-2 ${isExpanded ? "px-3" : "px-2"}`}>
        <div className={`glass-card ${isExpanded ? "p-3" : "p-2"}`}>
          <div className={`flex items-center ${isExpanded ? "justify-between" : "justify-center"}`}>
            {isExpanded ? <p className="eyebrow !mb-0">Thread History</p> : null}
            <button
              type="button"
              className="ghost-button px-2 py-1 text-xs"
              aria-label={isPinnedOpen ? "Disable pinned thread list" : "Enable pinned thread list"}
              title={isPinnedOpen ? "Pinned open (click to switch to hover mode)" : "Hover mode (click to pin open)"}
              onClick={() => setIsPinnedOpen((prev) => !prev)}
            >
              {isPinnedOpen ? "📌" : "📍"}
            </button>
          </div>
          {isExpanded ? <p className="text-xs muted-text mt-1">Select a thread to open full details.</p> : null}
        </div>
      </div>

      <ScrollArea
        className={`transition-opacity duration-200 ${isExpanded ? "h-full opacity-100" : "h-0 opacity-0 pointer-events-none"}`}
        ref={scrollRef}
      >
        <div className="flex flex-col gap-2 px-3 pb-4">
          {uniqueThreads.map((thread) => (
            <button
              key={thread.id}
              type="button"
              className={`w-full text-left rounded-xl border p-3 transition-all duration-200 ${
                selectedThreadId === thread.id
                  ? "border-[var(--brand)] bg-[var(--surface-strong)] shadow-[0_8px_22px_rgba(0,0,0,0.14)]"
                  : "border-[var(--glass-border)] bg-[var(--surface)] hover:bg-[var(--surface-strong)]"
              }`}
              onClick={() => onSelectThread(thread.id)}
            >
              <div className="text-sm">
                <div className="flex justify-between items-center">
                  <p className="truncate font-medium">{thread.topic || thread.id}</p>
                </div>
                <div className="mt-2 flex items-center gap-2 text-[11px]">
                  <span className="status-pill !px-2 !py-0.5 capitalize">{thread.status || "draft"}</span>
                  {typeof thread.viral_score === "number" ? (
                    <span className="status-pill !px-2 !py-0.5">Score {thread.viral_score.toFixed(1)}</span>
                  ) : null}    
                  {thread.created_at && (
                    <span className="text-[10px] muted-text ml-auto">
                      {new Date(thread.created_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                        year: "2-digit",
                      })}
                    </span>
                  )}
                </div>
                
              </div>
            </button>
          ))}
          {loading && (
            <div className="flex flex-col gap-2">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-20 w-full rounded-xl" />
              ))}
            </div>
          )}
          {!hasMore && threads.length === 0 && !loading && (
            <div className="glass-card text-xs text-center py-4 muted-text">No threads found.</div>
          )}
        </div>
      </ScrollArea>
    </aside>
  );
}
