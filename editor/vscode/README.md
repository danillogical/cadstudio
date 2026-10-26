# CADStudio VS Code extension

Source for the repo-local VS Code extension `danillogical.cadstudio`. The build output lives
in `.vscode/extensions/cadstudio/` and is committed, so a clean clone lists it under
Workspace Recommendations.

## Prerequisites

- Node.js >= 22
- VS Code >= 1.89 (local workspace extensions)

## Develop

```sh
cd editor/vscode
npm ci
npm test        # tsc --noEmit, then vitest (includes the stale-build guard)
npm run build   # writes ../../.vscode/extensions/cadstudio/
```

Commit `.vscode/extensions/cadstudio/` after every source change; the build test fails when
the committed build differs from a fresh one.

## Manual install

1. Open the repository in VS Code and trust the workspace.
2. Open the Extensions view and find "cadstudio" under **Workspace Recommendations**.
3. Choose **Install Workspace Extension** (VS Code installs it from
   `.vscode/extensions/cadstudio/`; there is no marketplace or global install).
4. Run **CADStudio: Open GUI** from the Command Palette. The panel shows the workspace folder,
   the extension version, the URI query and "Webview script: loaded".

## URI route

```sh
code --open-url "vscode://danillogical.cadstudio/open?x=1"
```

The URI runs the same command and shows `x=1` in the panel.

## Picking up a rebuild

To be confirmed at gate H0.

## H0 findings

Pending gate H0.
