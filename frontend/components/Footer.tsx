import Link from "next/link";
import { REPO_URL } from "@/lib/constants";

export default function Footer() {
  return (
    <footer className="mt-auto border-t line">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-2 px-4 py-6 text-sm muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>
          Built with <span aria-label="love" role="img">❤️</span> by{" "}
          <a href="https://1ctech.ca" target="_blank" rel="noreferrer" className="font-medium hover:underline" style={{ color: "var(--fg)" }}>
            1CTECH
          </a>
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
