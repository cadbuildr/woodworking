/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Optional override for JSON/STL kernel-api origin (e.g. http://127.0.0.1:8087 for local kernel-api). */
  readonly VITE_KERNEL_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
