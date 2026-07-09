import React from "react";
import ReactDOM from "react-dom/client";
import { type KernelDag } from "@cadbuildr/cad-kernel-r3f";
import {
  initializeCadPyodideRuntime,
  runCadPythonCode,
  type PyodideLike,
} from "@cadbuildr/cad-pyodide-runtime";
import {
  CadbuildrProvider,
  CadbuildrViewer,
  getPartKey,
  type SerializedMeshPayload,
} from "@cadbuildr/sdk-react";

import { resolveKernelApiBaseUrl } from "./kernelApiEnv";
import {
  FOUNDATION_WHEEL_FILE,
  LOCAL_WHEELS_URL_SEGMENT,
  WOODWORKING_WHEEL_FILE,
} from "./wheels";
import examplesManifest from "./examples.json";
import "./styles.css";

const DEMO_LOG = "[wood-joints-demo]";

function demoLog(message: string, detail?: Record<string, unknown> | null): void {
  if (detail != null) {
    console.info(DEMO_LOG, message, detail);
  } else {
    console.info(DEMO_LOG, message);
  }
}

function demoError(message: string, detail?: unknown): void {
  console.error(DEMO_LOG, message, detail);
}

type DemoExample = {
  id: string;
  title: string;
  description: string;
  python: string;
  group?: string;
};

const EXAMPLES: DemoExample[] = examplesManifest.examples;
const JOINTS = EXAMPLES.filter((e) => e.group !== "assembly");
const ASSEMBLIES = EXAMPLES.filter((e) => e.group === "assembly");

const FOUNDATION_IMPORT_PATH = "cadbuildr.foundation";
const FOUNDATION_DAG_UTILS_PATH = `${FOUNDATION_IMPORT_PATH}.dag_utils`;
const WOODWORKING_IMPORT_PATH = "cadbuildr_projects.woodworking";

function localWheelUrl(fileName: string): string {
  return new URL(
    `${LOCAL_WHEELS_URL_SEGMENT}/${fileName}`,
    window.location.origin + import.meta.env.BASE_URL
  ).href;
}

function resolveFoundationWheelUrl(): string {
  const fromEnv = (import.meta.env.VITE_FOUNDATION_WHEEL_URL as string | undefined)?.trim();
  return fromEnv || localWheelUrl(FOUNDATION_WHEEL_FILE);
}

function resolveWoodworkingWheelUrl(): string {
  const fromEnv = (import.meta.env.VITE_WOODWORKING_WHEEL_URL as string | undefined)?.trim();
  return fromEnv || localWheelUrl(WOODWORKING_WHEEL_FILE);
}

/** Viewer scene background: warm paper, matching the poster page. */
const SCENE_BG = "#f2f0e9";

/** Foundation / kernel STLs are Z-up; R3F is Y-up. */
const MESH_SCENE_POSITION: [number, number, number] = [0, 0, 0];
const CAD_Z_UP_TO_Y_UP: [number, number, number] = [-Math.PI / 2, 0, 0];

/** Pyodide runtime patches `builtins.show`; rebind foundation exports so
 *  `from … import show` still captures the DAG. */
function buildFoundationShowRebindScript(): string {
  return `
import builtins
from importlib import import_module

_root = import_module(${JSON.stringify(FOUNDATION_IMPORT_PATH)})
_dag_utils = import_module(${JSON.stringify(FOUNDATION_DAG_UTILS_PATH)})
_hook = builtins.show
_root.show = _hook
_dag_utils.show = _hook
`.trim();
}

function buildWheelInstallScript(wheelUrl: string, importPath: string): string {
  return `
import importlib
import micropip

try:
    importlib.import_module(${JSON.stringify(importPath)})
except Exception:
    await micropip.install(${JSON.stringify(wheelUrl)}, deps=False)
    importlib.import_module(${JSON.stringify(importPath)})
`.trim();
}

function TileGrid({
  title,
  examples,
  activeId,
  onSelect,
}: {
  title: string;
  examples: DemoExample[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <section className="poster-section">
      <h2 className="poster-section-title">{title}</h2>
      <div className="poster-grid">
        {examples.map((example) => (
          <button
            key={example.id}
            type="button"
            className={`poster-tile ${example.id === activeId ? "active" : ""}`}
            onClick={() => onSelect(example.id)}
          >
            <span className="poster-tile-title">{example.title}</span>
            <span className="poster-tile-code">
              {example.python.split("import ").pop()?.split("\n")[0]}
            </span>
            <span className="poster-tile-description">{example.description}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function App() {
  const [activeId, setActiveId] = React.useState<string | null>(null);
  const [dag, setDag] = React.useState<KernelDag | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [runtimeReady, setRuntimeReady] = React.useState(false);
  const [showCode, setShowCode] = React.useState(false);
  const [xray, setXray] = React.useState(false);
  const [meshPayload, setMeshPayload] = React.useState<SerializedMeshPayload | null>(null);
  const [hiddenParts, setHiddenParts] = React.useState<string[]>([]);
  const pyodideRef = React.useRef<PyodideLike | null>(null);
  const runCounterRef = React.useRef(0);
  const viewerRef = React.useRef<HTMLDivElement | null>(null);

  const activeExample = EXAMPLES.find((e) => e.id === activeId) ?? null;

  const kernelApiBaseUrl = resolveKernelApiBaseUrl();
  const keyId = (import.meta.env.VITE_CADBUILDR_KEY_ID as string | undefined)?.trim();
  const sessionToken = (
    import.meta.env.VITE_CADBUILDR_SESSION_TOKEN as string | undefined
  )?.trim();
  const viewerConfigured = Boolean(keyId || sessionToken);

  React.useEffect(() => {
    let cancelled = false;

    async function bootstrapRuntime() {
      try {
        demoLog("bootstrap: initializing Pyodide runtime");
        const pyodide = await initializeCadPyodideRuntime({
          packages: {
            foundation: "*",
            foundationPackageName: resolveFoundationWheelUrl(),
          },
          foundationImportPath: FOUNDATION_IMPORT_PATH,
        });
        if (cancelled) {
          return;
        }

        await pyodide.runPythonAsync(buildFoundationShowRebindScript());
        await pyodide.runPythonAsync(
          buildWheelInstallScript(resolveWoodworkingWheelUrl(), WOODWORKING_IMPORT_PATH)
        );
        if (cancelled) {
          return;
        }

        pyodideRef.current = pyodide;
        setRuntimeReady(true);
        demoLog("bootstrap: ready", {
          foundationWheel: resolveFoundationWheelUrl(),
          woodworkingWheel: resolveWoodworkingWheelUrl(),
          kernelApiBaseUrl,
        });
      } catch (runtimeError) {
        if (cancelled) {
          return;
        }
        const message = runtimeError instanceof Error ? runtimeError.message : String(runtimeError);
        demoError("bootstrap failed", runtimeError);
        setError(message);
      }
    }

    void bootstrapRuntime();
    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    if (!activeExample) {
      return;
    }
    if (!runtimeReady || !pyodideRef.current) {
      return;
    }

    const runId = ++runCounterRef.current;
    let cancelled = false;

    async function runExample() {
      try {
        setError(null);
        setDag(null);
        demoLog("runExample: executing Python", { runId, activeId });

        const result = await runCadPythonCode(
          pyodideRef.current as PyodideLike,
          (activeExample as DemoExample).python,
          {
            foundationImportPath: FOUNDATION_IMPORT_PATH,
            foundationDagUtilsPath: FOUNDATION_DAG_UTILS_PATH,
          }
        );

        if (cancelled || runId !== runCounterRef.current) {
          return;
        }
        setDag((result.dag as KernelDag | null) ?? null);
      } catch (runError) {
        if (cancelled || runId !== runCounterRef.current) {
          return;
        }
        const message = runError instanceof Error ? runError.message : String(runError);
        demoError("runExample: Python failed", runError);
        setError(message);
      }
    }

    void runExample();

    return () => {
      cancelled = true;
    };
  }, [activeExample, activeId, runtimeReady]);

  const selectExample = (id: string) => {
    setActiveId(id);
    setHiddenParts([]);
    // The viewer lives right under the header — bring it into view.
    requestAnimationFrame(() => {
      viewerRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  };

  const closeViewer = () => {
    setActiveId(null);
    setDag(null);
    setError(null);
    setMeshPayload(null);
    setHiddenParts([]);
  };

  const toggleHidden = (key: string) => {
    setHiddenParts((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  };

  const partEntries = React.useMemo(() => {
    const instances = meshPayload?.partInstances ?? [];
    return instances.map((instance, index) => {
      const storeEntry = meshPayload?.store?.[instance.hash];
      return {
        key: getPartKey(instance, index),
        label: instance.name || instance.path || `part ${index + 1}`,
        color: instance.color ?? storeEntry?.data?.color,
      };
    });
  }, [meshPayload]);

  const busy = activeExample && !dag && !error;

  return (
    <div className="poster-shell">
      <header className="poster-header">
        <h1>J O I N E R Y</h1>
        <p>
          Classic wood joints as CADbuildr code — each interface places the
          boards <em>and</em> cuts them. Pick a joint or a whole assembly and
          it takes shape right here.
        </p>
      </header>

      {activeExample ? (
        <div className="viewer-card" ref={viewerRef}>
          <div className="viewer-card-header">
            <div className="viewer-card-heading">
              <h2>{activeExample.title}</h2>
              <p>{activeExample.description}</p>
            </div>
            <div className="viewer-card-controls">
              <button
                type="button"
                className={`pill-button ${xray ? "active" : ""}`}
                onClick={() => setXray(!xray)}
              >
                X-ray
              </button>
              <button
                type="button"
                className={`pill-button ${showCode ? "active" : ""}`}
                onClick={() => setShowCode(!showCode)}
              >
                {"{ } Code"}
              </button>
              <button
                type="button"
                className="pill-button"
                onClick={closeViewer}
                aria-label="Close viewer"
              >
                ✕
              </button>
            </div>
          </div>

          <div className="viewer-card-stage">
            {error ? (
              <div className="viewer-overlay" role="alert">
                <pre>{error}</pre>
              </div>
            ) : null}
            {!runtimeReady && !error ? (
              <div className="viewer-overlay" role="status">
                <span>Warming up the Python runtime…</span>
              </div>
            ) : null}
            {runtimeReady && busy ? (
              <div className="viewer-overlay" role="status">
                <span>Cutting the joinery…</span>
              </div>
            ) : null}
            {viewerConfigured ? (
              <CadbuildrProvider
                baseUrl={kernelApiBaseUrl}
                keyId={keyId}
                sessionToken={sessionToken}
                projectKey="wood-joints"
              >
                <CadbuildrViewer
                  dag={dag}
                  background={SCENE_BG}
                  cameraPosition={[420, 320, 420]}
                  fov={40}
                  xray={xray}
                  autoFit
                  hiddenParts={hiddenParts}
                  onMeshPayload={setMeshPayload}
                  meshPosition={MESH_SCENE_POSITION}
                  meshRotation={CAD_Z_UP_TO_Y_UP}
                  onRender={(meta) => {
                    demoLog("CadbuildrViewer: render ready", meta);
                    setError(null);
                  }}
                  onError={(meshError) => {
                    demoError("CadbuildrViewer: render failed", meshError);
                    setError(meshError.message);
                  }}
                />
              </CadbuildrProvider>
            ) : (
              <div className="viewer-overlay" role="alert">
                <pre>
                  Viewer not configured: set VITE_CADBUILDR_KEY_ID (publishable
                  partner key) or VITE_CADBUILDR_SESSION_TOKEN in .env — see
                  .env.example.
                </pre>
              </div>
            )}
            {partEntries.length > 0 ? (
              <aside className="parts-panel">
                <h3>Parts</h3>
                <ul>
                  {partEntries.map((part) => {
                    const hidden = hiddenParts.includes(part.key);
                    return (
                      <li key={part.key}>
                        <button
                          type="button"
                          className={`parts-row ${hidden ? "hidden" : ""}`}
                          onClick={() => toggleHidden(part.key)}
                          title={hidden ? "Show part" : "Hide part"}
                        >
                          <span
                            className="parts-swatch"
                            style={{
                              background: part.color
                                ? `rgb(${part.color.map((c) => Math.round(c * 255)).join(",")})`
                                : "#a8b0c0",
                            }}
                          />
                          <span className="parts-name">{part.label}</span>
                          <span className="parts-eye">{hidden ? "○" : "●"}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </aside>
            ) : null}
          </div>

          {showCode ? <pre className="viewer-card-code">{activeExample.python}</pre> : null}
        </div>
      ) : null}

      <TileGrid title="Joints" examples={JOINTS} activeId={activeId} onSelect={selectExample} />
      <TileGrid
        title="Assemblies"
        examples={ASSEMBLIES}
        activeId={activeId}
        onSelect={selectExample}
      />

      <footer className="poster-footer">
        <span>cadbuildr · woodworking library</span>
        {!runtimeReady && !error ? <span> — loading Python runtime…</span> : null}
      </footer>
    </div>
  );
}

// Avoid StrictMode: dev double-mount fires duplicate kernel-api renders.
ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(<App />);
