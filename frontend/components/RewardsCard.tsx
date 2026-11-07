import { PAYOUTS_ENABLED } from "@/lib/constants";
import PayoutRewardsCard from "./PayoutRewardsCard";

/** The Nigeria payout programme: announced as coming soon until the launch switch is on. */
export default function RewardsCard() {
  return <PayoutRewardsCard comingSoon={!PAYOUTS_ENABLED} />;
}
