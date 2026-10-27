import { OPEN_REQUEST_ID } from "./protocol";

export const OPEN_PATH = "/open";

export interface OpenUri {
  query: string;
}

// Only the /open route is ours; everything else is reported as unsupported.
export function parseOpenUri(uri: { path: string; query: string }): OpenUri | undefined {
  const path = uri.path.endsWith("/") ? uri.path.slice(0, -1) : uri.path;
  if (path !== OPEN_PATH) return undefined;
  return { query: uri.query };
}

/**
 * The `req=<id>` of a `cad gui open` URI: undefined when there is none (the plain open route),
 * null when it is present but malformed or repeated.
 */
export function parseOpenRequestId(query: string): string | null | undefined {
  const values = new URLSearchParams(query).getAll("req");
  if (values.length === 0) return undefined;
  if (values.length > 1 || !OPEN_REQUEST_ID.test(values[0])) return null;
  return values[0];
}
