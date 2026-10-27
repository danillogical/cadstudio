import { TransportError } from "../transport/types";

export type BannerKind = "stale" | "error" | "info";

export interface BannerState {
  kind: BannerKind;
  text: string;
}

export interface BannerInput {
  stale: boolean;
  /** The service's last build (or run) error, when the displayed artifact is stale. */
  sceneError: string | null;
  /** The failure of the last load attempt, if any. */
  loadError: unknown;
  /** What is displayed; defaults to `scene`. A trajectory goes stale when a run fails. */
  subject?: "scene" | "trajectory";
}

/** Decide what the banner says; null means everything is fresh. */
export function bannerFor(input: BannerInput): BannerState | null {
  const subject = input.subject ?? "scene";
  if (input.loadError !== undefined && input.loadError !== null) {
    const error = input.loadError;
    if (error instanceof TransportError) {
      if (error.status === 401) {
        return {
          kind: "error",
          text: "Missing or invalid token; open the URL printed by `cad gui serve`.",
        };
      }
      const command = error.body?.command;
      if (subject === "scene" && error.status === 404 && typeof command === "string") {
        return { kind: "info", text: `No scene yet. Run \`${command}\`.` };
      }
    }
    const message = error instanceof Error ? error.message : String(error);
    return { kind: "error", text: `Could not load the ${subject}: ${message}` };
  }
  if (input.stale) {
    const detail = input.sceneError ? `: ${input.sceneError}` : ".";
    const action = subject === "scene" ? "build" : "run";
    return {
      kind: "stale",
      text: `Showing the last good ${subject}; the latest ${action} failed${detail}`,
    };
  }
  if (subject === "trajectory" && input.sceneError) {
    return { kind: "error", text: `The latest run failed: ${input.sceneError}` };
  }
  return null;
}

/** Paint the banner element, hiding it when there is nothing to say. */
export function renderBanner(container: HTMLElement, state: BannerState | null): void {
  if (!state) {
    container.textContent = "";
    container.hidden = true;
    container.removeAttribute("data-kind");
    return;
  }
  container.hidden = false;
  container.dataset.kind = state.kind;
  container.setAttribute("role", state.kind === "error" ? "alert" : "status");
  container.textContent = state.text;
}
