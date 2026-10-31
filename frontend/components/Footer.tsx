import Link from "next/link";
import { REPO_URL } from "@/lib/constants";

export default function Footer() {
  return (
    <footer className="mt-auto border-t line">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-2 px-4 py-6 text-sm muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>
          Built for the <span className="font-medium" style={{ color: "var(--fg)" }}>Meta Global AI Developer Hackathon</span>.
        </p>
        <nav aria-label="Footer" className="flex flex-wrap gap-x-4 gap-y-1">
          <Link href="/about" className="hover:underline">About</Link>
          <Link href="/terms" className="hover:underline">Terms</Link>
          <Link href="/privacy" className="hover:underline">Privacy</Link>
          <a href={REPO_URL || "#"} className="hover:underline" target={REPO_URL ? "_blank" : undefined} rel="noreferrer">
            Open source
          </a>
        </nav>
      </div>
    </footer>
  );
}
