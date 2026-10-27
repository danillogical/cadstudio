import { isModelSpec, isRunId, type NavigateTarget } from "../transport/messages";

/** A browser page's `?model=` or `?run=` (as `cad gui open` writes them); null when neither is valid. */
export function targetFromSearch(search: string): NavigateTarget | null {
  const params = new URLSearchParams(search);
  const model = params.get("model");
  if (model !== null) return isModelSpec(model) ? { model } : null;
  const run = params.get("run");
  if (run !== null) return isRunId(run) ? { run } : null;
  return null;
}
