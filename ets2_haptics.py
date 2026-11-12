
import asyncio
import json
import time
import urllib.request

from buttplug import (
    ButtplugClient,
    DeviceOutputCommand,
    OutputType
)


# ============================================================
# ADJUSTABLE SETTINGS
# ============================================================

TELEMETRY_URL = "http://127.0.0.1:31377/api/ets2/telemetry"
INTIFACE_URL = "ws://127.0.0.1:12345"


# ----------------------------
# RPM VIBRATION SETTINGS
# ----------------------------

RPM_MIN = 1000
# RPM at which vibration begins.

RPM_MAX = 2500
# RPM at which vibration reaches maximum intensity.

RPM_MAX_INTENSITY = 1.0
# Maximum RPM vibration.
# 1.0 = 100%, 0.5 = 50%.

RPM_CURVE = 2.0
# Changes how quickly vibration increases.
#
# 1.0 = Linear increase.
# Below 1.0 = Faster increase at lower RPM.
# Above 1.0 = Slower increase at lower RPM.


# ----------------------------
# VIBRATION SMOOTHING
# ----------------------------

SMOOTHING = 0.25
# Higher = vibration responds faster.
# Lower = smoother, slower transitions.
#
# Suggested range: 0.10 - 0.40


# ----------------------------
# ENGINE START / STOP EFFECTS
# ----------------------------

ENGINE_START_INTENSITY = 0.20
ENGINE_START_DURATION = 0.7

ENGINE_STOP_INTENSITY = 0.15
ENGINE_STOP_DURATION = 0.6


# ----------------------------
# GEAR CHANGE EFFECT
# ----------------------------

GEAR_CHANGE_INTENSITY = 0.25
GEAR_CHANGE_DURATION = 0.15


# ----------------------------
# GENERAL SETTINGS
# ----------------------------

UPDATE_INTERVAL = 0.1
# How frequently telemetry is checked.


# ============================================================
# TELEMETRY
# ============================================================

def get_telemetry():

    try:
        request = urllib.request.Request(
            TELEMETRY_URL,
            headers={"User-Agent": "ETS2-Haptics"}
        )

        with urllib.request.urlopen(request, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))

    except Exception as error:
        print(f"\nTelemetry error: {error}")
        return None


# ============================================================
# RPM CALCULATION
# ============================================================

def calculate_rpm_intensity(rpm):

    if rpm <= RPM_MIN:
        return 0.0

    if rpm >= RPM_MAX:
        return RPM_MAX_INTENSITY

    normalized = (rpm - RPM_MIN) / (RPM_MAX - RPM_MIN)

    intensity = normalized ** RPM_CURVE

    return intensity * RPM_MAX_INTENSITY


# ============================================================
# MAIN APPLICATION
# ============================================================

async def main():

    client = ButtplugClient("ETS2 Haptics")

    print("Connecting to Intiface...")

    device = None

    try:

        await client.connect(INTIFACE_URL)

        print("Connected to Intiface!")

        devices = [
            d for d in client.devices.values()
            if d.has_output(OutputType.VIBRATE)
        ]

        if not devices:
            print("No vibration-capable devices found.")
            return

        device = devices[0]

        print(f"Using device: {device.name}")
        print("\nETS2 Haptics running.")
        print("Start your truck to begin.")
        print("Press CTRL+C to stop.\n")

        # Current vibration state
        current_intensity = 0.0
        last_sent_intensity = -1.0

        # Engine and gear tracking
        engine_running = None
        previous_gear = None

        # Temporary effects
        effect_intensity = 0.0
        effect_end_time = 0.0

        while True:

            data = await asyncio.to_thread(get_telemetry)

            rpm = 0
            gear = None
            target_intensity = 0.0

            if data is not None:

                game = data.get("game", {})
                truck = data.get("truck", {})

                if game.get("connected", False):

                    rpm = float(truck.get("engineRpm", 0) or 0)
                    gear = truck.get("gear")

                    # Determine whether engine is running.
                    # Uses RPM because the telemetry field
                    # for engine state may vary.

                    is_engine_running = rpm > 100

                    # ----------------------------
                    # ENGINE START / STOP
                    # ----------------------------

                    if engine_running is None:

                        engine_running = is_engine_running

                    elif is_engine_running != engine_running:

                        engine_running = is_engine_running

                        if engine_running:

                            effect_intensity = ENGINE_START_INTENSITY
                            effect_end_time = (
                                time.monotonic() + ENGINE_START_DURATION
                            )

                            print("\nEngine started!")

                        else:

                            effect_intensity = ENGINE_STOP_INTENSITY
                            effect_end_time = (
                                time.monotonic() + ENGINE_STOP_DURATION
                            )

                            print("\nEngine stopped!")

                    # ----------------------------
                    # GEAR CHANGES
                    # ----------------------------

                    if engine_running:

                        if previous_gear is not None and gear != previous_gear:

                            effect_intensity = max(
                                effect_intensity,
                                GEAR_CHANGE_INTENSITY
                            )

                            effect_end_time = (
                                time.monotonic() + GEAR_CHANGE_DURATION
                            )

                            print(f"\nGear changed: {previous_gear} -> {gear}")

                    previous_gear = gear

                    # ----------------------------
                    # RPM VIBRATION
                    # ----------------------------

                    if engine_running:

                        target_intensity = calculate_rpm_intensity(rpm)

            else:

                # Lost telemetry connection.
                engine_running = None
                previous_gear = None
                effect_intensity = 0.0
                effect_end_time = 0.0

            # ----------------------------
            # TEMPORARY EFFECT HANDLING
            # ----------------------------

            if time.monotonic() >= effect_end_time:
                effect_intensity = 0.0

            # Combine RPM vibration with temporary effects.
            # The strongest effect takes priority.

            target_intensity = max(
                target_intensity,
                effect_intensity
            )

            # ----------------------------
            # SMOOTHING
            # ----------------------------

            current_intensity += (
                target_intensity - current_intensity
            ) * SMOOTHING

            current_intensity = max(
                0.0,
                min(1.0, current_intensity)
            )

            # ----------------------------
            # SEND TO LOVENSE
            # ----------------------------

            if abs(current_intensity - last_sent_intensity) >= 0.01:

                if current_intensity > 0.01:

                    await device.run_output(
                        DeviceOutputCommand(
                            OutputType.VIBRATE,
                            current_intensity
                        )
                    )

                else:

                    await device.stop()

                last_sent_intensity = current_intensity

            # ----------------------------
            # TERMINAL DISPLAY
            # ----------------------------

            print(
                f"\rRPM: {rpm:5.0f} | "
                f"Gear: {str(gear):>4} | "
                f"Vibration: {current_intensity * 100:5.1f}%",
                end="",
                flush=True
            )

            await asyncio.sleep(UPDATE_INTERVAL)

    except KeyboardInterrupt:

        print("\nStopping ETS2 Haptics...")

    except Exception as error:

        print(f"\nApplication error: {error}")

    finally:

        try:

            if device is not None:
                await device.stop()

            if client.connected:
                await client.disconnect()

        except Exception:
            pass

        print("\nDisconnected.")


if __name__ == "__main__":
    asyncio.run(main())