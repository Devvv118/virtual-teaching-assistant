const LEVEL = {
  info: { sym: "›", text: "text-cream/70", sym_c: "text-white/40" },
  ok: { sym: "✓", text: "text-cream/85", sym_c: "text-term-green" },
  warn: { sym: "!", text: "text-gold-soft", sym_c: "text-gold" },
  error: { sym: "✗", text: "text-term-red", sym_c: "text-term-red" },
  hit: { sym: "◆", text: "text-gold-soft", sym_c: "text-gold" },
};

export default function LogLine({ level = "info", msg, t, scope }) {
  const l = LEVEL[level] ?? LEVEL.info;
  const stamp = [scope, t != null ? `+${t.toFixed(2)}s` : null].filter(Boolean).join(" ");
  return (
    <div className="line-in flex gap-2 text-[12.5px] leading-relaxed">
      <span className="tabular w-[8.5rem] shrink-0 text-right text-white/30 max-sm:hidden">{stamp && `[${stamp}]`}</span>
      <span className={`w-3 shrink-0 text-center ${l.sym_c}`}>{l.sym}</span>
      <span className={`min-w-0 break-words whitespace-pre-wrap ${l.text}`}>{msg}</span>
    </div>
  );
}
