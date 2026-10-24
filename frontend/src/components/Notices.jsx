// Two things every visitor should know before asking anything.
export default function Notices({ status }) {
  const waking = status === "connecting";
  return (
    <div className="mt-8 grid gap-3 md:grid-cols-2">
      <div className={`rounded-lg border p-4 ${waking ? "border-notice/40 bg-notice/[0.07]" : "border-white/10 bg-white/[0.03]"}`}>
        <p className="flex items-center gap-2 text-[11px] tracking-[0.14em] text-notice uppercase">
          <span className={`h-1.5 w-1.5 rounded-full bg-notice ${waking ? "animate-pulse" : ""}`} />
          May take a while to connect
        </p>
        <p className="mt-2 text-[12.5px] leading-relaxed text-cream/75">
          The backend runs on a free server that sleeps when idle. The first connection can take{" "}
          <span className="text-cream">up to a minute</span> while it wakes up. Please keep this page open - it connects on its own.
        </p>
      </div>

      <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4">
        <p className="flex items-center gap-2 text-[11px] tracking-[0.14em] text-gold uppercase">
          <span className="h-1.5 w-1.5 rounded-full bg-gold" />
          Course questions only
        </p>
        <p className="mt-2 text-[12.5px] leading-relaxed text-cream/75">
          The assistant answers <span className="text-cream">only questions strictly relevant to the course</span> (TDS, Jan 2025). Anything
          unrelated - general chat, other subjects - will not be answered.
        </p>
      </div>
    </div>
  );
}
