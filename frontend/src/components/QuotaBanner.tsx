import type { RunQuota } from "../api/client";

/**
 * Presentational daily-quota readout shared by the Dashboard and the Job Search
 * form. Quota and concurrency are enforced server-side; this is a convenience
 * display. Unlimited accounts (`remaining === null`) see no daily-cap message.
 */
export interface QuotaBannerProps {
  quota: RunQuota | null;
}

function quotaMessage(quota: RunQuota): string {
  if (quota.remaining === null) {
    return "Unlimited runs on your account.";
  }
  const noun = quota.remaining === 1 ? "run" : "runs";
  return `${quota.remaining} ${noun} left today.`;
}

export function QuotaBanner({ quota }: QuotaBannerProps) {
  if (quota === null) {
    return null;
  }
  return (
    <>
      <p className="text-sm text-muted-foreground">{quotaMessage(quota)}</p>
      {quota.concurrent_blocked && (
        <p className="text-sm text-muted-foreground">
          A run is already running — wait for it to finish.
        </p>
      )}
    </>
  );
}
