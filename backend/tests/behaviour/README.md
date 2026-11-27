# Behaviour tests

Each test here pins down one rule of how osu! coach must behave, in the words a player would use, with the issue it
comes from. They are the specification, not a check of how the code happens to work today.

**Don't change a test here to make it pass.** A failing behaviour test means the code broke a rule: fix the code.
A test here changes only when the rule itself changes, and only with the maintainer's explicit permission (see
"Behaviour tests" in [AGENTS.md](../../../AGENTS.md)); say which rule changed and why in the commit message.

The web app's are in `frontend/src/behaviour/`, and the end-to-end ones in `frontend/e2e/`.
