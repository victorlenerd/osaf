"use client";

import { useCallback, useEffect, useRef, useState } from "react";

function fmt(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const s = Math.floor(seconds);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

/** Audio player for voice-note reviews. Wraps a hidden <audio>; the URL 302-redirects to the file. */
export default function VoicePlayer({ src, reviewer }: { src: string | null; reviewer?: string | null }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [failed, setFailed] = useState(false);
  const [scrubbing, setScrubbing] = useState(false);

  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;
    const onTime = () => {
      if (!scrubbing) setCurrent(a.currentTime);
    };
    const onMeta = () => setDuration(Number.isFinite(a.duration) ? a.duration : 0);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onEnded = () => {
      setPlaying(false);
      setCurrent(0);
    };
    const onError = () => setFailed(true);
    a.addEventListener("timeupdate", onTime);
    a.addEventListener("loadedmetadata", onMeta);
    a.addEventListener("durationchange", onMeta);
    a.addEventListener("play", onPlay);
    a.addEventListener("pause", onPause);
    a.addEventListener("ended", onEnded);
    a.addEventListener("error", onError);
    return () => {
      a.removeEventListener("timeupdate", onTime);
      a.removeEventListener("loadedmetadata", onMeta);
      a.removeEventListener("durationchange", onMeta);
      a.removeEventListener("play", onPlay);
      a.removeEventListener("pause", onPause);
      a.removeEventListener("ended", onEnded);
      a.removeEventListener("error", onError);
    };
  }, [scrubbing, src]);

  const toggle = useCallback(() => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) a.play().catch(() => setFailed(true));
    else a.pause();
  }, []);

  const seek = (value: number) => {
    const a = audioRef.current;
    setCurrent(value);
    if (a && Number.isFinite(value)) a.currentTime = value;
  };

  const unavailable = !src || failed;
  const pct = duration > 0 ? Math.min(100, (current / duration) * 100) : 0;
  const who = reviewer ? `voice review by ${reviewer}` : "voice review";

  return (
    <div
      className="flex h-full min-h-[180px] w-full flex-col justify-between rounded-xl border line p-4"
      style={{ background: "var(--bg-elev)" }}
    >
      {src && !failed && <audio ref={audioRef} preload="metadata" src={src} />}

      <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--brand)" }}>
        <span aria-hidden>🎤</span>
        <span>Voice review</span>
      </div>

      {unavailable ? (
        <div className="my-6 text-center">
          <p className="text-sm font-medium">Audio unavailable</p>
          <p className="mt-1 text-xs muted">The recording could not be loaded. The transcript on the left is still complete.</p>
        </div>
      ) : (
        <div className="my-4 flex items-center gap-3">
          <button
            type="button"
            onClick={toggle}
            aria-label={playing ? `Pause ${who}` : `Play ${who}`}
            aria-pressed={playing}
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full transition-transform active:scale-95"
            style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
          >
            {playing ? (
              <svg aria-hidden width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="5" width="4" height="14" rx="1" />
                <rect x="14" y="5" width="4" height="14" rx="1" />
              </svg>
            ) : (
              <svg aria-hidden width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                <path d="M8 5.5v13a1 1 0 0 0 1.5.86l11-6.5a1 1 0 0 0 0-1.72l-11-6.5A1 1 0 0 0 8 5.5Z" />
              </svg>
            )}
          </button>
          <div className="min-w-0 flex-1">
            <input
              type="range"
              min={0}
              max={duration > 0 ? duration : 0}
              step={0.1}
              value={Math.min(current, duration || 0)}
              disabled={duration <= 0}
              aria-label="Seek"
              aria-valuetext={`${fmt(current)} of ${fmt(duration)}`}
              onPointerDown={() => setScrubbing(true)}
              onPointerUp={() => setScrubbing(false)}
              onKeyUp={() => setScrubbing(false)}
              onChange={(e) => seek(Number(e.target.value))}
              className="voice-seek block w-full"
              style={{ "--voice-pct": `${pct}%` } as React.CSSProperties}
            />
            <div className="mt-1.5 flex justify-between text-xs tabular-nums muted" aria-live="off">
              <span>{fmt(current)}</span>
              <span>{duration > 0 ? fmt(duration) : "–:––"}</span>
            </div>
          </div>
        </div>
      )}

      <p className="text-xs muted">Sent as a WhatsApp voice note. Transcribed and summarised by AI; no video, no face check.</p>
    </div>
  );
}
