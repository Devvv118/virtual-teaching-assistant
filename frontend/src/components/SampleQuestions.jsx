import { SAMPLE_QUESTIONS } from "../lib/samples";

// Click a sample to run it straight away (or queue it until the backend has woken up).
export default function SampleQuestions({ onPick, disabled, waiting, queued }) {
  return (
    <section className="mt-8">
      <p className="text-[11px] tracking-[0.14em] text-white/50 uppercase">Try a sample question</p>
      <div className="mt-3 flex flex-col gap-2">
        {SAMPLE_QUESTIONS.map((q) => {
          const isQueued = queued === q;
          return (
            <button
              key={q}
              type="button"
              disabled={disabled || !!queued}
              onClick={() => onPick(q)}
              className={`group flex items-start gap-3 rounded-lg border px-4 py-3 text-left text-[13px] transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                isQueued ? "border-gold bg-gold/10" : "border-white/10 bg-white/[0.03] enabled:hover:border-gold/60 enabled:hover:bg-gold/[0.07]"
              }`}
            >
              <span className="pt-px text-gold transition-transform group-enabled:group-hover:translate-x-0.5">▸</span>
              <span className="min-w-0 flex-1 text-cream/90">{q}</span>
              {isQueued && <span className="shrink-0 text-[11px] text-gold">queued - runs when connected</span>}
            </button>
          );
        })}
      </div>
      {waiting && !queued && (
        <p className="mt-2 text-[11px] text-white/35">Click one now - it will run automatically once the server is connected.</p>
      )}
    </section>
  );
}
