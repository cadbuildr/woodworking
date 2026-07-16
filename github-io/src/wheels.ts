/** Wheel filenames from `uv build` in each Python package root; keep versions in sync.
 *  Foundation installs from PyPI — FOUNDATION_WHEEL_FILE exists only for the
 *  dev-time override (VITE_FOUNDATION_WHEEL_URL) when hacking on foundation
 *  itself; it is never bundled into a deployed build. */
export const FOUNDATION_WHEEL_FILE = "cadbuildr_foundation-0.2.13-py3-none-any.whl";
export const WOODWORKING_WHEEL_FILE =
  "cadbuildr_woodworking-0.1.0-py3-none-any.whl";

/** URL path segment (under Vite `base`, e.g. `/repo/local-wheels/...` on GitHub Pages). */
export const LOCAL_WHEELS_URL_SEGMENT = "local-wheels";
