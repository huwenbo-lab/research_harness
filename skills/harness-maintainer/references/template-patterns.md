# Harness Template Patterns Reference

Use this reference when revising Research Harness files, especially agent entry files, shared rules, workflow files, templates, and skills.

## Source patterns

### AGENTS.md

Observed pattern:

- Treat `AGENTS.md` as a predictable README for agents.
- Include only what helps an agent work: project overview, setup commands, code style, testing instructions, security considerations, and unusual project constraints.
- Use nested `AGENTS.md` files when subprojects need different instructions.
- Let explicit user instructions and closer directory instructions override broader instructions.
- Treat the file as living documentation.

Local translation:

- `agent_entries/global/AGENTS.md` should be a short router into the harness, not the full harness.
- Project `AGENTS.md` should explain what to read in this project, not repeat global research principles.

Source:

- https://agents.md/
- https://developers.openai.com/codex/guides/agents-md

### Codex AGENTS.md

Observed pattern:

- Codex layers global, project, and nested guidance.
- Files closer to the current directory appear later and override earlier guidance.
- Codex has a combined guidance size limit, so entry files should stay compact.
- A good setup can be verified by asking Codex to summarize loaded instructions.

Local translation:

- Keep global guidance stable and broad.
- Put project-specific facts in project files.
- If subdirectories later need special instructions, use local `AGENTS.md` or equivalent path-specific rules rather than bloating the root entry.

Source:

- https://developers.openai.com/codex/guides/agents-md

### Claude CLAUDE.md and rules

Observed pattern:

- `CLAUDE.md` files provide persistent context and are loaded into context, but they are not hard enforcement.
- Specific, concise, well-structured instructions work best.
- Claude's official guidance targets under 200 lines per `CLAUDE.md`.
- Multi-step procedures or rules that only matter in one area should move to skills or path-scoped rules.
- If a repository already uses `AGENTS.md`, `CLAUDE.md` can import it and add Claude-specific notes.

Local translation:

- `project_CLAUDE_template.md` should import or point to project `AGENTS.md` if duplication becomes a maintenance problem.
- Keep `CLAUDE.md` focused on reading order, project scope, and tool-specific execution hints.
- Do not use `CLAUDE.md` to store current research history.

Source:

- https://code.claude.com/docs/en/memory
- https://claude.com/blog/how-claude-code-works-in-large-codebases-best-practices-and-where-to-start

### Cursor rules

Observed pattern:

- Project rules live in `.cursor/rules`.
- Each rule is an MDC file with metadata and content.
- Rules can be always-on, auto-attached by file pattern, agent-requested, or manual.
- Good rules are focused, actionable, scoped, and under about 500 lines.
- Large concepts should be split into composable rules.

Local translation:

- Cursor support should be optional, not a default project requirement.
- If added, create a small adapter layer under `agent_entries/cursor/`.
- Do not duplicate the full harness into `.cursor/rules`; use focused rules such as writing blueprint, Stata analysis, or table output.

Source:

- https://docs.cursor.com/context/rules

### Codex skills

Observed pattern:

- Skills use progressive disclosure.
- Codex initially sees only name, description, and path.
- Full `SKILL.md` loads only when the skill is relevant.
- Detailed references should live in reference files and be loaded only when needed.

Local translation:

- Put operational detail in `skills/*/SKILL.md`.
- Keep the skill trigger description clear.
- Move long examples or template cases into `references/`.

Source:

- https://developers.openai.com/codex/skills

### OpenAI prompt engineering

Observed pattern:

- Instructions should be clear and precise.
- Complex tasks should be decomposed.
- Markdown structure helps readability.
- Testing and validation instructions improve reliability.
- Context window planning matters.

Local translation:

- Replace broad slogans with checkable actions.
- Include verification commands or review checks in workflow and skill files.
- Keep startup context small and push long details to on-demand files.

Source:

- https://developers.openai.com/api/docs/guides/prompt-engineering

## Local file-type templates

### Entry file pattern

Use for `AGENTS.md`, `CLAUDE.md`, and agent entry templates:

```markdown
# Agent Entry

## Read First

- ...

## Task Routing

- If the task is literature mapping, read ...
- If the task is analysis, read ...

## Priority

1. User's current instruction
2. Project files
3. Global harness

## Do Not

- ...
```

### Shared rule pattern

Use for `shared_rules/*.md`:

```markdown
# Topic Rule

## Scope

This rule applies when...

## Principles

- Concrete rule
- Concrete rule

## Boundaries

- Put procedures in workflows or skills.
- Put output skeletons in templates.
```

### Workflow pattern

Use for `workflows/*.md`:

```markdown
# Workflow Name

## When to use

## Read first

## Inputs

## Steps

## Outputs

## Stop condition

## Handoff
```

### Template file pattern

Use for `templates/*.md`:

```markdown
# Artifact Name

## Required fields

- [placeholder]

## Optional fields

- [placeholder]

## Notes

- Keep placeholders minimal.
```

### Skill pattern

Use for `skills/*/SKILL.md`:

```markdown
---
name: skill-name
description: What the skill does and when to use it.
---

# skill-name

## Purpose

## Required context

## Workflow

## Checks

## Output
```

Existing local Research Harness skills may not all use YAML frontmatter yet. New maintenance skills should use frontmatter so they can be copied into Codex skill locations later if needed.

