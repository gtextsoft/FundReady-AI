"""Feature modules.

Each module owns its own `router` / `service` / `repository` / `schemas` /
`models`. Modules never import another module's `repository`, `models`, or other
internals -- they talk only through each other's public `service` functions
(ARCHITECTURE.md section 3).
"""
