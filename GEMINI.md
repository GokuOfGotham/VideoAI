# VideoAI project instructions

Read AGENTS.md and PRODUCTION_RULES.md before any production. Load the canonical videoai_policy/policy.json for the shared editing, sound and analytics defaults. Use `python policy_tool.py prompt` when passing work to another model, and `python policy_tool.py check <plan.json>` before final production. Existing explicit user choices override defaults; record them without asking again.
