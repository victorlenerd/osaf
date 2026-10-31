/** Afefehub mark: a speech bubble holding an "A". Colours follow the theme tokens. */
export default function Logo({ size = 24, className }: { size?: number; className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      className={className}
      aria-hidden
      focusable="false"
    >
      <path
        d="M18 6H46a12 12 0 0 1 12 12v20a12 12 0 0 1-12 12H26L12 60V49A12 12 0 0 1 6 38V18A12 12 0 0 1 18 6Z"
        fill="var(--brand)"
      />
      <path
        d="M21 40 32 16l11 24M25.5 32.5h13"
        fill="none"
        stroke="var(--bg)"
        strokeWidth="5.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
