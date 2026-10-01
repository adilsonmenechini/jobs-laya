# CLAUDE.md

## Core Principles

- **Simplicity First:** Make every change as simple as possible. Minimal surface area and impact on existing code.
- **Root-Cause Focus:** No temporary band-aids or superficial fixes. Debug deeply and solve at the root.
- **High Standards:** Act with Staff-level engineering rigor, ownership, and zero tolerance for laziness.

## Workflow Orchestration

### 1. Plan Mode Default

- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions).
- If something goes sideways, STOP and re-plan immediately — don't keep pushing.
- Use plan mode for verification steps, not just building.
- Write detailed specs upfront to reduce ambiguity.

### 2. Subagent Strategy

- Use subagents liberally to keep the main context window clean.
- Offload research, exploration, and parallel analysis to subagents.
- For complex problems, throw more compute at it via subagents.
- One task per subagent for focused execution.

### 3. Self-Improvement Loop

- After ANY correction from the user: update `plan/tasks/lessons-<YYYYMMDDHHmm>.md` with the pattern.
- Write rules for yourself that prevent the same mistake.
- Ruthlessly iterate on these lessons until mistake rate drops.
- Review lessons at session start for the relevant project.

### 4. Verification Before Done

- Never mark a task complete without proving it works.
- Diff behavior between main and your changes when relevant.
- Ask yourself: "Would a Staff engineer approve this?"
- Run tests, check logs, and demonstrate correctness.

### 5. Demand Elegance (Balanced)

- For non-trivial changes: pause and ask, "Is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution."
- Skip this for simple, obvious fixes — don't over-engineer.
- Challenge your own work before presenting it.

### 6. Autonomous Bug Fixing

- When given a bug report: just fix it. Don't ask for hand-holding.
- Point at logs, errors, and failing tests — then resolve them.
- Zero context switching required from the user.
- Go fix failing CI tests without being told how.

### 7. AI Memory & Session Tracking

- **Always use AI Memory** for project memory, context, decisions, lessons, and relevant persistent knowledge.
- Follow the AI Memory documentation and workflow: https://github.com/akitaonrails/ai-memory/tree/main/docs
- Before starting relevant work, check existing AI Memory context instead of assuming prior decisions or rediscovering information.
- After meaningful corrections, architectural decisions, discoveries, or reusable lessons, update the AI Memory accordingly.
- Keep project memory organized, concise, and focused on information that will be useful in future sessions.

## Task & Session Management

1. **Plan First:** Write the spec to `plan/sdd/spec-<YYYYMMDDHHmm>.md` and the tasks to `plan/tasks/todo-<YYYYMMDDHHmm>.md` with checkable items.
2. **Verify Plan:** Check in before starting implementation.
3. **Track Progress:** Mark items complete as you go.
4. **Explain Changes:** Provide a high-level summary at each step.
5. **Document Results:** Add a review section to `plan/tasks/todo-<YYYYMMDDHHmm>.md`.
6. **Capture Lessons:** Update `plan/tasks/lessons-<YYYYMMDDHHmm>.md` and AI Memory after corrections.
7. **Save Session:** Before finishing or switching tasks, save session logs, summary, and status to `plan/sessions/session-<YYYYMMDDHHmm>.md`.

### 8. Development Flow (SPEC → TDD → TASK → CODING → REFACTOR → LINTER → SAFETY → SESSION)

For any non-trivial task (3+ steps or architectural decisions), strictly follow this sequential flow:

1. **SPEC:** Define requirements, constraints, assumptions, and acceptance criteria.
   - Save to: `plan/sdd/spec-<YYYYMMDDHHmm>.md`
2. **TDD:** Write or update tests expressing expected behaviors and edge cases *before* implementing.
3. **TASK:** Break work into small, checkable items.
   - Save to: `plan/tasks/todo-<YYYYMMDDHHmm>.md`
4. **CODING:** Implement the minimal correct solution to satisfy specs and tests.
5. **REFACTOR:** Clean up code structure, duplication, and readability without changing behavior.
6. **LINTER:** Run formatters, linters, static analysis, and type checkers. Fix issues directly — never suppress without justification.
7. **SAFETY:** Audit security, input validation, permissions, data handling, and destructive operations.
8. **SESSION:** Summarize changes made, test results, decisions taken, and remaining items.
   - Save to: `plan/sessions/session-<YYYYMMDDHHmm>.md`

### File Naming Rules

- Timestamps must follow 24h format: `YYYYMMDDHHmm` (e.g., `202610011234`).
- SPEC, TASK, and SESSION files created for the same iteration **must share the exact same timestamp**.
- **Forbidden filenames:** Never use generic paths like `tasks/todo.md`, `spec.md`, or `session.md`. Always create new timestamped files for new iterations.
