import { motion, AnimatePresence } from "framer-motion";
import { GlassCard } from "../components/GlassCard";
import { getNodeDisplay } from "../linkedin/nodeDisplayConfig";
import type { PipelineStatus } from "../linkedin/useLinkedInWebSocket";

interface LiveStatusPanelProps {
  status: PipelineStatus;
  className?: string;
}

export function LiveStatusPanel({ status, className = "" }: LiveStatusPanelProps) {
  const nodeConfig = getNodeDisplay(status.currentNode || undefined);

  // Extract key metrics from metadata with proper type guards
  const viralScore =typeof status.metadata.viral_score === "number" ? status.metadata.viral_score : 
    (typeof status.metadata.viralScore === "number" ? status.metadata.viralScore : null);
  const realismScore = typeof status.metadata.realism_score === "number" ? status.metadata.realism_score :
    (typeof status.metadata.realismScore === "number" ? status.metadata.realismScore : null);
  const researchConfidence = typeof status.metadata.research_confidence === "number" ? status.metadata.research_confidence :
    (typeof status.metadata.researchConfidence === "number" ? status.metadata.researchConfidence : null);
  const iterationCount = typeof status.metadata.iteration_count === "number" ? status.metadata.iteration_count :
    (typeof status.metadata.iterationCount === "number" ? status.metadata.iterationCount : 0);
  
  // Display 1-based iteration (0 -> 1, 1 -> 2, etc.)
  const displayIteration = iterationCount + 1;
  
  const researchRetryCount = typeof status.metadata.research_retry_count === "number" ? status.metadata.research_retry_count :
    (typeof status.metadata.researchRetryCount === "number" ? status.metadata.researchRetryCount : 0);
  const counterClaims = Array.isArray(status.metadata.counter_claims) ? status.metadata.counter_claims :
    (Array.isArray(status.metadata.counterClaims) ? status.metadata.counterClaims : []);
  const riskFlags = Array.isArray(status.metadata.risk_flags) ? status.metadata.risk_flags :
    (Array.isArray(status.metadata.riskFlags) ? status.metadata.riskFlags : []);
  
  // Extract API usage stats from metadata
  const llmCalls = typeof status.metadata.llm_calls === "number" ? status.metadata.llm_calls : 0;
  const searchCalls = typeof status.metadata.search_calls === "number" ? status.metadata.search_calls : 0;
  const totalTokens = typeof status.metadata.total_tokens === "number" ? status.metadata.total_tokens : 0;
  const totalApiCalls = typeof status.metadata.total_api_calls === "number" ? status.metadata.total_api_calls : (llmCalls + searchCalls);

  if (!status.isRunning && !status.isComplete) {
    return null;
  }

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key="live-status"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -16 }}
        transition={{ duration: 0.35 }}
        className={className}
      >
        <GlassCard className="p-6">
          <div className="flex items-start gap-4">
            {/* Icon & Status Indicator */}
            <motion.div
              key={status.currentNode || "idle"}
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.3, type: "spring", stiffness: 200 }}
              className="relative flex-shrink-0"
            >
              <div
                className={`flex h-12 w-12 items-center justify-center rounded-xl text-2xl ${
                  status.error
                    ? "bg-red-500/20"
                    : status.isComplete
                      ? "bg-green-500/20"
                      : "bg-blue-500/20"
                }`}
              >
                {nodeConfig.icon}
              </div>

              {/* Pulsing indicator dot */}
              {status.isRunning && !status.isComplete && !status.error && (
                <motion.div
                  className="absolute -right-1 -top-1 h-3 w-3 rounded-full bg-blue-500"
                  animate={{
                    scale: [1, 1.3, 1],
                    opacity: [1, 0.6, 1],
                  }}
                  transition={{
                    duration: 1.5,
                    repeat: Infinity,
                    ease: "easeInOut",
                  }}
                />
              )}
            </motion.div>

            {/* Status Text */}
            <div className="flex-1 space-y-2">
              <div>
                <p className="eyebrow">
                  {status.isComplete
                    ? "Complete"
                    : status.error
                      ? "Error"
                      : "Live Pipeline Status"}
                </p>
                <AnimatePresence mode="wait">
                  <motion.h3
                    key={nodeConfig.label}
                    initial={{ opacity: 0, x: -12 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 12 }}
                    transition={{ duration: 0.25 }}
                    className="text-xl font-semibold"
                  >
                    {nodeConfig.label}
                  </motion.h3>
                </AnimatePresence>
              </div>

              <AnimatePresence mode="wait">
                <motion.p
                  key={status.statusText}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="text-sm muted-text"
                >
                  {status.statusText || nodeConfig.description}
                </motion.p>
              </AnimatePresence>

              {/* Metrics Pills */}
              {(viralScore || realismScore || researchConfidence !== undefined || iterationCount > 0 || researchRetryCount > 0) && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.2 }}
                  className="flex flex-wrap gap-2 pt-2"
                >
                  {viralScore !== null && (
                    <span className="status-pill text-xs">
                      🔥 Viral: {viralScore.toFixed(1)}/10
                    </span>
                  )}
                  {realismScore !== null && (
                    <span className="status-pill text-xs">
                      ✓ Realism: {realismScore.toFixed(1)}/10
                    </span>
                  )}
                  {researchConfidence !== null && (
                    <span className="status-pill text-xs">
                      📊 Confidence: {researchConfidence.toFixed(1)}/10
                    </span>
                  )}
                  {iterationCount > 0 && (
                    <span className="status-pill text-xs">
                      🔄 Iteration: {displayIteration}
                    </span>
                  )}
                  {researchRetryCount > 0 && (
                    <span className="status-pill text-xs bg-orange-500/10">
                      🔍 Re-search: {researchRetryCount}
                    </span>
                  )}
                </motion.div>
              )}

              {/* API Usage Stats */}
              {totalApiCalls > 0 && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.25 }}
                  className="flex flex-wrap gap-2 pt-2"
                >
                  <span className="status-pill text-xs bg-blue-500/10">
                    🤖 LLM: {llmCalls}
                  </span>
                  <span className="status-pill text-xs bg-green-500/10">
                    🔎 Search: {searchCalls}
                  </span>
                  {totalTokens > 0 && (
                    <span className="status-pill text-xs bg-cyan-500/10">
                      📊 {(totalTokens / 1000).toFixed(1)}k tokens
                    </span>
                  )}
                </motion.div>
              )}

              {/* Risk Flags */}
              {(counterClaims.length > 0 || riskFlags.length > 0) && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.3 }}
                  className="flex flex-wrap gap-2 pt-2"
                >
                  {counterClaims.length > 0 && (
                    <span className="status-pill text-xs bg-yellow-500/10">
                      ⚠️ {counterClaims.length} counter-claim{counterClaims.length !== 1 ? "s" : ""}
                    </span>
                  )}
                  {riskFlags.length > 0 && (
                    <span className="status-pill text-xs bg-red-500/10">
                      🚩 {riskFlags.length} risk flag{riskFlags.length !== 1 ? "s" : ""}
                    </span>
                  )}
                </motion.div>
              )}

              {/* Error Display */}
              {status.error && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="mt-3 rounded-lg bg-red-500/10 p-3 text-sm text-red-400"
                >
                  {status.error}
                </motion.div>
              )}
            </div>
          </div>

          {/* Progress Bar */}
          {status.isRunning && !status.isComplete && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.4 }}
              className="mt-4 h-1 w-full overflow-hidden rounded-full bg-white/5"
            >
              <motion.div
                className="h-full bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500"
                animate={{
                  x: ["-100%", "100%"],
                }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  ease: "linear",
                }}
                style={{ width: "50%" }}
              />
            </motion.div>
          )}
        </GlassCard>
      </motion.div>
    </AnimatePresence>
  );
}
