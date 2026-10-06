import LogLine from "./LogLine";
import Markdown from "./Markdown";
import { Caret, Prompt, Spinner } from "./Terminal";

const snippet = (s, n = 140) => {
  const flat = s.replace(/\s+/g, " ").trim();
  return flat.length > n ? flat.slice(0, n - 1) + "…" : flat;
};

// One question: echoed command -> streamed log lines -> answer -> sources -> exit code.
export default function RunBlock({ run }) {
  const { question, link, lines, status, answer, sources, error, duration } = run;

  return (
    <section className="mt-10 border-t border-white/10 pt-8">
      <Prompt>
        ask <span className="text-gold-soft">--question</span>{" "}
        <span className="whitespace-pre-wrap text-cream">"{question}"</span>
        {link && (
          <>
            {" "}
            <span className="text-gold-soft">--link</span> <span className="text-cream">"{link}"</span>
          </>
        )}
      </Prompt>

      <div className="mt-4 space-y-1">
        {lines.map((l, i) => (
          <LogLine key={i} scope="api" {...l} />
        ))}
        {status === "running" && (
          <div className="flex gap-2 text-[12.5px] text-white/40">
            <span className="w-[8.5rem] shrink-0 max-sm:hidden" />
            <span className="w-3 shrink-0 text-center">
              <Spinner />
            </span>
            <span>
              working <Caret />
            </span>
          </div>
        )}
      </div>

      {status === "done" && (
        <>
          <Prompt className="mt-8 border-b border-white/10 pb-3">cat answer.md</Prompt>
          <div className="line-in">
            <Markdown source={answer} />
          </div>

          {sources.length > 0 && (
            <>
              <Prompt className="mt-8">cat sources</Prompt>
              <ol className="mt-3 space-y-2">
                {sources.map((s, i) => (
                  <li key={i} className="line-in text-[12.5px]">
                    <details className="group">
                      <summary className="cursor-pointer list-none marker:hidden">
                        <span className="flex items-baseline gap-2">
                          <span className="text-gold">[{i + 1}]</span>
                          <a
                            href={s.url}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="min-w-0 break-all text-gold-soft underline underline-offset-4 hover:text-gold"
                          >
                            {s.url}
                          </a>
                          <span className="shrink-0 text-white/30 group-open:hidden">+ chunk</span>
                          <span className="hidden shrink-0 text-white/30 group-open:inline">- hide</span>
                        </span>
                        <span className="mt-1 block pl-7 text-white/35 group-open:hidden">{snippet(s.text)}</span>
                      </summary>
                      <p className="mt-2 ml-7 border-l-2 border-white/15 pl-4 break-words whitespace-pre-wrap text-cream/55">
                        {s.text}
                      </p>
                    </details>
                  </li>
                ))}
              </ol>
            </>
          )}
        </>
      )}

      {status !== "running" && (
        <p className={`mt-6 text-[11px] ${status === "done" ? "text-white/35" : "text-term-red/80"}`}>
          {status === "done" && `process exited with code 0 · ${duration?.toFixed(2)}s`}
          {status === "error" && `process exited with code 1${error?.status ? ` · http ${error.status}` : ""}`}
          {status === "aborted" && "^C"}
        </p>
      )}
    </section>
  );
}
