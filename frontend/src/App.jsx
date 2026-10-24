import { useEffect, useRef, useState } from "react";
import { streamAsk } from "./lib/api";
import useBoot from "./hooks/useBoot";
import { Prompt, TerminalWindow } from "./components/Terminal";
import LogLine from "./components/LogLine";
import AskForm from "./components/AskForm";
import RunBlock from "./components/RunBlock";
import Notices from "./components/Notices";

export default function App() {
  const { lines: bootLines, status, retry } = useBoot();
  const [runs, setRuns] = useState([]);
  const ctrlRef = useRef(null);
  const bottomRef = useRef(null);
  const nextId = useRef(1);
  const [queued, setQueued] = useState(null); // sample picked before the backend woke up

  const busy = runs.some((r) => r.status === "running");
  const patch = (id, fn) => setRuns((rs) => rs.map((r) => (r.id === id ? fn(r) : r)));

  // keep the newest output in view once the conversation has started
  const lineCount = runs.reduce((n, r) => n + r.lines.length, 0);
  useEffect(() => {
    if (runs.length) bottomRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [lineCount, runs.length]);

  const ask = async ({ question, link }) => {
    const id = nextId.current++;
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;
    setRuns((rs) => [...rs, { id, question, link, lines: [], status: "running", answer: "", sources: [], error: null, duration: null }]);

    const fail = (msg, code) =>
      patch(id, (r) => ({
        ...r,
        status: "error",
        error: { status: code, msg },
        lines: [...r.lines, { level: "error", msg }],
      }));

    try {
      await streamAsk(
        { question, link },
        (ev) => {
          if (ev.type === "log") patch(id, (r) => ({ ...r, lines: [...r.lines, { level: ev.level, msg: ev.msg, t: ev.t }] }));
          else if (ev.type === "result") patch(id, (r) => ({ ...r, status: "done", answer: ev.answer, sources: ev.links, duration: ev.t }));
          else if (ev.type === "error")
            patch(id, (r) => ({
              ...r,
              status: "error",
              error: { status: ev.status, msg: ev.msg },
              lines: [...r.lines, { level: "error", msg: ev.msg, t: ev.t }],
            }));
        },
        ctrl.signal,
      );
      // stream closed without a result/error
      patch(id, (r) => (r.status === "running" ? { ...r, status: "error", lines: [...r.lines, { level: "error", msg: "connection closed before the answer arrived" }] } : r));
    } catch (e) {
      if (e.name === "AbortError") patch(id, (r) => ({ ...r, status: "aborted", lines: [...r.lines, { level: "warn", msg: "interrupted" }] }));
      else fail(`request failed: ${e.message}`);
    }
  };

  // run a queued sample as soon as the backend is reachable
  useEffect(() => {
    if (queued && status === "ready" && !busy) {
      const q = queued;
      setQueued(null);
      ask({ question: q, link: "" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queued, status, busy]);

  return (
    <main className="min-h-screen page-bg font-mono text-cream">
      <TerminalWindow status={status}>
        <h1 className="font-warm-display text-2xl text-cream md:text-4xl">Virtual Teaching Assistant</h1>
        <p className="mt-3 max-w-xl text-sm leading-relaxed text-cream/70">
          Ask a question about the IITM TDS course of Jan 2025. The answer is retrieved from the course material and past Discourse threads
          - and you can watch every step as it runs.
        </p>

        <Notices status={status} />

        <Prompt className="mt-10">python main.py</Prompt>
        <div className="mt-4 space-y-1">
          {bootLines.map((l, i) => (
            <LogLine key={i} {...l} />
          ))}
          {status === "offline" && (
            <button type="button" onClick={retry} className="mt-3 text-[12px] text-gold underline underline-offset-4 hover:text-gold-soft">
              [ retry connection ]
            </button>
          )}
        </div>

        {runs.map((r) => (
          <RunBlock key={r.id} run={r} />
        ))}

        <AskForm
          disabled={status !== "ready"}
          offline={status === "offline"}
          busy={busy}
          queued={queued}
          onSubmit={ask}
          onPick={(q) => (status === "ready" ? ask({ question: q, link: "" }) : setQueued(q))}
          onInterrupt={() => ctrlRef.current?.abort()}
        />

        {runs.length > 0 && !busy && (
          <button
            type="button"
            onClick={() => setRuns([])}
            className="mt-8 text-[11px] text-white/35 underline-offset-4 transition-colors hover:text-gold hover:underline"
          >
            $ clear
          </button>
        )}
        <div ref={bottomRef} />
      </TerminalWindow>
    </main>
  );
}
