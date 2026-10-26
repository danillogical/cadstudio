import type { SceneDoc } from "../transport/types";
import type { Selection } from "./selection";

/**
 * Render the part list; clicking an item selects it. Text only, never innerHTML.
 * Returns the selection subscription so a re-render can drop the old one.
 */
export function renderTree(
  container: HTMLElement,
  doc: SceneDoc,
  selection: Selection,
): () => void {
  container.replaceChildren();
  const list = document.createElement("ul");
  list.className = "part-tree";
  list.setAttribute("role", "tree");
  list.setAttribute("aria-label", "Parts");

  const items = new Map<string, HTMLLIElement>();
  for (const part of doc.parts) {
    const item = document.createElement("li");
    item.className = "part";
    item.setAttribute("role", "treeitem");
    item.dataset.partId = part.id;
    item.tabIndex = 0;

    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = part.color;
    swatch.setAttribute("aria-hidden", "true");

    const label = document.createElement("span");
    label.className = "part-name";
    label.textContent = part.name || part.id;

    item.append(swatch, label);
    const activate = () => selection.set(part.id);
    item.addEventListener("click", activate);
    item.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        activate();
      }
    });
    items.set(part.id, item);
    list.appendChild(item);
  }
  container.appendChild(list);

  const apply = (id: string | null) => {
    for (const [partId, item] of items) {
      const selected = partId === id;
      item.setAttribute("aria-selected", String(selected));
      item.classList.toggle("selected", selected);
      if (selected) item.scrollIntoView?.({ block: "nearest" });
    }
  };
  apply(selection.get());
  return selection.onChange(apply);
}
