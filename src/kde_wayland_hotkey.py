import asyncio
import threading

from dbus_next import BusType, Message, MessageType
from dbus_next.aio import MessageBus


KGLOBALACCEL_SERVICE = "org.kde.kglobalaccel"
KGLOBALACCEL_PATH = "/kglobalaccel"
KGLOBALACCEL_INTERFACE = "org.kde.KGlobalAccel"
COMPONENT_INTERFACE = "org.kde.kglobalaccel.Component"

COMPONENT_UNIQUE = "wispr"
COMPONENT_FRIENDLY = "Wispr Dictation"

ACTION_UNIQUE = "hold_to_talk"
ACTION_FRIENDLY = "Hold to Talk"

# Qt::Key_Space = 0x20
# Qt::Key_Meta  = 0x10000000
SUPER_SPACE = 0x10000020

# KGlobalAccel SetPresent flag.
SET_PRESENT = 0x02


class KDEWaylandHotkey:
    """
    Global Super+Space hold detector for KDE Plasma Wayland.

    Uses KDE KGlobalAccel rather than evdev or X11 input access.
    """

    def __init__(self):
        self._activation_event = threading.Event()
        self._release_event = threading.Event()
        self._ready_event = threading.Event()

        self._startup_error = None

        self._thread = None
        self._loop = None
        self._bus = None

        self._component = None
        self._component_path = None

        self._running = False
        self._active = False

    # ------------------------------------------------------------------
    # D-Bus thread
    # ------------------------------------------------------------------

    def _run(self):
        try:
            asyncio.run(self._async_main())

        except Exception as error:
            self._startup_error = error
            self._ready_event.set()

    # ------------------------------------------------------------------
    # KGlobalAccel setup
    # ------------------------------------------------------------------

    async def _async_main(self):
        self._loop = asyncio.get_running_loop()

        self._bus = await MessageBus(
            bus_type=BusType.SESSION
        ).connect()

        self._bus.add_message_handler(
            self._handle_message
        )

        await self._add_signal_match()

        introspection = await self._bus.introspect(
            KGLOBALACCEL_SERVICE,
            KGLOBALACCEL_PATH,
        )

        proxy = self._bus.get_proxy_object(
            KGLOBALACCEL_SERVICE,
            KGLOBALACCEL_PATH,
            introspection,
        )

        interface = proxy.get_interface(
            KGLOBALACCEL_INTERFACE
        )

        action_id = [
            COMPONENT_UNIQUE,
            ACTION_UNIQUE,
            COMPONENT_FRIENDLY,
            ACTION_FRIENDLY,
        ]

        # Register the component/action with KGlobalAccel.
        try:
            await interface.call_do_register(
                action_id
            )
        except Exception:
            # The action may already be registered.
            pass

        # Assign Super+Space.
        await interface.call_set_shortcut(
            action_id,
            [SUPER_SPACE],
            SET_PRESENT,
        )

        self._component_path = (
            f"/component/{COMPONENT_UNIQUE}"
        )

        component_introspection = (
            await self._bus.introspect(
                KGLOBALACCEL_SERVICE,
                self._component_path,
            )
        )

        component_proxy = (
            self._bus.get_proxy_object(
                KGLOBALACCEL_SERVICE,
                self._component_path,
                component_introspection,
            )
        )

        self._component = (
            component_proxy.get_interface(
                COMPONENT_INTERFACE
            )
        )

        self._running = True
        self._ready_event.set()

        print(
            "[OK] KDE Wayland Super+Space hotkey registered.",
            flush=True,
        )

        try:
            while self._running:
                await asyncio.sleep(1)

        finally:
            await self._unregister()

    async def _add_signal_match(self):
        """
        Subscribe to KGlobalAccel shortcut signals.
        """

        message = Message(
            destination="org.freedesktop.DBus",
            path="/org/freedesktop/DBus",
            interface="org.freedesktop.DBus",
            member="AddMatch",
            signature="s",
            body=[
                "type='signal',"
                "sender='org.kde.kglobalaccel',"
                "path='/component/wispr',"
                "interface='org.kde.kglobalaccel.Component'"
            ],
        )

        reply = await self._bus.call(message)

        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(
                f"Failed to subscribe to KGlobalAccel signals: "
                f"{reply.body}"
            )

    # ------------------------------------------------------------------
    # D-Bus signal handling
    # ------------------------------------------------------------------

    def _handle_message(self, message):
        if message.message_type != MessageType.SIGNAL:
            return

        if message.path != "/component/wispr":
            return

        if message.interface != COMPONENT_INTERFACE:
            return

        if message.member == "globalShortcutPressed":
            self._on_pressed()

        elif message.member == "globalShortcutReleased":
            self._on_released()

    # ------------------------------------------------------------------
    # Hold-to-talk state
    # ------------------------------------------------------------------

    def _on_pressed(self):
        if self._active:
            return

        self._active = True

        self._release_event.clear()
        self._activation_event.set()

    def _on_released(self):
        if not self._active:
            return

        self._active = False
        self._release_event.set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """
        Start the KDE Wayland global hotkey backend.

        Blocks until KGlobalAccel registration succeeds or fails.
        """

        if self._thread is not None:
            return

        self._thread = threading.Thread(
            target=self._run,
            name="kde-wayland-hotkey",
            daemon=True,
        )

        self._thread.start()

        if not self._ready_event.wait(
            timeout=10
        ):
            raise RuntimeError(
                "Timed out waiting for KDE Wayland "
                "hotkey registration."
            )

        if self._startup_error is not None:
            raise RuntimeError(
                "KDE Wayland hotkey backend failed "
                "during startup."
            ) from self._startup_error

    def wait_for_activation(self):
        """
        Block until Super+Space is pressed.
        """

        self._activation_event.wait()
        self._activation_event.clear()

    def wait_for_release(self):
        """
        Block until Super+Space is released.
        """

        self._release_event.wait()
        self._release_event.clear()

    def close(self):
        """
        Stop the KDE Wayland hotkey backend.
        """

        self._running = False

        if self._loop is not None:
            self._loop.call_soon_threadsafe(
                lambda: None
            )

        if self._thread is not None:
            self._thread.join(
                timeout=2
            )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def _unregister(self):
        """
        Remove the registered shortcut from KGlobalAccel.
        """

        if self._bus is None:
            return

        try:
            introspection = await self._bus.introspect(
                KGLOBALACCEL_SERVICE,
                KGLOBALACCEL_PATH,
            )

            proxy = self._bus.get_proxy_object(
                KGLOBALACCEL_SERVICE,
                KGLOBALACCEL_PATH,
                introspection,
            )

            interface = proxy.get_interface(
                KGLOBALACCEL_INTERFACE
            )

            await interface.call_unregister(
                COMPONENT_UNIQUE,
                ACTION_UNIQUE,
            )

            print(
                "[OK] KDE Wayland hotkey unregistered.",
                flush=True,
            )

        except Exception as error:
            print(
                "[WARN] Failed to unregister KDE "
                f"shortcut: {error}",
                flush=True,
            )