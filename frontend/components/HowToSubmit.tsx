import { WHATSAPP_NUMBER } from "@/lib/constants";
import WhatsAppIcon from "./WhatsAppIcon";

export default function HowToSubmit({ compact = false }: { compact?: boolean }) {
  const number = WHATSAPP_NUMBER || "+000 000 000 0000";
  const waHref = WHATSAPP_NUMBER ? `https://wa.me/${WHATSAPP_NUMBER.replace(/[^\d]/g, "")}` : undefined;
  return (
    <section className="card overflow-hidden" aria-labelledby="howto-title">
      <div className={compact ? "p-4 sm:p-5" : "p-5 sm:p-8"}>
        <h2 id="howto-title" className="font-display text-xl font-semibold sm:text-2xl" style={{ color: "var(--brand)" }}>
          Reviewed a place on camera, or just want to tell us?
        </h2>
        <ol className="mt-4 grid gap-4 sm:grid-cols-3">
          {[
            { n: 1, t: "Post a public reel", d: "Film yourself talking about the business and post it publicly on Instagram." },
            { n: 2, t: "Send us the link, or a voice note", d: "WhatsApp the reel link to the Afefehub number. Did not film? A voice note describing your visit works too. No app, no sign-up." },
            { n: 3, t: "We do the rest", d: "Our agent checks a reel is a real face, transcribes the video or voice note, and adds it to the business page." },
          ].map((s) => (
            <li key={s.n} className="flex gap-3">
              <span
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full font-display text-sm font-bold"
                style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
              >
                {s.n}
              </span>
              <div>
                <p className="font-semibold">{s.t}</p>
                <p className="mt-0.5 text-sm muted">{s.d}</p>
              </div>
            </li>
          ))}
        </ol>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <span className="text-sm muted">Afefehub WhatsApp:</span>
          {waHref ? (
            <a
              href={waHref}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-full py-2 pl-3 pr-4 text-sm font-semibold"
              style={{ background: "#25D366", color: "#062b14" }}
              aria-label={`Chat with Afefehub on WhatsApp, ${number}`}
            >
              <WhatsAppIcon size={18} />
              {number}
            </a>
          ) : (
            <code className="rounded-full border line px-4 py-2 text-sm font-semibold">{number}</code>
          )}
          {!WHATSAPP_NUMBER && <span className="text-xs italic muted">(number coming soon)</span>}
        </div>
      </div>
    </section>
  );
}
