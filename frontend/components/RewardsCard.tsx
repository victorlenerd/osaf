import { PAYOUTS_ENABLED } from "@/lib/constants";
import CurrentRewardsCard from "./CurrentRewardsCard";
import PayoutRewardsCard from "./PayoutRewardsCard";

/** The current rewards scheme until the payout launch, then the Nigeria payout programme. */
export default function RewardsCard() {
  return PAYOUTS_ENABLED ? <PayoutRewardsCard /> : <CurrentRewardsCard />;
}
