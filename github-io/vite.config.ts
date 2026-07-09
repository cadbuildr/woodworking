import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

import {
  FOUNDATION_WHEEL_FILE,
  LOCAL_WHEELS_URL_SEGMENT,
  WOODWORKING_WHEEL_FILE,
} from "./src/wheels";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** Dev-only: stream the wheels from each package's `dist/` (run `uv build` there,
 *  or `pnpm run sync-wheels` once). */
function serveLocalWheelsFromDist(): Plugin {
  const wheelSources: Record<string, string> = {
    [FOUNDATION_WHEEL_FILE]: path.resolve(
      __dirname,
      "../../../cadbuildr/foundation/dist",
      FOUNDATION_WHEEL_FILE
    ),
    [WOODWORKING_WHEEL_FILE]: path.resolve(__dirname, "..", "dist", WOODWORKING_WHEEL_FILE),
  };
  return {
    name: "serve-local-wheels-from-dist",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const pathname = req.url?.split("?")[0] ?? "";
        const match = Object.keys(wheelSources).find((file) =>
          pathname.endsWith(`/${LOCAL_WHEELS_URL_SEGMENT}/${file}`)
        );
        if (!match) {
          next();
          return;
        }
        const wheelPath = wheelSources[match];
        if (!fs.existsSync(wheelPath)) {
          res.statusCode = 404;
          res.setHeader("Content-Type", "text/plain; charset=utf-8");
          res.end(
            `Missing wheel at ${wheelPath}.\nRun: uv build in that Python package directory (or pnpm run sync-wheels here).`
          );
          return;
        }
        res.setHeader("Content-Type", "application/octet-stream");
        fs.createReadStream(wheelPath).pipe(res);
      });
    },
  };
}

export default defineConfig({
  base: (process.env.VITE_APP_BASE_PATH as string | undefined) ?? "/",
  plugins: [react(), serveLocalWheelsFromDist()],
  server: {
    host: "0.0.0.0",
    port: 3008,
  },
  build: {
    outDir: "dist",
  },
});
