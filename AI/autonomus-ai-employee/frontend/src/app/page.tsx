"use client";
import { useState } from "react";

export default function Home() {
  const [msg, setMsg] = useState("");
  const [response, setResponse] = useState("");
  const [loading, setLoading] = useState(false);

  const sendMessage = async () => {
    if (!msg) return;

    setLoading(true);
    setResponse("");

    try {
      const res = await fetch("http://127.0.0.1:8000/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message: msg }),
      });

      const data = await res.json();
      setResponse(data.response);
    } catch (err) {
      setResponse("Error connecting to backend");
    }

    setLoading(false);
  };

  return (
    <main className="min-h-screen bg-black text-white flex flex-col items-center p-10">
      <h1 className="text-3xl font-bold mb-6">🧠 Autonomous AI Employee</h1>

      <div className="w-full max-w-2xl flex gap-2">
        <input
          className="flex-1 p-3 rounded bg-gray-800"
          placeholder="Give your AI a task..."
          value={msg}
          onChange={(e) => setMsg(e.target.value)}
        />
        <button
          onClick={sendMessage}
          className="bg-blue-600 px-6 py-3 rounded"
        >
          Send
        </button>
      </div>

      {loading && <p className="mt-6">Thinking...</p>}

      {response && (
        <div className="mt-6 w-full max-w-2xl bg-gray-900 p-4 rounded">
          <pre className="whitespace-pre-wrap">{response}</pre>
        </div>
      )}
    </main>
  );
}
