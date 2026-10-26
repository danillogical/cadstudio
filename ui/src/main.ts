import "./style.css";
import { AppController } from "./app/controller";
import { renderBanner } from "./app/banner";
import { BrowserTransport } from "./transport/browser";
import { TransportError } from "./transport/types";
import { Viewport } from "./viewport/viewport";

function element<T extends HTMLElement>(id: string): T {
  const found = document.getElementById(id);
  if (!found) throw new Error(`missing #${id}`);
  return found as T;
}

async function main(): Promise<void> {
  const banner = element("banner");
  const picker = element<HTMLSelectElement>("model-picker");
  const viewportHost = element("viewport");

  const transport = BrowserTransport.fromLocation();
  const viewport = new Viewport(viewportHost);
  const controller = new AppController({
    transport,
    viewport,
    elements: {
      banner,
      tree: element("tree"),
      props: element("props"),
    },
  });
  viewport.onPick = (partId) => controller.selection.set(partId);

  element("fit").addEventListener("click", () => viewport.fit());

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Select a model…";
  picker.appendChild(placeholder);
  picker.disabled = true;

  picker.addEventListener("change", () => {
    const model = picker.value;
    if (model) void controller.loadModel(model);
  });

  const unsubscribe = transport.subscribe((event) => {
    if (event.type === "connection") {
      if (event.state === "error") {
        renderBanner(banner, { kind: "error", text: "Live updates disconnected; retrying…" });
      } else {
        controller.refreshBanner();
      }
      return;
    }
    controller.handleEvent(event);
  });
  globalThis.addEventListener("pagehide", () => {
    unsubscribe();
    controller.dispose();
    viewport.dispose();
  });

  try {
    const health = await transport.health();
    if (health.protocolVersion !== 1) {
      renderBanner(banner, {
        kind: "error",
        text: `Service protocol ${health.protocolVersion} does not match this UI (1).`,
      });
    }
    const models = await transport.listModels();
    picker.replaceChildren(placeholder);
    for (const model of models.models) {
      const option = document.createElement("option");
      option.value = model;
      option.textContent = model;
      picker.appendChild(option);
    }
    picker.disabled = models.models.length === 0;
    if (models.models.length === 1) {
      picker.value = models.models[0];
      await controller.loadModel(models.models[0]);
    }
  } catch (error) {
    const message =
      error instanceof TransportError && error.status === 401
        ? "Missing or invalid token; open the URL printed by `cad gui serve`."
        : error instanceof Error
          ? error.message
          : String(error);
    renderBanner(banner, { kind: "error", text: `Could not reach the GUI service: ${message}` });
  }
}

void main();
