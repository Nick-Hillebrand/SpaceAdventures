# How to Use Claude Code Efficiently on This Project

Strategy for implementing the Space Adventures v2 roadmap on an **Anthropic Pro
subscription** (5-hour rolling window + weekly usage limits) with Claude Code
and agent-deck — optimizing for code quality, functionality, and quota.

The project's biggest advantage: v2 is already broken into numbered steps with
per-step spec files in `Architecture/`, and `CLAUDE.md` tells the agent to load
only the specs for the current step. That spec quality is the main lever —
everything below builds on it.

---

## TL;DR

- Run **one focused Sonnet session per roadmap step**, plan mode first,
  `/clear` between steps.
- Use **Haiku only for mechanical work** (i18n keys, boilerplate-to-pattern,
  search subagents).
- **Skip agent teams** — on a Pro plan they drain the shared quota faster
  without adding any.
- **Don't use Fable / Opus with 1M context for implementation grind** — it's
  the most expensive tier and exhausts the window fastest. Reserve it for
  planning and hard debugging.

---

## How the limits actually burn

The 5-hour and weekly limits are token-based. Three things dominate
consumption — model choice is only one of them:

1. **Context size per request.** Every turn resends the whole conversation. A
   long meandering session burns quota roughly quadratically. `/clear` between
   steps matters more than which model you pick.
2. **Model tier.** Haiku consumes roughly a third of Sonnet's quota per token;
   Opus/Fable several times more. Long-context variants (`[1m]`) make it worse
   for step-by-step implementation work.
3. **Duplication.** Every subagent or parallel session re-reads `CLAUDE.md`,
   specs, and code from scratch. That's the hidden cost of "agent teams."

---

## Model assignment

| Work | Model | Why |
|---|---|---|
| Step planning, architecture decisions, security steps (spec `10`/`25`), worker/locking (spec `17`) | Opus/Fable, plan mode | A wrong plan costs far more tokens in rework than the planning session costs. Correctness-critical code shouldn't be downgraded. |
| Implementing a well-specified step | **Sonnet (default workhorse)** | The specs are detailed enough that Sonnet executes them reliably at ~⅓–½ the quota of Opus. This is where 80% of the tokens go, so this is where tier matters. |
| i18n keys across six locales, test boilerplate following an existing pattern, renames, lint/format fixes, docs | Haiku | Genuinely cheaper and good enough. **Not** for anything touching auth, subscriptions, or coverage-gated logic — a subtly wrong Haiku change costs more to find and fix than it saved. |
| Explore/search subagents | Haiku | Fan-out file searching doesn't need intelligence; subagents are where cheap models pay off most. |

Haiku is a scalpel, not a strategy. The bigger win is Sonnet-by-default plus
context discipline.

---

## Agent teams: mostly no, on Pro

All sessions share one quota pool. A coordinator plus three workers doesn't
buy more tokens — it spends the same pool faster, and each agent pays the full
cost of re-establishing context that a single session would pay once. On Max
plans teams buy wall-clock speed; on Pro they mostly buy hitting the 5-hour
wall sooner. The roadmap steps are also largely sequential (P1 security → P3
worker → features), which removes the one case where teams shine: truly
independent parallel workstreams.

Where **agent-deck** is valuable:

- **Queueing, not fanning out.** Line up "Step X → tests → commit" to run when
  a fresh 5-hour window opens, including overnight/off-hours windows that
  would otherwise go unused.
- **One cheap second opinion**, not a team: a `/code-review` at low/medium
  effort after each step catches bugs for a fraction of a full reviewer
  agent's cost.
- **Session-per-step isolation**, so no session ever accumulates cross-step
  context.

---

## The per-step workflow

1. **Fresh session, plan mode.** "Implement Step X per `Architecture/NN-….md`"
   — let it read *only* the listed specs (`CLAUDE.md` already enforces this;
   keep enforcing it).
2. **Front-load the full spec in one turn.** One well-specified prompt beats
   ten clarification round-trips — every follow-up turn resends the whole
   context. State the step, constraints, and definition-of-done up front.
3. Implement against the definition-of-done below, `/code-review` low, commit.
4. **`/clear`, next step.** Never let one session span two steps. Avoid
   relying on auto-compact — compaction itself costs tokens; a clean start
   with a good `CLAUDE.md` is cheaper.

### Definition of done (state it in every step prompt)

Paste-ready step prompt:

> Implement Step **X** of the v2 roadmap exactly as specified in CLAUDE.md
> ("Implementation Order") and the Architecture specs listed there for this
> step. Read only those specs plus the code you need. First check git
> log/status — if a previous session started this step, verify and complete
> the remaining scope instead of redoing it.
>
> Definition of done, all required:
> 1. Feature implemented per spec.
> 2. All tests green — backend pytest (with branch coverage) and frontend
>    vitest.
> 3. Per-module coverage gates pass (`scripts/check_module_coverage.py`,
>    vitest per-file thresholds).
> 4. **Security testing** per `Architecture/25-security-testing.md`: every
>    new route lands in the route-authorization matrix, every new external
>    data source lands in the injection fixture matrix, security tests green.
> 5. **Documentation updated**: Readme and affected docs reflect new env
>    vars, endpoints, commands, and behavior.
> 6. Run /code-review at low effort and fix confirmed findings.
> 7. Commit on the current branch with a descriptive message. Do not push.
>
> Delegate mechanical multi-file work (i18n keys across all six locales,
> pattern-following test boilerplate, bulk renames) to subagents running on
> haiku. Never delegate auth, subscription, or security code.

The delegation line at the end is how "switch to Haiku when it makes sense"
works in practice — the Sonnet session spawns haiku subagents per task; you
don't switch the session model.

## Milestone verification — every 5 steps

After every 5 completed steps, run a dedicated verification session (Sonnet,
fresh context, **not** combined with a feature step). Nothing new gets built
in this session; issues found must be fixed before the next step starts.

Paste-ready verification prompt:

> Milestone verification — do not implement new features.
>
> 1. **Dev deployment**: start the dev stack (`docker compose up -d --build`),
>    wait for health, then exercise all user-facing functionality end-to-end:
>    every backend route group in `Architecture/02-api-routes.md` via curl
>    (including auth flows — seed with `backend/create_dev_user.py`), verify
>    the frontend builds and serves, and check container logs for errors.
> 2. **Fix before moving on**: diagnose and fix every issue found (broken
>    endpoint, failing container, log/console error, regression), add a
>    regression test where sensible, and re-run the affected checks.
> 3. **Production deployment**: validate the production path per
>    `Architecture/12-deployment.md` — build the prod images; if the prod
>    compose/Caddy config exists, boot it locally, check health endpoints and
>    security headers, then tear it down. If prod setup is not yet implemented
>    (pre-P3), verify what exists and list the gaps.
> 4. Run the full test suite once more, commit fixes (do not push), and tear
>    down all containers you started.
>
> Finish with a clear PASS/FAIL summary. Never claim PASS with open issues.

Checkpoint positions in the roadmap order (S1 S2 P1 P2 P3 | P4 B1 B2 B3 L1 |
L2 L3 G1 G2 G3 | G4 G5 G6 G7 T1 | …): verify after **P3, L1, G3, T1**.

## Automating it with agent-deck (no orchestrator needed)

The cheapest automation is sequencing, not orchestration:

- **One headless run per step**: `claude -p "<step prompt>" --model sonnet
  --permission-mode acceptEdits`, executed from the repo root. Each invocation
  is a brand-new session — the fresh-context-per-step rule for free.
- **Queue steps sequentially** with agent-deck (`launch` a session per step,
  or have a simple loop feed the next step prompt when the previous run
  finishes and its commit exists). Never run two steps in parallel — they
  share the quota pool and the codebase.
- **When a run dies mid-step** (usage window exhausted), just re-issue the
  same step prompt later — the prompt's "check git log/status first" line
  makes re-runs resume instead of redo.
- **Skip the conductor** for the build itself; it spends from the same Pro
  quota on heartbeats. Add it only if you want Slack-remote steering.
- Claude cannot `/clear` itself or switch its own session model. Context
  hygiene comes from session boundaries (one run per step); Haiku usage comes
  from the delegation line in the step prompt.

### Hygiene

- **Keep MCP servers minimal** in this project — every attached tool schema is
  input tokens on *every* request.
- **Check `/usage` before starting something big** so a step doesn't get cut
  off mid-window — resuming a half-done step in a new session means re-paying
  all the context.

---

## Bottom line

Efficiency here isn't primarily a model question — it's **quota per completed
step**. Sonnet + one-session-per-step + plan-first + `/clear` will roughly
double or triple how many roadmap steps fit in a week compared to
Fable-with-long-sessions, with no quality loss on a project specced this well.
Haiku shaves a bit more on the mechanical edges; agent teams would move you
backwards.
