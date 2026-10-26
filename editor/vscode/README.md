# CADStudio VS Code extension

Source for the repo-local VS Code extension `danillogical.cadstudio`. The build output lives
in `.vscode/extensions/cadstudio/` and is committed for local workspace installation.
The GUI plan currently follows the browser-first fallback; editor integration remains optional
until its live checks are completed.

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

## Optional manual install

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

Reload or reinstall requirements remain unverified and will be checked during G4/G5.

## H0 findings

On 2026-10-26 the user selected the browser-first fallback and authorized continuing to G1.
Workspace installation, panel rendering and rebuild pickup remain unverified; H0 is recorded
as fallback selected. Keep this extension for the later editor work. A private VSIX will be
an explicit opt-in if workspace installation proves unreliable.

VS Code's [URI-handler API](https://code.visualstudio.com/api/references/vscode-api#window.registerUriHandler)
dispatches URIs to the topmost window when several are open. G5 therefore retains its repo-root
check, acknowledgment and explicit browser fallback for opening a model or run from a terminal.
