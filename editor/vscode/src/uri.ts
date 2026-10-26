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
