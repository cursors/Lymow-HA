# Fix: MQTT Reconnect Stuck Forever After DNS Failure

## Context

AWS IoT drops the MQTT WebSocket when the embedded Cognito session token expires (~1 hour). `_handle_disconnect` fires and schedules `_reconnect_with_fresh_creds` as a background task. That function makes a single attempt — if the attempt hits a transient DNS failure (`socket.gaierror: [Errno -3] Try again`), it logs and returns. There is no retry loop.

After the failure, `self.mqtt` is left as a zombie `MqttClient` (its internal `_client` is None because `loop_start()` was never called). Paho never fires `_on_disconnect` again, so `_handle_disconnect` never fires again, and the integration stays disconnected forever until HA restarts.

Two bugs must be fixed:

1. **Zombie `self.mqtt`** — `_connect_mqtt` assigns `self.mqtt = MqttClient(...)` before calling `cli.connect()`. If `connect()` raises, `self.mqtt` is a dead object instead of `None`.
2. **No retry loop** — `_reconnect_with_fresh_creds` makes one attempt and gives up.

## Changes

Both changes are in `custom_components/lymow/coordinator.py` only. `mqtt.py` is untouched.

---

### Change 1 — Fix zombie state in `_connect_mqtt` (~lines 218–242)

Construct the `MqttClient` as a local `cli` variable, call `cli.connect()`, and only assign `self.mqtt = cli` after a successful connect. If `connect()` raises, `self.mqtt` stays `None`.

```python
async def _connect_mqtt(self) -> None:
    """Create and connect a new MqttClient with current credentials."""
    if self.mqtt:
        try:
            await self.mqtt.disconnect()
        except Exception:
            pass
        self.mqtt = None

    cli = MqttClient(
        thing_name=self.thing_name,
        host=self.client._ep["iotDomain"].replace("https://", "").rstrip("/"),
        region=self._region,
        on_pboutput=self._handle_pboutput,
        on_notify_app=self._handle_notify_app,
        on_disconnect_cb=self._handle_disconnect,
    )
    await cli.connect(
        access_key=self.auth.access_key_id,
        secret_key=self.auth.secret_access_key,
        session_token=self.auth.session_token,
    )
    self.mqtt = cli
    _LOGGER.debug("MQTT connected for %s — firing startup queries", self.thing_name)
    self._fire_startup_queries()
```

---

### Change 2 — Retry loop in `_reconnect_with_fresh_creds` (~lines 815–826)

Replace the single-attempt structure with a `while not self._shutting_down` loop. Use exponential backoff capped at 5 minutes (`min(5 * 2**attempt, 300)`), giving delays of 5, 10, 20, 40, 80, 160, 300, 300, … seconds.

`asyncio.CancelledError` is a `BaseException`, not an `Exception`, so the `except Exception` block does not swallow cancellation — `async_shutdown()`'s `task.cancel()` still works correctly.

```python
async def _reconnect_with_fresh_creds(self) -> None:
    """Refresh AWS credentials and re-create the MQTT connection, retrying with backoff."""
    attempt = 0
    while not self._shutting_down:
        delay = min(_RECONNECT_DELAY * (2 ** attempt), 300)
        _LOGGER.debug(
            "MQTT reconnect attempt %d for %s — waiting %ds",
            attempt + 1, self.thing_name, delay,
        )
        await asyncio.sleep(delay)
        if self._shutting_down:
            return
        try:
            _LOGGER.info("Refreshing AWS credentials for %s (attempt %d)", self.thing_name, attempt + 1)
            await self.auth.ensure_valid(self._email, self._password)
            await self._connect_mqtt()
            _LOGGER.info("MQTT reconnected for %s", self.thing_name)
            return
        except Exception:
            attempt += 1
            _LOGGER.warning(
                "MQTT reconnect attempt %d failed for %s — will retry in %ds",
                attempt, self.thing_name, min(_RECONNECT_DELAY * (2 ** attempt), 300),
            )
```

---

## What is NOT changing

- `mqtt.py` — no changes
- `async_shutdown()` — already cancels `_reconnect_task`; the loop exits cleanly via `CancelledError`
- `_handle_disconnect()` guard — `_reconnect_task.done()` check still prevents duplicate tasks
- `_refresh_loop()` — no watchdog needed since the reconnect loop now runs indefinitely

## Verification

1. Trigger a disconnect by temporarily blocking DNS (or by examining logs for the next hourly credential rotation)
2. Confirm log shows "MQTT reconnect attempt 1 … waiting 5s", then "attempt 2 … waiting 10s", etc.
3. Restore network — confirm "MQTT reconnected for …" appears and entities update
4. Confirm HA shutdown (Settings → Restart) cancels the reconnect task cleanly (no traceback, no hang)
5. Confirm that after a successful reconnect, a subsequent disconnect re-triggers a fresh reconnect cycle
