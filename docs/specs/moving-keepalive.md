# Moving Keepalive Spec

## Purpose

Define an opt-in moving keepalive feature in Lymow-HA that improves live telemetry freshness while the mower is moving, without forcing the behavior on all users or pushing packet-level logic into downstream consumers such as GeoDroid.

## Problem statement

Current behavior suggests that Lymow's backend or mower may provide better live telemetry when an active client session is present. In practice, live position updates can remain healthy while the official app is foregrounded, then become sparse or stall after the app is backgrounded or closed.

Lymow-HA currently performs periodic MQTT-driven queries, but it does not expose a dedicated, user-controlled "keepalive while moving" behavior intended to mimic active client presence during mower movement.

## Goals

- add a moving keepalive capability that runs only while the mower is in qualifying movement states
- keep the capability entirely inside Lymow-HA
- make the feature user-controlled and default-off
- allow downstream consumers to depend on Lymow-HA rather than implementing their own keepalive logic
- make the behavior observable enough to evaluate during real mower testing

## Non-goals

- do not make GeoDroid or any other consumer send MQTT or protocol packets directly
- do not auto-enable keepalive based on consumer detection in Phase 1
- do not redesign general coordinator refresh behavior beyond what is necessary for moving keepalive
- do not create a permanent diagnostics entity model in Phase 1
- do not try to solve every stale-state or map-recovery problem as part of this feature
- do not scatter moving-keepalive-specific logic broadly through unrelated coordinator behavior if a focused abstraction can contain it

## User-facing behavior

- the feature is exposed as a switch entity in Lymow-HA
- the switch defaults to off for:
  - new installs
  - existing upgraded installs
- when the switch is off, coordinator behavior remains unchanged
- when the switch is on, Lymow-HA is permitted to run moving keepalive while the mower is in qualifying moving states
- the switch does not force keepalive traffic while the mower is idle, docked, or offline
- the switch state persists across Home Assistant restarts

## Ownership model

- Lymow-HA owns the moving keepalive capability
- consumers may depend on the capability existing, but they do not implement or control the packet loop directly
- in Phase 1, the user explicitly enables the feature
- consumer-driven automatic requests are deferred to a later phase

## Qualifying movement states

The initial moving keepalive eligibility set is:

- mowing
- resuming
- docking/returning
- escaping

These correspond to movement states where fresh position updates matter to a map consumer.

Implementation rule:

- eligibility should be derived from the current mower state using the same broad localization-aware interpretation already used by the integration where practical
- Phase 1 should not invent a completely separate movement definition unless reuse proves too broad or incorrect

## Activation model

Moving keepalive is implemented as a persistent coordinator background task.

Lifecycle rules:

- the task exists for the life of the coordinator
- it wakes on the keepalive interval
- on each cycle it evaluates current eligibility from live coordinator state
- if eligibility is true, it sends the moving keepalive packet set
- if eligibility is false, it does nothing and records the inactive reason
- when the mower leaves a qualifying movement state, the loop stops sending packets on the next cycle boundary
- no linger timer or special shutdown packet is used in Phase 1

This lifecycle model is intentional, not a temporary testing shortcut.

## Implementation structure

The core moving-keepalive behavior should be encapsulated behind a focused abstraction.

Rules:

- prefer a dedicated helper, internal class, or similarly narrow abstraction for moving-keepalive state and decisions
- keep edits to existing coordinator code as narrow as possible
- use existing coordinator code primarily for:
  - task lifecycle wiring
  - persistence wiring
  - entity-facing attribute exposure
- avoid spreading keepalive-specific conditionals through unrelated refresh, reconnect, and state-merge paths unless correctness requires it

The spec does not require a single exact Python shape, but it does require the feature to remain structurally contained.

## Connection behavior

Moving keepalive is opportunistic.

Rules:

- it runs only when:
  - the feature is enabled
  - the mower is in a qualifying movement state
  - MQTT is connected
- if MQTT is disconnected, the keepalive task skips sending
- the keepalive task does not implement its own reconnect strategy
- existing coordinator reconnect logic remains the single authority for connection recovery

## Refresh interaction

When moving keepalive is active, it replaces the default overlapping moving-state refresh/query behavior with a dedicated moving keepalive cadence.

Rules:

- avoid duplicate overlapping query traffic from multiple concurrent loops
- do not layer a second moving refresh loop on top of the existing moving query behavior
- preserve unrelated coordinator maintenance responsibilities unless they are intentionally folded into the new behavior

Phase 1 focuses only on the moving telemetry problem and should avoid broad refresh redesign.

## Packet set

Phase 1 uses the smallest plausible packet set needed to test the keepalive hypothesis.

Initial packet profile:

- `appConnect`
- `QUERY_PATH`

Rules:

- do not add a second less-frequent sub-cycle in Phase 1
- do not include additional config/net/RTK packets in the moving keepalive loop unless testing shows the minimal packet profile is insufficient
- packet set should be easy to tune in code during testing

## Cadence

Initial moving keepalive interval:

- 5 seconds

Rules:

- 5 seconds is the initial test value, not a claim of final correctness
- the interval should be easy to adjust during testing
- the interval should be defined centrally, not buried inline in loop code

## Diagnostics

Phase 1 diagnostics are temporary mower-entity attributes intended to support real-world testing.

Initial attribute set:

- `moving_keepalive_enabled`
- `moving_keepalive_active`
- `moving_keepalive_interval_s`
- `moving_keepalive_packet_profile`
- `moving_keepalive_last_sent_at`
- `moving_keepalive_last_send_ok`
- `moving_keepalive_last_reason`
- `last_mqtt_message_at`
- `moving_keepalive_motion_state`

Rules:

- diagnostics are exposed on the mower entity for Phase 1 testing convenience
- they are considered temporary
- after validation, they should be either removed or moved to a cleaner long-term diagnostic surface
- diagnostics should be inspectable from Home Assistant Developer Tools during runtime testing

## Persistence

- moving keepalive enablement must persist across Home Assistant restarts
- the persisted value represents user permission for the feature to run while moving
- ephemeral runtime diagnostics do not need to persist across restart

## Phase 1 acceptance criteria

Phase 1 is acceptable when all of the following are true:

1. a user can enable and disable moving keepalive through a switch entity
2. the switch defaults to off for both new installs and upgraded installs
3. when enabled, the feature sends the defined keepalive packet profile only during qualifying movement states
4. the feature does not send moving keepalive traffic while idle, docked, offline, or MQTT-disconnected
5. the coordinator avoids duplicate overlapping moving refresh behavior
6. testing attributes are visible on the mower entity
7. the implementation is stable across normal coordinator setup, reconnect, and shutdown flows

## Verification

Automated verification:

1. run `.venv\Scripts\ruff.exe check .`
2. run `.venv\Scripts\python.exe -m pytest`

Manual Home Assistant verification:

1. enable the feature through the switch
2. confirm the mower entity exposes the expected diagnostics
3. observe the feature inactive while the mower is idle
4. start a mower run and confirm keepalive becomes active in a qualifying moving state
5. confirm diagnostics update as packets are sent
6. compare position freshness with and without moving keepalive while the official app is backgrounded
7. confirm the feature stops sending after the mower exits the qualifying movement state

## Open questions for later phases

- should consumer-driven request or lease semantics be added after Phase 1
- should the keepalive packet profile expand if `appConnect + QUERY_PATH` proves insufficient
- should diagnostics remain visible after validation, and if so, where
- should the movement predicate be widened or narrowed based on field testing
