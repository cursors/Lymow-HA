# Moving Keepalive Plan

This plan implements the spec in [docs/specs/moving-keepalive.md](/c:/repos/Lymow-HA/docs/specs/moving-keepalive.md).

The goal is to add an opt-in moving keepalive capability to Lymow-HA with a minimal packet profile, a persistent coordinator task, and enough diagnostics to evaluate whether it materially improves moving telemetry freshness.

## Implementation guidance

- keep the core moving-keepalive behavior encapsulated behind a focused abstraction
- prefer narrow integration points in existing coordinator code
- modify unrelated coordinator behavior only when required by correctness
- avoid spreading moving-keepalive conditionals across multiple unrelated paths if a helper or internal stateful object can contain them

The plan intentionally does not force one exact Python shape, but it does assume the feature should remain structurally contained.

## Reviewability guidance

- keep Phase 1 narrowly scoped to moving keepalive only
- preserve existing behavior completely when the feature is off
- keep the Phase 1 packet profile explicit and minimal
- make the replacement of overlapping moving refresh behavior obvious in code
- add focused tests around eligibility and loop decision logic
- treat mower-entity diagnostics as temporary and label them accordingly
- avoid bundling unrelated coordinator cleanup into this feature branch
- prefer a commit structure that separates:
  - internal keepalive behavior
  - user-facing switch and diagnostics wiring

## Milestone 1: Coordinator groundwork

### Goal

Add the internal coordinator structures needed to support moving keepalive without changing user-facing behavior yet.

### Tasks

- add persistent coordinator state for:
  - moving keepalive enabled
  - moving keepalive active
  - keepalive interval
  - keepalive packet profile label
  - last keepalive send timestamp
  - last keepalive send result
  - last keepalive reason
- add a persistent background task in the coordinator for moving keepalive
- define a single eligibility helper that evaluates:
  - feature enabled
  - MQTT connected
  - qualifying moving state
- introduce the focused abstraction that will own moving-keepalive decisions and state where practical
- ensure the task lifecycle is integrated cleanly into coordinator setup and shutdown
- persist the user permission state across restarts

### Target files

- `custom_components/lymow/coordinator.py`
- `custom_components/lymow/state.py`
- `custom_components/lymow/__init__.py`
- any config-entry persistence plumbing needed by the current integration structure

### Deliverable

The coordinator can track and evaluate moving keepalive state, but the feature is still not user-toggleable.

### Verification

- import and lint checks pass
- existing tests still pass
- coordinator startup and shutdown paths remain coherent

### Risks

- duplicate or conflicting background-loop behavior
- persistence added in the wrong storage surface
- eligibility logic diverging from current movement/localization logic

## Milestone 2: Keepalive loop behavior

### Goal

Implement the actual moving keepalive packet loop with the Phase 1 packet profile and cadence.

### Tasks

- implement the keepalive loop at a central 5-second interval
- send the Phase 1 packet profile:
  - `appConnect`
  - `QUERY_PATH`
- record keepalive diagnostics on each cycle
- ensure the loop does nothing when ineligible, but records the inactive reason
- ensure moving keepalive replaces overlapping moving refresh behavior rather than layering on top of it
- avoid introducing a separate reconnect or retry strategy

### Target files

- `custom_components/lymow/coordinator.py`
- `custom_components/lymow/protocol.py` only if packet helpers need small refactoring or explicit reuse

### Deliverable

The coordinator can perform moving keepalive internally while moving, using the defined packet profile and cadence.

### Verification

- lint and tests pass
- no regressions in startup query behavior
- code inspection confirms there is no duplicate moving query loop for the same packet responsibilities

### Risks

- accidentally spamming overlapping packets from multiple loops
- changing moving-state behavior more broadly than intended
- packet profile not being minimal in practice

## Milestone 3: User control surface

### Goal

Expose moving keepalive as a user-controlled switch with default-off behavior and persistent preference state.

### Tasks

- add a switch entity for moving keepalive permission
- default the feature to off for:
  - new installs
  - existing upgraded installs
- wire switch state changes into coordinator permission state
- persist the switch-controlled permission across restart
- ensure the switch means:
  - permission to run while moving
  - not force-run while idle

### Target files

- `custom_components/lymow/switch.py`
- `custom_components/lymow/coordinator.py`
- `custom_components/lymow/__init__.py`
- any config migration or persistence files required by the current integration structure

### Deliverable

Users can enable or disable moving keepalive from Home Assistant, and the preference persists across restart.

### Verification

- switch entity appears and toggles correctly
- default state is off in fresh and upgraded scenarios
- restart preserves the chosen state

### Risks

- ambiguous switch semantics
- persistence mismatch between runtime state and saved state
- upgrade path accidentally enabling the feature

## Milestone 4: Phase 1 diagnostics

### Goal

Expose temporary testing diagnostics as mower-entity attributes so runtime evaluation is practical in Home Assistant.

### Tasks

- add temporary mower attributes for:
  - `moving_keepalive_enabled`
  - `moving_keepalive_active`
  - `moving_keepalive_interval_s`
  - `moving_keepalive_packet_profile`
  - `moving_keepalive_last_sent_at`
  - `moving_keepalive_last_send_ok`
  - `moving_keepalive_last_reason`
  - `last_mqtt_message_at`
  - `moving_keepalive_motion_state`
- ensure attribute values are updated consistently during moving, idle, disconnect, and reconnect cases
- keep the diagnostics implementation narrow so it can be removed or relocated later

### Target files

- `custom_components/lymow/lawn_mower.py`
- `custom_components/lymow/coordinator.py`

### Deliverable

The mower entity exposes the temporary diagnostics needed for real-world keepalive testing.

### Verification

- attributes are visible in Home Assistant Developer Tools
- values update coherently during moving and non-moving states
- values remain understandable during MQTT disconnect/reconnect events

### Risks

- cluttering the mower entity too much
- attribute values becoming stale or misleading
- temporary diagnostics accidentally turning into permanent design without review

## Milestone 5: Runtime validation and cleanup

### Goal

Validate the feature against real mower behavior and make small tuning adjustments needed for Phase 1 acceptance.

### Tasks

- test with keepalive off and on during real moving runs
- compare telemetry freshness when the official app is backgrounded
- adjust interval or packet profile label only if testing justifies it
- verify the loop stops cleanly outside qualifying moving states
- verify behavior across MQTT reconnect
- document any observed limitations and post-test cleanup decisions

### Target files

- implementation files above, only if small tuning changes are needed
- docs if the spec or plan needs post-validation notes

### Deliverable

A validated Phase 1 implementation with enough evidence to decide whether moving keepalive should remain, expand, or be revised.

### Verification

- `.venv\Scripts\ruff.exe check .`
- `.venv\Scripts\python.exe -m pytest`
- Home Assistant runtime checks from the spec

### Risks

- real mower behavior may show that `appConnect + QUERY_PATH` is insufficient
- the 5-second interval may be too weak or too aggressive
- temporary diagnostics may need refinement to make test results interpretable

## Implementation order

Recommended order:

1. Milestone 1: coordinator groundwork
2. Milestone 2: keepalive loop behavior
3. Milestone 3: user control surface
4. Milestone 4: Phase 1 diagnostics
5. Milestone 5: runtime validation and cleanup

This order keeps the internal behavior coherent before exposing it to users.

## Decisions already made

The plan assumes these design decisions are settled:

- feature classification: `feat`
- user-facing control: switch entity
- default state: off for new and upgraded installs
- runtime semantics: permission to run while moving, not force-run always
- movement scope: mowing, resuming, docking/returning, escaping
- lifecycle model: persistent coordinator task
- packet profile: `appConnect + QUERY_PATH`
- cadence: 5 seconds initially
- diagnostics: temporary mower attributes during testing

## Out of scope for this plan

- automatic consumer-driven activation
- request/lease semantics for downstream consumers
- permanent diagnostics surface design
- broad coordinator refresh redesign beyond the moving keepalive scope
