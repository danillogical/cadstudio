/**
 * `cad gui open` requests, arriving as `vscode://danillogical.cadstudio/open?req=<id>`. The request
 * is claimed from this window's registered service only (never one started for the URI). VS Code
 * hands the URI to the frontmost window, so a window whose folder has no matching service cannot
 * see the request: it warns and leaves `cad gui open` to time out and fall back. A window that can
 * see it either opens the panel on the target and acks, or nacks with the reason.
 */
import {
  openAckRoute,
  openClaimRoute,
  openNackRoute,
  parseNavigateTarget,
  type HttpRoute,
  type NavigateTarget,
  type Reply,
} from "./protocol";

/** Below the CLI's 10 s ack wait, so a slow panel is reported as a nack rather than a timeout. */
export const READY_TIMEOUT_MS = 8_000;

export const NOT_THIS_WINDOW =
  "CADStudio: this window is not the cadstudio repo for that `cad gui open` request; it will fall back to a browser.";

export interface OpenRequestDeps {
  /** This window's workspace folder, canonicalised like the service's repo root; null without one. */
  workspaceRoot: string | null;
  trusted: boolean;
  /** Forward a route to the registered service without starting one; null when none is registered. */
  request(route: HttpRoute): Promise<Reply | null>;
  /** Open or reveal the GUI panel; false when it was refused or could not load. */
  openPanel(): boolean;
  /** Post the navigate message to the panel once its page is ready; false if it never was. */
  navigate(target: NavigateTarget | null): Promise<boolean>;
  warn(message: string): void;
  sleep(ms: number): Promise<void>;
  readyTimeoutMs?: number;
}

export type OpenOutcome =
  | { status: "acked"; target: NavigateTarget | null }
  /** Opened, but the service refused the ack (e.g. the CLI already gave up). */
  | { status: "ack-failed"; target: NavigateTarget | null; reason: string }
  | { status: "nacked"; reason: string }
  /** The request was never reached, so there was nothing to nack. */
  | { status: "unavailable"; reason: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function describe(target: NavigateTarget | null): string {
  if (!target) return "the GUI";
  return "model" in target ? target.model : `run ${target.run}`;
}

/** Claim, check, open, navigate, then ack; every refusal after the claim is a nack with its reason. */
export async function handleOpenRequest(id: string, deps: OpenRequestDeps): Promise<OpenOutcome> {
  if (!deps.workspaceRoot) {
    deps.warn(NOT_THIS_WINDOW);
    return { status: "unavailable", reason: "this window has no workspace folder" };
  }
  const claimed = await deps.request(openClaimRoute(id));
  if (claimed === null) {
    deps.warn(NOT_THIS_WINDOW);
    return { status: "unavailable", reason: "no GUI service is registered for this window's folder" };
  }
  if (!claimed.ok) {
    deps.warn(NOT_THIS_WINDOW);
    return { status: "unavailable", reason: `the service refused the request: ${claimed.error.message}` };
  }

  const body = claimed.result;
  const target = isRecord(body) ? parseNavigateTarget(body.target) : undefined;
  const nack = async (reason: string): Promise<OpenOutcome> => {
    deps.warn(`CADStudio: not opening ${describe(target ?? null)}: ${reason}`);
    await deps.request(openNackRoute(id, reason));
    return { status: "nacked", reason };
  };
  if (!isRecord(body) || typeof body.repoRoot !== "string" || target === undefined) {
    return nack("the open request is malformed");
  }
  if (!deps.trusted) return nack("this workspace is not trusted");
  if (body.repoRoot !== deps.workspaceRoot) {
    return nack(`the request is for ${body.repoRoot}, but this window's folder is ${deps.workspaceRoot}`);
  }
  if (!deps.openPanel()) return nack("the GUI panel could not be opened in this window");
  const timeoutMs = deps.readyTimeoutMs ?? READY_TIMEOUT_MS;
  const posted = await Promise.race([deps.navigate(target), deps.sleep(timeoutMs).then(() => false)]);
  if (!posted) return nack(`the GUI panel did not become ready within ${Math.round(timeoutMs / 1000)} s`);

  const ack = await deps.request(openAckRoute(id));
  if (!ack?.ok) {
    const reason = ack ? ack.error.message : "the GUI service is no longer registered";
    deps.warn(`CADStudio: opened ${describe(target)}, but \`cad gui open\` was not told (${reason}).`);
    return { status: "ack-failed", target, reason };
  }
  return { status: "acked", target };
}
