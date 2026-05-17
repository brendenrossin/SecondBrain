/**
 * Customize these for your installation.
 *
 * NEXT_PUBLIC_* env vars override at build time (used by the demo deploy).
 * Falls back to your personal defaults for local development.
 *
 * Also update these static files manually if changing for a permanent install:
 *   - frontend/public/manifest.json  (name, short_name)
 *   - frontend/package.json          (name field)
 */
export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "SecondBrain";
export const USER_NAME = process.env.NEXT_PUBLIC_USER_NAME ?? "User";
export const USER_INITIAL = process.env.NEXT_PUBLIC_USER_INITIAL ?? "U";
export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
