# CADStudio VS Code extension

This workspace extension hosts the CADStudio GUI (the built `ui/` bundle, copied into `media/`)
in a VS Code webview. "CADStudio: Open GUI" opens the panel, or reveals it if it is already open,
and the panel comes back after a window reload.

The webview has no network access. The extension finds the workspace's GUI service through
`.cadstudio/gui/service.json`, starts `cad gui serve` in a task when none is running, and forwards the
panel's requests and live updates itself; the service token never reaches the webview.

The extension does not run in untrusted workspaces. It is built from `editor/vscode/`; see
`editor/vscode/README.md` in the repository for the build and manual install steps.
