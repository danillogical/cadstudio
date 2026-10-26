import type { Provenance, SceneDoc, ScenePart, Vec3 } from "../transport/types";

function mm(value: number): string {
  return `${value.toFixed(2)} mm`;
}

function size(part: ScenePart): Vec3 {
  return [
    part.bbox.max[0] - part.bbox.min[0],
    part.bbox.max[1] - part.bbox.min[1],
    part.bbox.max[2] - part.bbox.min[2],
  ];
}

function vec(values: Vec3): string {
  return values.map(mm).join(", ");
}

function provenanceRows(provenance: Provenance): Array<[string, string]> {
  const commit = provenance.commit
    ? `${provenance.commit.slice(0, 12)}${provenance.dirty ? " (dirty)" : ""}`
    : "unknown";
  const overrides = Object.entries(provenance.overrides)
    .map(([key, value]) => `${key}=${value}`)
    .join(", ");
  return [
    ["commit", commit],
    ["params", provenance.paramsPath],
    ["sha256", provenance.paramsSha256.slice(0, 12)],
    ["overrides", overrides || "none"],
    ["built", provenance.builtAt],
  ];
}

/** Read-only properties for the selected part plus the model provenance. */
export function renderProps(
  container: HTMLElement,
  doc: SceneDoc,
  partId: string | null,
): void {
  container.replaceChildren();
  const title = document.createElement("h2");
  title.textContent = "Properties";
  container.appendChild(title);

  const part = partId ? doc.parts.find((entry) => entry.id === partId) ?? null : null;
  const rows: Array<[string, string]> = part
    ? [
        ["id", part.id],
        ["name", part.name],
        ["bbox min", vec(part.bbox.min)],
        ["bbox max", vec(part.bbox.max)],
        ["size", vec(size(part))],
        ["volume", `${part.volume.toFixed(2)} mm³ (${(part.volume / 1000).toFixed(2)} cm³)`],
        ["colour", part.color],
      ]
    : [["part", "none selected"]];

  container.appendChild(definitions("part-props", rows));
  const heading = document.createElement("h3");
  heading.textContent = "Provenance";
  container.appendChild(heading);
  container.appendChild(definitions("provenance", provenanceRows(doc.provenance)));
}

function definitions(className: string, rows: Array<[string, string]>): HTMLDListElement {
  const list = document.createElement("dl");
  list.className = className;
  for (const [term, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = value;
    list.append(dt, dd);
  }
  return list;
}
