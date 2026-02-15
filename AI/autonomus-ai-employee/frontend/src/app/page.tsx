"use client";

import { useState, useEffect, useRef } from "react";

export default function Home() {
  // --- STATE ---
  const [msg, setMsg] = useState("");
  const [response, setResponse] = useState("");
  const [loading, setLoading] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [plan, setPlan] = useState<string[]>([]);
  const [awaitingApproval, setAwaitingApproval] = useState(false);

  // --- EFFECTS ---

  // --- HANDLERS ---

  // 🚀 STEP 1: START RESEARCH
  const startResearch = async () => {
    if (!msg) return;

    setLoading(true);
    setResponse("");
    setPlan([]);
    setAwaitingApproval(false);

    try {
      const res = await fetch("http://127.0.0.1:8000/chat/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg }),
      });

      const data = await res.json();
      setThreadId(data.thread_id);
      setPlan(data.proposed_plan || []);
      setAwaitingApproval(true);
    } catch (err) {
      setResponse("Error connecting to backend");
    } finally {
      setLoading(false);
    }
  };

  // ✅ STEP 2: APPROVE PLAN
  const approvePlan = async () => {
    if (!threadId) return;

    setLoading(true);

    try {
      const res = await fetch("http://127.0.0.1:8000/chat/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          thread_id: threadId,
          approve: true,
          edited_plan: plan,
        }),
      });

      const data = await res.json();

      if (data.status === "awaiting_approval_again") {
        setPlan(data.proposed_plan || []);
        setAwaitingApproval(true);
        setResponse("");
      } else if (data.status === "complete") {
        setResponse(data.final_answer);
        setAwaitingApproval(false);
        setPlan([]);
        setThreadId(null);
      } else {
        setResponse("Approval failed or unknown status");
        setAwaitingApproval(false);
      }
    } catch (err) {
      setResponse("Approval failed");
      setAwaitingApproval(false);
    } finally {
      setLoading(false);
    }
  };

  const cancelPlan = () => {
    setAwaitingApproval(false);
    setPlan([]);
    setThreadId(null);
  };

  const updateStep = (index: number, value: string) => {
    const newPlan = [...plan];
    newPlan[index] = value;
    setPlan(newPlan);
  };

  // --- RENDER ---
  return (
    <main className="min-h-screen bg-[#0a0a0a] text-gray-100 flex flex-col items-center p-6 md:p-12 font-mono">
      <div className="w-full max-w-3xl">
        <h1 className="text-2xl font-bold mb-8 text-center border-b border-gray-800 pb-4">
          <span className="text-blue-500">SYSTEM:</span> AUTONOMOUS AGENT
        </h1>

        {/* INPUT SECTION */}
        <div className="flex gap-2 mb-8">
          <input
            className="flex-1 p-4 rounded bg-gray-900 border border-gray-700 focus:outline-none focus:border-blue-500 transition-colors"
            placeholder="Assign a complex task..."
            value={msg}
            onChange={(e) => setMsg(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && startResearch()}
          />
          <button
            onClick={startResearch}
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 px-8 py-4 rounded font-bold transition-all"
          >
            INITIALIZE
          </button>
        </div>

        {/* AGENT STATUS */}
        {loading && (
          <div className="mb-6 flex items-center justify-center gap-2 text-yellow-500 text-sm animate-pulse">
            <span className="h-2 w-2 bg-yellow-500 rounded-full"></span>
            PROCESSING COMMAND...
          </div>
        )}

        {/* PLAN APPROVAL SECTION */}
        {awaitingApproval && (
          <div className="mb-8 w-full bg-gray-900 border border-yellow-700/50 p-6 rounded-lg shadow-xl">
            <h2 className="text-sm font-bold mb-4 text-yellow-500 tracking-widest uppercase">
               Proposed Strategy
            </h2>
            <div className="space-y-3">
              {plan.map((step, i) => (
                <div key={i} className="flex gap-3 items-center">
                  <span className="text-gray-500 text-xs">{i + 1}.</span>
                  <input
                    value={step}
                    onChange={(e) => updateStep(i, e.target.value)}
                    className="w-full p-2 bg-gray-800 border border-gray-700 rounded text-sm focus:border-yellow-500 outline-none"
                  />
                </div>
              ))}
            </div>
            <div className="flex gap-4 mt-6">
              <button
                onClick={approvePlan}
                className="flex-1 bg-green-700 hover:bg-green-600 py-3 rounded text-sm font-bold uppercase tracking-wider transition-colors"
              >
                Confirm & Deploy
              </button>
              <button
                onClick={cancelPlan}
                className="bg-transparent hover:bg-gray-800 border border-gray-600 px-6 py-3 rounded text-sm transition-colors"
              >
                Abort
              </button>
            </div>
          </div>
        )}

        {/* OUTPUT DISPLAY */}
        {response && (
          <div className="mb-8 w-full bg-gray-900 border border-blue-900 p-6 rounded-lg">
            <h2 className="text-sm font-bold mb-4 text-blue-400 uppercase tracking-widest">
              Mission Report
            </h2>
            <div className="text-sm leading-relaxed text-gray-300 whitespace-pre-wrap">
              {response}
            </div>
          </div>
        )}

        {/* LOGS PANEL REMOVED: logs now written to backend log.txt */}
      </div>
    </main>
  );
}
