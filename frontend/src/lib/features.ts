/**
 * Internal feature switches (not viewer settings). Flip a value and reload to try a variant.
 */
export const FEATURES = {
  /** Pop Match Analyst comments up as a bubble beside the insight card on the pitch. Off while
   *  the comments live in the dedicated panel on the right; may come back after testing. */
  analystBubble: false,
} as const;
