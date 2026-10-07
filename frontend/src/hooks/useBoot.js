import { useEffect, useState } from "react";
import { API_URL, pingServer } from "../lib/api";

// Waits for the backend (e.g. a Render cold start) to answer, giving up after a minute.
// status: "connecting" | "ready" | "offline"
const TIMEOUT_MS = 60_000;
const RETRY_MS = 3_000;

export default function useBoot() {
  const [lines, setLines] = useState([]);
  const [status, setStatus] = useState("connecting");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    let timer;
    const push = (l) => setLines((ls) => [...ls, l]);
    const start = Date.now();

    setLines([]);
    setStatus("connecting");
    push({ scope: "client", level: "info", msg: `connecting to ${API_URL} ...` });
    push({ scope: "client", level: "info", msg: "waiting for the server to start (up to 60s) ..." });

    const tryConnect = async () => {
      try {
        await pingServer(ctrl.signal);
        push({ scope: "client", level: "ok", msg: "api ready" });
        setStatus("ready");
      } catch (e) {
        if (e.name === "AbortError") return;
        if (Date.now() - start >= TIMEOUT_MS) {
          push({ scope: "client", level: "error", msg: "connection timed out after 60s" });
          setStatus("offline");
        } else {
          timer = setTimeout(tryConnect, RETRY_MS);
        }
      }
    };
    tryConnect();

    return () => {
      ctrl.abort();
      clearTimeout(timer);
    };
  }, [attempt]);

  return { lines, status, retry: () => setAttempt((a) => a + 1) };
}
