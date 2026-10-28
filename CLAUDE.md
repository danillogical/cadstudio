@AGENTS.md

## Claude Code

- Starting the GUI service binds a loopback port. If your Claude Code sandbox blocks that (the error ends in `PermissionError: [Errno 1] Operation not permitted`), rerun the command once outside the sandbox, or ask the user to run it in their terminal. Later `cad gui open` calls reuse the running service.
- The `code` CLI must be reachable from the sandbox for `cad gui open` (VS Code route) and the `connect-ide` skill. If it is not, the command falls back to the browser or exits 3. Don't change sandbox or allowlist settings without the user's go-ahead.
- Bash runs under zsh on macOS. Capture exit codes with `$?` right after the command, and use `$pipestatus` for pipelines.
