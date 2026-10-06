import { useEffect, useRef, useState } from "react";
import { isSupportedLink } from "../lib/api";
import { Prompt } from "./Terminal";

const MAX_QUESTION = 20_000;

export default function AskForm({ disabled, busy, onSubmit, onInterrupt }) {
  const [question, setQuestion] = useState("");
  const [link, setLink] = useState("");
  const taRef = useRef(null);

  const trimmedLink = link.trim();
  const linkBad = trimmedLink !== "" && !isSupportedLink(trimmedLink);
  const canRun = !disabled && !busy && question.trim() !== "" && !linkBad;

  // grow the textarea with its content
  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [question]);

  // focus when the terminal becomes usable again
  useEffect(() => {
    if (!disabled && !busy) taRef.current?.focus({ preventScroll: true });
  }, [disabled, busy]);

  const run = () => {
    if (!canRun) return;
    onSubmit({ question: question.trim(), link: trimmedLink });
    setQuestion("");
    setLink("");
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      run();
    }
  };

  return (
    <section className="mt-10">
      <Prompt>ask</Prompt>

      <label className="mt-3 flex items-start gap-3 text-[13px]">
        <span className="w-[5.5rem] shrink-0 pt-[3px] text-gold-soft">question</span>
        <span className="pt-[3px] text-gold">▸</span>
        <textarea
          ref={taRef}
          rows={1}
          value={question}
          maxLength={MAX_QUESTION}
          disabled={disabled || busy}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={disabled ? "waiting for the backend ..." : "e.g. When is the project 1 deadline?"}
          spellCheck={false}
          className="min-w-0 flex-1 resize-none border-b border-dashed border-white/20 bg-transparent py-0.5 text-cream caret-gold outline-none transition-colors placeholder:text-white/25 focus:border-gold disabled:opacity-50"
        />
      </label>

      <label className="mt-3 flex items-start gap-3 text-[13px]">
        <span className="w-[5.5rem] shrink-0 pt-[3px] text-gold-soft">
          link <span className="text-white/30">(opt)</span>
        </span>
        <span className="pt-[3px] text-gold">▸</span>
        <input
          value={link}
          disabled={disabled || busy}
          onChange={(e) => setLink(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="https://tds.s-anand.net/#/…  or  https://discourse.onlinedegree.iitm.ac.in/t/…"
          spellCheck={false}
          className={`min-w-0 flex-1 border-b border-dashed bg-transparent py-0.5 text-cream caret-gold outline-none transition-colors placeholder:text-white/25 disabled:opacity-50 ${
            linkBad ? "border-term-red" : "border-white/20 focus:border-gold"
          }`}
        />
      </label>

      {linkBad && (
        <p className="mt-2 pl-[7.1rem] text-[12px] text-term-red">
          ✗ link not supported - use a tds.s-anand.net page or a discourse.onlinedegree.iitm.ac.in/t/ thread
        </p>
      )}

      <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-3 pl-0 md:pl-[7.1rem]">
        {busy ? (
          <button
            type="button"
            onClick={onInterrupt}
            className="rounded-full border border-term-red/60 px-5 py-2.5 text-[11px] tracking-[0.08em] text-term-red transition-colors hover:bg-term-red/10"
          >
            ^C INTERRUPT
          </button>
        ) : (
          <button
            type="button"
            onClick={run}
            disabled={!canRun}
            className="rounded-full border border-gold bg-gold px-5 py-2.5 text-[11px] tracking-[0.08em] text-warm-ink transition-colors hover:bg-gold-soft disabled:cursor-not-allowed disabled:border-white/15 disabled:bg-transparent disabled:text-white/30"
          >
            RUN ⏎
          </button>
        )}
        <span className="text-[11px] text-white/35">
          enter to run · shift+enter for a new line · {question.length.toLocaleString()}/{MAX_QUESTION.toLocaleString()}
        </span>
      </div>
    </section>
  );
}
