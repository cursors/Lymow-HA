# Code Assistant Methodology

This document captures the working habits we want to preserve while using this fork of Lymow-HA.

It is intentionally practical. The goal is not process for process sake. The goal is to keep active work understandable, testable, and safe to contribute upstream without leaking fork-only planning material.

## Core principles

- prefer small, understandable changes over clever rewrites
- preserve working behavior unless there is a clear reason to change it
- tighten risky behavior by extracting decision logic into focused helpers
- add tests around subtle behavior before or while changing it
- use comments sparingly, but do use them when the code is handling a non-obvious integration trap

## Power words

Power words are lightweight, repo-native workflow skills we can create on the fly.

They are shorthand for a repeatable working pattern, not just a one-off instruction. When a power word exists, it should mean the same thing from session to session unless we intentionally revise it here.

The current power words are:

- `grill-me`: turn fuzzy behavior into an explicit rule set before coding
- `tidy-up`: do lightweight repository housekeeping when no feature branch is needed
- `ship-it`: commit signed-off work, push it to `origin`, and perform the usual post-push cleanup

## Branching and publish flow

- `main` tracks `origin/main`
- `origin/main` is kept aligned with `upstream/main`
- fork-only planning docs may live in this repo under `docs/`
- `docs/` is treated as fork-only material unless we intentionally decide otherwise
- upstreamable code should be prepared on a clean PR branch based on `upstream/main`

This means there are two valid kinds of branches:

- fork-working branches, which may include `docs/`
- upstream PR branches, which must be clean of fork-only docs

## Fork-only docs workflow

The default workflow for specs, plans, and assistant-facing project notes is:

1. create or update docs on a fork-working branch
2. push that branch to `origin`
3. implement from that branch if the docs are useful working context
4. when it is time to contribute upstream, create a fresh PR branch from `upstream/main`
5. move only upstreamable code commits onto that PR branch

Important:

- a working branch based on docs is good for development context
- it is not automatically safe for upstream push
- the local `pre-push` hook blocks pushes to `upstream` when commits touch `docs/`

## Upstream PR workflow

When work may eventually go upstream, the safe pattern is:

1. keep planning docs and exploratory notes on a fork-working branch
2. do implementation there if that is the easiest way to work
3. once the code is ready, create a clean PR branch from `upstream/main`
4. cherry-pick or otherwise move only the upstreamable code commits
5. verify the clean branch
6. push the clean branch for PR use

The point is to separate working context from submission context.

## Ship-it

`ship-it` is our shorthand for turning signed-off work into a committed and published repository state.

When someone says `ship-it`, the expected workflow is:

1. show the proposed commit message to the user before committing
2. commit the signed-off work with a clear title and, when appropriate, a detailed body
3. push the work to `origin`
4. if the work lives on a branch and the repo is being used trunk-first, fast-forward `main`
5. push `main`
6. refresh remote refs
7. delete safely stale local branches

`ship-it` should follow the normal safety rules:

- do not commit unsanctioned work
- do not rewrite history unless explicitly asked
- do not update branches unsafely if the working tree is not in a safe state

## Tightening existing behavior

When an existing feature becomes subtle or bug-prone, the default strategy is:

1. identify the smallest decision-making seam inside the feature
2. extract that logic into a helper with a narrow interface
3. add focused unit tests for the helper
4. keep the integration-facing entity or coordinator code thin where possible
5. smoke test the end-to-end behavior in Home Assistant

This is the preferred pattern for coordinator loops, telemetry derivation, entity mapping, and stateful workflows.

## Grill-me

`grill-me` is our shorthand for turning fuzzy behavior into an explicit rule set before changing code.

Definition:

Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

When someone says `grill-me`, the expected workflow is:

1. ask one precise behavior question at a time
2. provide a recommended answer with each question
3. keep going until no meaningful ambiguity remains
4. turn the answers into explicit rules
5. only then extract helpers, write focused tests, and change runtime behavior

If a question can be answered by exploring the codebase, explore the codebase instead of asking.

Use `grill-me` when:

- the current behavior is partly working but not fully defined
- regressions have come from ambiguous intent rather than bad implementation
- multiple edge cases interact, such as moving telemetry, map consumers, and keepalive behavior

The point of `grill-me` is to avoid coding from vibes.

## Tidy-up

`tidy-up` is our shorthand for lightweight repository housekeeping when no feature branch is needed.

When someone says `tidy-up`, the expected workflow is:

1. check `git status`
2. if the working tree is clean and the update is safe, get the latest changes with a fast-forward update
3. refresh remote refs
4. prune safely stale local branches

If the working tree is not clean, `tidy-up` should stop short of any risky update and explain why.

## Test strategy

Use the lightest test that gives confidence.

- pure data or decision logic: unit tests first
- config normalization and source resolution: focused unit tests
- tricky stateful behavior: extract the decision logic, then unit test the extracted helper
- Home Assistant integration quirks: keep a short manual smoke test path in addition to automated tests

For regressions around telemetry freshness or moving keepalive, the goal is to test the coordinator decision logic directly instead of relying only on manual mower runs.

## Home Assistant smoke workflow

When a change affects visible map behavior or runtime mower behavior:

1. run the normal automated checks
2. install or copy the updated integration into Home Assistant
3. restart or reload as needed
4. smoke test the actual behavior in Home Assistant before sign-off

Home Assistant smoke testing is part of sign-off for telemetry and map behavior, not an optional afterthought.

## Comments

Most Python in this repo should stay readable without heavy commenting.

Add an inline comment when one of these is true:

- Home Assistant is doing something surprising
- MQTT or protobuf behavior is non-obvious
- a state transition is easy to break if someone "cleans it up"
- the code intentionally avoids an apparently simpler approach for a good reason

Do not add comments that merely restate the next line of code.

## Diagnostics and observability

When debugging subtle mower behavior, prefer adding targeted diagnostics rather than guessing.

Useful examples:

- last MQTT message timestamp
- last pose update timestamp
- keepalive task active or inactive
- last moving keepalive reason
- current moving or localization predicate

If a bug is expensive to rediscover, add enough observability to make the next debugging session shorter.

## Commit discipline

Before committing signed-off work:

- show the proposed commit message to the user
- prefer detailed commit bodies for behavioral changes
- keep the commit message aligned with the spec and the actual verification work

If a branch contains both fork-only docs and upstreamable code, do not assume it is PR-ready. Prepare a clean branch before upstream submission.

## Verification checklist

Before signing off on behavior changes:

1. run `.venv\Scripts\ruff.exe check .`
2. run `.venv\Scripts\python.exe -m pytest`
3. perform any needed Home Assistant smoke test

## Evolving this document

If we find ourselves repeating a successful pattern more than once, it probably belongs here.
