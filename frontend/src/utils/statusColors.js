import { tokens } from "../styles/tokens";

// Invoice-status → colour, aligned with the Badge dot colours used across the app.
export const STATUS_COLORS = {
  draft: tokens.color.neutral[400],
  pending_processing: tokens.color.status.pending.base,
  validated: tokens.color.status.info.base,
  pending_approval: tokens.color.status.warning.base,
  approved: tokens.color.status.success.base,
  rejected: tokens.color.status.danger.dark,
  exception: tokens.color.status.danger.base,
  parked: "#7CAF83",  // muted sage green — softer than approved's emerald
  posted: tokens.color.status.posted.base,
};
