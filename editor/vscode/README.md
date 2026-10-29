# CADStudio VS Code extension

Source for the repo-local VS Code extension `danillogical.cadstudio`. The build output lives
in `.vscode/extensions/cadstudio/` and is committed for local workspace installation.
The GUI plan currently follows the browser-first fallback; editor integration remains optional
until its live checks are completed.

The extension hosts the same `ui/` bundle the browser uses, in a webview panel:

- **Open GUI** opens the panel, or reveals it if it is already open. A window reload restores it.
- **Assets.** The build copies `ui/dist` into `media/`. The panel loads it through webview URIs
  under a strict CSP: `default-src 'none'`, scripts and the stylesheet only with a per-load nonce,
  `connect-src 'none'`.
- **Service.** The extension host reads `.cadstudio/gui/service.json`. It uses the service only if
  `/v1/health` answers for the same pid and this workspace folder as repo root. Otherwise it runs
  `uv run --frozen --extra physics cad gui serve --no-browser --json` in a "GUI service" task and
  waits up to 180 s for it to register. Closing the panel or the window leaves the service running.
- **Messages.** The webview's `VsCodeTransport` posts each call to the host. The host checks it
  against the transport method list and its argument rules, then forwards it to that call's
  service endpoint. Answers, artifact bytes and SSE events come back as messages. The service
  token stays in the extension host.
- **Trust.** The extension does not run in untrusted workspaces.

## Install

Run `./setup.sh` from the engine root. It builds the UI, packages the extension to
`editor/vscode/cadstudio.vsix` and runs `code --install-extension ... --force`, so the extension
is available in every VS Code window, including your own projects repos. To do it by hand:

```sh
cd ui && npm ci && npm run build
cd ../editor/vscode && npm ci && npm run build && npm run package
code --install-extension cadstudio.vsix --force
```

If `code` is not found, run **Shell Command: Install 'code' command in PATH** from the Command
Palette. Then run **CADStudio: Open GUI**. The first open starts the "GUI service" task if no
service is running for the folder.

## Prerequisites

- Node.js >= 22
- VS Code >= 1.89

## Develop

Developing the extension inside the engine repo uses the committed workspace build instead:

```sh
cd editor/vscode
npm ci
npm test        # tsc --noEmit, then vitest (includes the stale-build guard)
npm run build   # writes ../../.vscode/extensions/cadstudio/
```

Build `ui/` first (`cd ui && npm ci && npm run build`): the extension build copies `ui/dist`
into `media/` and fails if it is missing, and the stale-build guard compares `media/` too.

Commit `.vscode/extensions/cadstudio/` after every source change; the build test fails when
the committed build differs from a fresh one.

To use that workspace build: open the repository in VS Code and trust the workspace, find
"cadstudio" under **Workspace Recommendations** in the Extensions view, and choose
**Install Workspace Extension**.

## URI route

```sh
code --open-url "vscode://danillogical.cadstudio/open?x=1"
```

The URI runs the same command. The query is not used yet; `cad gui open` (G5) will define it.

## Picking up a rebuild

Reload or reinstall requirements remain unverified; gate H4 checks them.

## H0 findings

On 2026-10-26 the user selected the browser-first fallback and authorized continuing to G1.
Workspace installation, panel rendering and rebuild pickup remain unverified; H0 is recorded
as fallback selected. Keep this extension for the later editor work. A private VSIX will be
an explicit opt-in if workspace installation proves unreliable.

VS Code's [URI-handler API](https://code.visualstudio.com/api/references/vscode-api#window.registerUriHandler)
dispatches URIs to the topmost window when several are open. G5 therefore retains its repo-root
check, acknowledgment and explicit browser fallback for opening a model or run from a terminal.
