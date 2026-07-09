# JOINERY — wood joints demo (Vite + R3F + Pyodide)

Static browser demo of the `cadbuildr_projects.woodworking` library: pick a
joint or a whole assembly, the Python runs in Pyodide, and the CADbuildr
kernel renders the cut + placed boards. Live at
https://cadbuildr.github.io/woodworking/

## Develop

```bash
cd github-io
pnpm install
pnpm run dev
```

The page loads two Python wheels from `public/local-wheels/`:
`cadbuildr-foundation` and this repo's `cadbuildr-projects-woodworking`.
Build them with `uv build` (foundation from PyPI source or the wheel of the
matching release) and copy the `.whl` files into `public/local-wheels/`, or
point `VITE_FOUNDATION_WHEEL_URL` / `VITE_WOODWORKING_WHEEL_URL` at hosted
wheels.

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
