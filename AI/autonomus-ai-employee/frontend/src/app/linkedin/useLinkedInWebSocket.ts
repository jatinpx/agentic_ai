import { useEffect, useRef, useState, useCallback } from "react";

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://127.0.0.1:8000";

export interface PipelineEvent {
  type: string;
  thread_id: string;
  timestamp: string;
  node?: string;
  detail?: string;
  metadata?: Record<string, unknown>;
  error?: string;
  [key: string]: unknown;
}

export interface PipelineStatus {
  currentNode: string | null;
  statusText: string;
  isRunning: boolean;
  isComplete: boolean;
  error: string | null;
  metadata: Record<string, unknown>;
  events: PipelineEvent[];
}

/**
 * Custom hook to manage WebSocket connection for LinkedIn pipeline status streaming.
 * 
 * Usage:
 *   const { status, connect, disconnect } = useLinkedInWebSocket();
 *   
 *   // On pipeline start:
 *   connect(threadId);
 *   
 *   // Status updates automatically as events arrive:
 *   console.log(status.currentNode, status.statusText, status.metadata);
 */
export function useLinkedInWebSocket() {
  const [status, setStatus] = useState<PipelineStatus>({
    currentNode: null,
    statusText: "Idle",
    isRunning: false,
    isComplete: false,
    error: null,
    metadata: {},
    events: [],
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const threadIdRef = useRef<string | null>(null);
  const connectFnRef = useRef<((threadId: string) => void) | null>(null);

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const data: PipelineEvent = JSON.parse(event.data);

      setStatus((prev) => {
        const newEvents = [...prev.events, data];

        switch (data.type) {
          case "connected":
            return {
              ...prev,
              statusText: "Connected - waiting for pipeline to start",
              events: newEvents,
            };

          case "pipeline_start":
            return {
              ...prev,
              isRunning: true,
              isComplete: false,
              statusText: `Starting pipeline: ${data.topic || ""}`,
              events: newEvents,
            };

          case "node_start":
            return {
              ...prev,
              currentNode: data.node || null,
              statusText: data.detail || `Running ${data.node}...`,
              metadata: { ...prev.metadata, ...data.metadata },
              events: newEvents,
            };

          case "node_complete":
            return {
              ...prev,
              currentNode: data.node || null,
              statusText: data.detail || `Completed ${data.node}`,
              metadata: { ...prev.metadata, ...data.metadata },
              events: newEvents,
            };

          case "state_update":
            const updatedMetadata = { ...prev.metadata };
            if (data.key && typeof data.key === "string" && data.value !== undefined) {
              updatedMetadata[data.key] = data.value;
            }
            return {
              ...prev,
              statusText: (typeof data.summary === "string" ? data.summary : null) || `Updated ${data.key}`,
              metadata: updatedMetadata,
              events: newEvents,
            };

          case "error":
            return {
              ...prev,
              error: data.error || data.detail || "Pipeline error",
              statusText: `Error: ${data.error || "Unknown error"}`,
              isRunning: false,
              events: newEvents,
            };

          case "pipeline_complete":
            return {
              ...prev,
              isRunning: false,
              isComplete: true,
              statusText: "Pipeline complete",
              metadata: { 
                ...prev.metadata, 
                ...data,
                // Ensure final_post is preserved if sent
                final_post: data.final_post || prev.metadata.final_post 
              },
              events: newEvents,
            };

          case "usage_update":
            return {
              ...prev,
              metadata: { ...prev.metadata, ...data.metadata },
              events: newEvents,
            };

          default:
            return { ...prev, events: newEvents };
        }
      });
    } catch (error) {
      console.error("Failed to parse WebSocket message:", error);
    }
  }, []);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    threadIdRef.current = null;
  }, []);

  const connect = useCallback(
    (threadId: string) => {
      // Disconnect existing connection if any
      disconnect();

      threadIdRef.current = threadId;

      // Reset status
      setStatus({
        currentNode: null,
        statusText: "Connecting...",
        isRunning: true,
        isComplete: false,
        error: null,
        metadata: {},
        events: [],
      });

      try {
        const ws = new WebSocket(`${WS_BASE}/linkedin/ws/${threadId}`);
        wsRef.current = ws;

        ws.onopen = () => {
          console.log(`WebSocket connected for thread: ${threadId}`);
          setStatus((prev) => ({ ...prev, statusText: "Connected" }));
        };

        ws.onmessage = handleMessage;

        ws.onerror = (error) => {
          console.error("WebSocket error:", error);
          setStatus((prev) => ({
            ...prev,
            error: "Connection error",
            statusText: "Connection failed - retrying...",
          }));
        };

        ws.onclose = (event) => {
          console.log("WebSocket closed:", event.code, event.reason);

          // If pipeline is still running and not complete, try to reconnect
          if (
            threadIdRef.current === threadId &&
            !status.isComplete &&
            !status.error &&
            event.code !== 1000 // Normal closure
          ) {
            console.log("Attempting to reconnect in 2 seconds...");
            reconnectTimeoutRef.current = setTimeout(() => {
              if (threadIdRef.current === threadId && connectFnRef.current) {
                connectFnRef.current(threadId);
              }
            }, 2000);
          } else {
            setStatus((prev) => ({
              ...prev,
              isRunning: false,
              statusText: prev.isComplete ? "Complete" : "Disconnected",
            }));
          }
        };
      } catch (error) {
        console.error("Failed to create WebSocket:", error);
        setStatus((prev) => ({
          ...prev,
          error: "Failed to connect",
          statusText: "Connection failed",
          isRunning: false,
        }));
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [disconnect, handleMessage]
  );

  // Store connect function in ref so onclose can access it
  useEffect(() => {
    connectFnRef.current = connect;
  }, [connect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    status,
    connect,
    disconnect,
  };
}
