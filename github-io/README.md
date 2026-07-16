# JOINERY — wood joints demo (Vite + R3F + Pyodide)

Static browser demo of the `cadbuildr.woodworking` library: pick a
joint or a whole assembly, the Python runs in Pyodide, and the CADbuildr
kernel renders the cut + placed boards. Live at
https://cadbuildr.github.io/woodworking/

## Develop

```bash
cd github-io
pnpm install
pnpm run dev
```

At runtime the page installs `cadbuildr-foundation` **from PyPI** (pinned in
`src/main.tsx`) and loads this repo's own `cadbuildr-woodworking`
wheel from `public/local-wheels/` (`pnpm run sync-wheels` builds and copies
it). Never bundle a locally-built foundation wheel — release foundation to
PyPI first, then bump the pin. `VITE_FOUNDATION_WHEEL_URL` exists only as a
dev override while hacking on foundation itself.

Viewer auth (see `.env.example`): set `VITE_CADBUILDR_KEY_ID` (publishable
partner key, origin-checked) or `VITE_CADBUILDR_SESSION_TOKEN`.

## Deploy (GitHub Pages)

```bash
VITE_APP_BASE_PATH=/woodworking/ pnpm run build
# publish dist/ to the gh-pages branch
```

The example snippets live in `src/examples.json`; the Python test suite
(`tests/test_demo_examples.py`) executes every snippet verbatim, so a broken
demo snippet fails CI before it breaks the page.
