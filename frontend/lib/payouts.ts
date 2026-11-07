/**
 * Copy for the Nigeria payout programme, shared by the home page card and /payouts.
 * The numbers mirror the backend (`app/config.py`, `app/rewards/rules.py`) and the Terms.
 */
import { NGN_PER_POINT, PAYOUT_POOLS, POINTS, WEEKLY_REVIEW_LIMIT } from "./constants";

export { NGN_PER_POINT, PAYOUT_POOLS, POINTS, WEEKLY_REVIEW_LIMIT };

/** Days a reviewer has to reply ENTER, and to send an Instagram verification code (backend payout_offer_days, ig_code_days). */
export const OFFER_DAYS = 7;
export const CODE_DAYS = 7;
export const AFEFEHUB_IG = "afefehub";

export const naira = (n: number) => `₦${Math.round(n).toLocaleString("en-NG")}`;

export const TIERS: { points: number; title: string; detail: string; featured?: boolean }[] = [
  { points: POINTS.voice, title: "Voice note", detail: "Talk us through your visit on WhatsApp." },
  { points: POINTS.reelOther, title: "Someone else’s reel", detail: "We can still publish it, but it earns no points." },
  {
    points: POINTS.reelAuthor,
    title: "Your own reel",
    detail: `We send you a code; DM it to @${AFEFEHUB_IG} from the account that posted it.`,
    featured: true,
  },
];

/** A worked pro-rata example for one busy month in a ₦1,000,000 pool. */
export const PRO_RATA_EXAMPLE = { points: 1_250, pool: 1_000_000 } as const;
