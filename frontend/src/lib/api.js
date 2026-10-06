export const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

// Same prefixes main.py accepts for the optional link.
export const LINK_PREFIXES = [
  "https://tds.s-anand.net/#/",
  "https://discourse.onlinedegree.iitm.ac.in/t/",
];
export const isSupportedLink = (l) => LINK_PREFIXES.some((p) => l.startsWith(p));

export async function fetchBoot(signal) {
  const res = await fetch(`${API_URL}/boot`, { signal });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// POST /api/stream -> newline-delimited JSON; onEvent() is called as each line arrives.
export async function streamAsk({ question, link }, onEvent, signal) {
  const res = await fetch(`${API_URL}/api/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, link: link || null }),
    signal,
  });

  if (!res.ok || !res.body) {
    let detail;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch { /* not JSON */ }
    throw new Error(detail ?? `HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (line) onEvent(JSON.parse(line));
    }
  }
  if (buf.trim()) onEvent(JSON.parse(buf));
}
