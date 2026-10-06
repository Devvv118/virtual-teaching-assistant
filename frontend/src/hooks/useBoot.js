import { useEffect, useState } from "react";
import { API_URL, fetchBoot } from "../lib/api";

// Replays the startup messages main.py recorded, then adds a live DB ping.
// status: "connecting" | "ready" | "offline"
export default function useBoot() {
  const [lines, setLines] = useState([]);
  const [status, setStatus] = useState("connecting");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    const timers = [];
    const push = (l) => setLines((ls) => [...ls, l]);
    const later = (fn, ms) => timers.push(setTimeout(fn, ms));

    setLines([]);
    setStatus("connecting");
    push({ scope: "client", level: "info", msg: `connecting to ${API_URL} ...` });

    fetchBoot(ctrl.signal)
      .then((data) => {
        const STEP = 110;
        data.boot.forEach((b, i) => later(() => push({ ...b, scope: "server" }), STEP * (i + 1)));
        later(() => {
          if (data.db.ok) push({ scope: "client", level: "ok", msg: `live database ping ok - ${data.db.ms} ms` });
          else push({ scope: "client", level: "error", msg: "live database ping failed" });
        }, STEP * (data.boot.length + 1));
        later(() => {
          push({ scope: "client", level: data.db.ok ? "ok" : "warn", msg: `api ready - up ${data.uptime}s` });
          setStatus(data.db.ok ? "ready" : "offline");
        }, STEP * (data.boot.length + 2));
      })
      .catch((e) => {
        if (e.name === "AbortError") return;
        push({ scope: "client", level: "error", msg: `cannot reach the API (${e.message})` });
        push({ scope: "client", level: "warn", msg: "is the backend running?  ->  cd backend && python main.py" });
        setStatus("offline");
      });

    return () => {
      ctrl.abort();
      timers.forEach(clearTimeout);
    };
  }, [attempt]);

  return { lines, status, retry: () => setAttempt((a) => a + 1) };
}
