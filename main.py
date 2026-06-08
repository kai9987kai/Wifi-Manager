import queue
import threading
from tkinter import TclError, messagebox, simpledialog

import customtkinter as ctk

from wifi_backend import WiFiBackend, WiFiBackendError


ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class SavedKeyDialog(ctk.CTkToplevel):
    CLIPBOARD_CLEAR_MS = 30_000

    def __init__(self, parent, ssid, password):
        super().__init__(parent)
        self.parent = parent
        self.password = password
        self.revealed = False

        self.title(f"Saved key - {ssid}")
        self.geometry("440x225")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self,
            text=ssid,
            font=ctk.CTkFont(size=19, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=24, pady=(22, 2), sticky="ew")
        ctk.CTkLabel(
            self,
            text="Saved Wi-Fi key",
            text_color=("gray40", "gray65"),
            anchor="w",
        ).grid(row=1, column=0, padx=24, sticky="ew")

        self.key_entry = ctk.CTkEntry(self, show="*", height=38)
        self.key_entry.grid(row=2, column=0, padx=24, pady=(14, 10), sticky="ew")
        self.key_entry.insert(0, password)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=3, column=0, padx=24, sticky="ew")
        actions.grid_columnconfigure(2, weight=1)

        self.reveal_button = ctk.CTkButton(
            actions,
            text="Reveal",
            width=82,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            command=self._toggle_reveal,
        )
        self.reveal_button.grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Copy key",
            width=92,
            command=self._copy_key,
        ).grid(row=0, column=1)
        ctk.CTkButton(
            actions,
            text="Close",
            width=74,
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90"),
            command=self.destroy,
        ).grid(row=0, column=3)

        self.feedback_label = ctk.CTkLabel(
            self,
            text="",
            text_color=("gray40", "gray65"),
            anchor="w",
        )
        self.feedback_label.grid(row=4, column=0, padx=24, pady=(8, 0), sticky="ew")
        self.after(50, self.focus_force)

    def _toggle_reveal(self):
        self.revealed = not self.revealed
        self.key_entry.configure(show="" if self.revealed else "*")
        self.reveal_button.configure(text="Hide" if self.revealed else "Reveal")

    def _copy_key(self):
        self.parent.clipboard_clear()
        self.parent.clipboard_append(self.password)
        self.feedback_label.configure(text="Copied. Clipboard clears automatically in 30 seconds.")
        self.parent.after(self.CLIPBOARD_CLEAR_MS, self._clear_clipboard)

    def _clear_clipboard(self):
        try:
            if self.parent.clipboard_get() == self.password:
                self.parent.clipboard_clear()
        except TclError:
            pass


class WiFiManagerApp(ctk.CTk):
    AUTO_REFRESH_MS = 15_000

    def __init__(self):
        super().__init__()

        self.title("WiFi Manager")
        self.geometry("1040x700")
        self.minsize(880, 580)

        self.backend = WiFiBackend()
        self.networks = []
        self.saved_profiles = set()
        self.connection_info = None
        self.current_ssid = None
        self.action_buttons = []
        self.busy = False
        self.filter_mode = "All"
        self.view_mode = "Nearby"
        self.task_results = queue.Queue()
        self.auto_refresh_job = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._create_sidebar()
        self._create_main_area()
        self.bind("<F5>", lambda _event: self.refresh_networks())
        self.bind("<Control-f>", lambda _event: self.search_entry.focus_set())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(75, self._process_task_results)
        self.refresh_networks()

    def _create_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=240, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(7, weight=1)

        ctk.CTkLabel(
            self.sidebar_frame,
            text="WiFi Manager",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, padx=24, pady=(24, 0), sticky="w")
        ctk.CTkLabel(
            self.sidebar_frame,
            text="Windows network control",
            text_color=("gray40", "gray65"),
        ).grid(row=1, column=0, padx=24, pady=(0, 24), sticky="w")

        self.refresh_button = ctk.CTkButton(
            self.sidebar_frame,
            text="Refresh networks",
            height=38,
            command=self.refresh_networks,
        )
        self.refresh_button.grid(row=2, column=0, padx=24, pady=(0, 22), sticky="ew")

        ctk.CTkLabel(
            self.sidebar_frame,
            text="CONNECTION",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("gray40", "gray65"),
        ).grid(row=3, column=0, padx=24, sticky="w")

        self.current_net_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="Checking...",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=190,
        )
        self.current_net_label.grid(row=4, column=0, padx=24, pady=(6, 2), sticky="ew")

        self.connection_meta_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="",
            anchor="w",
            justify="left",
            wraplength=190,
            text_color=("gray35", "gray70"),
        )
        self.connection_meta_label.grid(row=5, column=0, padx=24, pady=(0, 8), sticky="ew")

        self.status_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="Starting",
            anchor="w",
            justify="left",
            wraplength=190,
            text_color=("gray40", "gray65"),
        )
        self.status_label.grid(row=6, column=0, padx=24, sticky="ew")

        self.auto_refresh_switch = ctk.CTkSwitch(
            self.sidebar_frame,
            text="Auto-refresh every 15s",
            command=self._toggle_auto_refresh,
        )
        self.auto_refresh_switch.grid(row=8, column=0, padx=24, pady=(0, 18), sticky="w")

        ctk.CTkLabel(
            self.sidebar_frame,
            text="APPEARANCE",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("gray40", "gray65"),
        ).grid(row=9, column=0, padx=24, pady=(0, 6), sticky="w")
        self.appearance_menu = ctk.CTkOptionMenu(
            self.sidebar_frame,
            values=["System", "Light", "Dark"],
            command=ctk.set_appearance_mode,
        )
        self.appearance_menu.set("System")
        self.appearance_menu.grid(row=10, column=0, padx=24, pady=(0, 24), sticky="ew")

    def _create_main_area(self):
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=0, column=1, padx=24, pady=22, sticky="nsew")
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        self.header_title = ctk.CTkLabel(
            header,
            text="Nearby networks",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        self.header_title.grid(row=0, column=0, sticky="w")
        self.summary_label = ctk.CTkLabel(
            header,
            text="Scanning...",
            text_color=("gray40", "gray65"),
        )
        self.summary_label.grid(row=1, column=0, pady=(0, 14), sticky="w")

        self.view_control = ctk.CTkSegmentedButton(
            header,
            values=["Nearby", "Saved profiles"],
            command=self._set_view,
        )
        self.view_control.set("Nearby")
        self.view_control.grid(row=0, column=1, rowspan=2, padx=(18, 0), sticky="e")

        controls = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        controls.grid(row=1, column=0, pady=(0, 12), sticky="ew")
        controls.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            controls,
            placeholder_text="Search networks",
            height=36,
        )
        self.search_entry.grid(row=0, column=0, padx=(0, 12), sticky="ew")
        self.search_entry.bind("<KeyRelease>", lambda _event: self._render_content())

        self.filter_control = ctk.CTkSegmentedButton(
            controls,
            values=["All", "Saved", "Open"],
            command=self._set_filter,
        )
        self.filter_control.set("All")
        self.filter_control.grid(row=0, column=1)

        self.main_frame = ctk.CTkScrollableFrame(
            self.content_frame,
            fg_color="transparent",
            corner_radius=0,
        )
        self.main_frame.grid(row=2, column=0, sticky="nsew")

    def refresh_networks(self):
        if self.busy:
            return
        self._cancel_auto_refresh()
        self._set_busy(True, "Scanning for networks...")
        self.summary_label.configure(text="Scanning...")
        self._submit_task(self._load_snapshot, self._finish_refresh)

    def _load_snapshot(self):
        connection_info = self.backend.get_connection_info()
        return {
            "networks": self.backend.scan_networks(),
            "connection_info": connection_info,
            "current_ssid": connection_info["ssid"] if connection_info else None,
            "saved_profiles": set(self.backend.get_saved_profiles()),
        }

    def _finish_refresh(self, snapshot, status=None):
        self.networks = snapshot["networks"]
        self.connection_info = snapshot["connection_info"]
        self.current_ssid = snapshot["current_ssid"]
        self.saved_profiles = snapshot["saved_profiles"]
        self._set_busy(False, status or "Ready")
        self._update_connection_panel()
        self._render_content()
        self._schedule_auto_refresh()

    def _render_content(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()
        self.action_buttons.clear()

        if self.view_mode == "Saved profiles":
            self._render_saved_profiles()
        else:
            self._render_nearby_networks()
        self._update_action_button_states()

    def _render_nearby_networks(self):
        query = self.search_entry.get().strip().casefold()
        visible = []
        for network in self.networks:
            ssid = network["ssid"]
            if query and query not in ssid.casefold():
                continue
            if self.filter_mode == "Saved" and ssid not in self.saved_profiles:
                continue
            if self.filter_mode == "Open" and not self.backend.is_open_network(network["auth"]):
                continue
            visible.append(network)

        visible.sort(
            key=lambda network: (
                network["ssid"] != self.current_ssid,
                -network["signal"],
                network["ssid"].casefold(),
            )
        )
        saved_count = sum(network["ssid"] in self.saved_profiles for network in self.networks)
        self.summary_label.configure(
            text=f"{len(self.networks)} nearby  |  {saved_count} saved in range"
        )

        if not visible:
            message = "No networks match your search or filter." if self.networks else "No Wi-Fi networks found."
            self._show_empty_state(message)
            return

        for network in visible:
            self._create_network_item(network)

    def _render_saved_profiles(self):
        query = self.search_entry.get().strip().casefold()
        nearby_by_ssid = {network["ssid"]: network for network in self.networks}
        profiles = [
            profile
            for profile in self.saved_profiles
            if not query or query in profile.casefold()
        ]
        profiles.sort(key=lambda profile: (profile != self.current_ssid, profile.casefold()))

        in_range = sum(profile in nearby_by_ssid for profile in self.saved_profiles)
        self.summary_label.configure(
            text=f"{len(self.saved_profiles)} saved  |  {in_range} currently in range"
        )

        if not profiles:
            message = "No saved profiles match your search." if self.saved_profiles else "No saved Wi-Fi profiles."
            self._show_empty_state(message)
            return

        for profile in profiles:
            self._create_saved_profile_item(profile, nearby_by_ssid.get(profile))

    def _create_network_item(self, network):
        ssid = network["ssid"]
        signal = network["signal"]
        is_connected = ssid == self.current_ssid
        is_saved = ssid in self.saved_profiles

        card = self._create_card(is_connected)
        signal_frame = ctk.CTkFrame(card, width=94, fg_color="transparent")
        signal_frame.grid(row=0, column=0, padx=(16, 10), pady=16, sticky="ns")
        ctk.CTkLabel(
            signal_frame,
            text=f"{signal}%",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack()
        progress = ctk.CTkProgressBar(
            signal_frame,
            width=72,
            height=6,
            progress_color=self._signal_color(signal),
        )
        progress.set(max(0, min(signal, 100)) / 100)
        progress.pack(pady=(5, 0))

        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=0, column=1, pady=14, sticky="ew")
        title = ssid + ("  |  Connected" if is_connected else "")
        ctk.CTkLabel(
            info_frame,
            text=title,
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        ).pack(fill="x")

        details = [network["auth"]]
        if network.get("encryption") not in {None, "Unknown"}:
            details.append(network["encryption"])
        if network.get("bands"):
            details.append(" / ".join(network["bands"]))
        if network.get("channels"):
            details.append("Ch " + ", ".join(network["channels"]))
        access_points = network.get("access_points", 0)
        if access_points:
            details.append(f"{access_points} access point{'s' if access_points != 1 else ''}")
        if is_saved:
            details.append("Saved")
        ctk.CTkLabel(
            info_frame,
            text="  |  ".join(details),
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
            anchor="w",
            justify="left",
            wraplength=430,
        ).pack(fill="x", pady=(2, 0))

        button_frame = ctk.CTkFrame(card, fg_color="transparent")
        button_frame.grid(row=0, column=2, padx=14, pady=14)
        if is_saved:
            self._add_key_button(button_frame, ssid)
        self._add_connection_button(button_frame, ssid, network, is_connected)

    def _create_saved_profile_item(self, ssid, network):
        is_connected = ssid == self.current_ssid
        card = self._create_card(is_connected)

        state_frame = ctk.CTkFrame(card, width=94, fg_color="transparent")
        state_frame.grid(row=0, column=0, padx=(16, 10), pady=16, sticky="ns")
        if network:
            ctk.CTkLabel(
                state_frame,
                text=f"{network['signal']}%",
                font=ctk.CTkFont(size=16, weight="bold"),
            ).pack()
            ctk.CTkLabel(
                state_frame,
                text="In range",
                font=ctk.CTkFont(size=10),
                text_color=("#16734a", "#4cd49a"),
            ).pack(pady=(2, 0))
        else:
            ctk.CTkLabel(
                state_frame,
                text="Saved",
                font=ctk.CTkFont(size=14, weight="bold"),
            ).pack()
            ctk.CTkLabel(
                state_frame,
                text="Out of range",
                font=ctk.CTkFont(size=10),
                text_color=("gray40", "gray65"),
            ).pack(pady=(2, 0))

        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=0, column=1, pady=14, sticky="ew")
        title = ssid + ("  |  Connected" if is_connected else "")
        ctk.CTkLabel(
            info_frame,
            text=title,
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        ).pack(fill="x")
        detail = "Windows saved profile"
        if network:
            detail = f"{network['auth']}  |  {' / '.join(network.get('bands', [])) or 'Band unknown'}"
        ctk.CTkLabel(
            info_frame,
            text=detail,
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        button_frame = ctk.CTkFrame(card, fg_color="transparent")
        button_frame.grid(row=0, column=2, padx=14, pady=14)
        self._add_key_button(button_frame, ssid)
        forget_button = ctk.CTkButton(
            button_frame,
            text="Forget",
            width=72,
            fg_color=("gray70", "gray30"),
            hover_color=("#c85c54", "#8f3b36"),
            command=lambda name=ssid: self.forget_profile_action(name),
        )
        forget_button.pack(side="left", padx=(0, 8))
        self.action_buttons.append(forget_button)
        self._add_connection_button(button_frame, ssid, network, is_connected)

    def _create_card(self, is_connected):
        card = ctk.CTkFrame(
            self.main_frame,
            border_width=1 if is_connected else 0,
            border_color=("#2f80ed", "#4c9aff"),
        )
        card.pack(fill="x", padx=2, pady=6)
        card.grid_columnconfigure(1, weight=1)
        return card

    def _add_key_button(self, parent, ssid):
        button = ctk.CTkButton(
            parent,
            text="Key",
            width=58,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            command=lambda name=ssid: self.show_password_action(name),
        )
        button.pack(side="left", padx=(0, 8))
        self.action_buttons.append(button)

    def _add_connection_button(self, parent, ssid, network, is_connected):
        if is_connected:
            button = ctk.CTkButton(
                parent,
                text="Disconnect",
                width=92,
                fg_color="#c0392b",
                hover_color="#962d22",
                command=self.disconnect_action,
            )
        else:
            button = ctk.CTkButton(
                parent,
                text="Connect",
                width=86,
                command=lambda item=network, name=ssid: self.connect_action(item, name),
            )
        button.pack(side="left")
        self.action_buttons.append(button)

    def show_password_action(self, ssid):
        if self.busy:
            return
        if not messagebox.askyesno(
            "Access saved key",
            f"Open the saved Wi-Fi key for {ssid}?\n\nAnyone viewing your screen may be able to see it.",
            parent=self,
        ):
            return

        self._set_busy(True, f"Retrieving key for {ssid}...")

        def show_password(password):
            self._set_busy(False, "Ready")
            if password:
                SavedKeyDialog(self, ssid, password)
            else:
                messagebox.showerror(
                    "Key unavailable",
                    "Windows did not return a saved key. Administrator access may be required.",
                    parent=self,
                )

        self._submit_task(lambda: self.backend.get_profile_password(ssid), show_password)

    def connect_action(self, network=None, ssid=None):
        if self.busy:
            return
        ssid = ssid or network["ssid"]

        if ssid in self.saved_profiles:
            operation = lambda: self.backend.connect_to_profile(ssid)
        elif network and self.backend.is_open_network(network["auth"]):
            operation = lambda: self.backend.connect_new_network(ssid, network["auth"])
        elif network and self.backend.supports_password_profile(network["auth"]):
            password = simpledialog.askstring(
                "Connect to network",
                f"Enter the password for {ssid}:",
                show="*",
                parent=self,
            )
            if password is None:
                return
            if not self.backend.is_valid_passphrase(password):
                messagebox.showerror(
                    "Invalid password",
                    "Use 8-63 characters, or a 64-digit hexadecimal key.",
                    parent=self,
                )
                return
            operation = lambda: self.backend.connect_new_network(
                ssid, network["auth"], password
            )
        else:
            messagebox.showinfo(
                "Network unavailable",
                "This profile is not currently in range, or Windows requires additional setup.",
                parent=self,
            )
            return

        self._cancel_auto_refresh()
        self._set_busy(True, f"Connecting to {ssid}...")

        def connect_and_reload():
            operation()
            if not self.backend.wait_for_connection(ssid):
                raise WiFiBackendError(
                    f"Windows did not connect to {ssid}. Check its availability and credentials."
                )
            return self._load_snapshot()

        self._submit_task(
            connect_and_reload,
            lambda snapshot: self._finish_refresh(snapshot, f"Connected to {ssid}"),
        )

    def disconnect_action(self):
        if self.busy:
            return
        self._cancel_auto_refresh()
        self._set_busy(True, "Disconnecting...")

        def disconnect_and_reload():
            self.backend.disconnect()
            if not self.backend.wait_for_disconnection():
                raise WiFiBackendError("Windows did not disconnect from the network.")
            return self._load_snapshot()

        self._submit_task(
            disconnect_and_reload,
            lambda snapshot: self._finish_refresh(snapshot, "Disconnected"),
        )

    def forget_profile_action(self, ssid):
        if self.busy:
            return
        connected_note = (
            "\n\nThis is the active network. Its credentials will no longer be saved."
            if ssid == self.current_ssid
            else ""
        )
        if not messagebox.askyesno(
            "Forget saved network",
            f"Remove the saved profile for {ssid}?{connected_note}",
            icon="warning",
            parent=self,
        ):
            return

        self._cancel_auto_refresh()
        self._set_busy(True, f"Forgetting {ssid}...")

        def forget_and_reload():
            self.backend.delete_profile(ssid)
            return self._load_snapshot()

        self._submit_task(
            forget_and_reload,
            lambda snapshot: self._finish_refresh(snapshot, f"Forgot {ssid}"),
        )

    def _set_view(self, value):
        self.view_mode = value
        if value == "Saved profiles":
            self.header_title.configure(text="Saved profiles")
            self.search_entry.configure(placeholder_text="Search saved profiles")
            self.filter_control.grid_remove()
        else:
            self.header_title.configure(text="Nearby networks")
            self.search_entry.configure(placeholder_text="Search networks")
            self.filter_control.grid()
        self._render_content()

    def _set_filter(self, value):
        self.filter_mode = value
        self._render_content()

    def _set_busy(self, busy, status):
        self.busy = busy
        self.status_label.configure(text=status)
        self.refresh_button.configure(state="disabled" if busy else "normal")
        self._update_action_button_states()

    def _update_action_button_states(self):
        state = "disabled" if self.busy else "normal"
        for button in self.action_buttons:
            if button.winfo_exists():
                button.configure(state=state)

    def _update_connection_panel(self):
        info = self.connection_info
        if not info:
            self.current_net_label.configure(
                text="Not connected",
                text_color=("gray40", "gray65"),
            )
            self.connection_meta_label.configure(text="No active Wi-Fi connection")
            return

        self.current_net_label.configure(
            text=info["ssid"],
            text_color=("#16734a", "#4cd49a"),
        )
        details = []
        if info.get("signal") is not None:
            details.append(f"{info['signal']}% signal")
        location = "  |  ".join(
            item
            for item in (
                info.get("band"),
                f"Channel {info['channel']}" if info.get("channel") else None,
            )
            if item
        )
        if location:
            details.append(location)
        if info.get("radio_type"):
            details.append(info["radio_type"])
        if info.get("receive_rate") is not None or info.get("transmit_rate") is not None:
            receive = self._format_rate(info.get("receive_rate"))
            transmit = self._format_rate(info.get("transmit_rate"))
            details.append(f"Rx {receive}  |  Tx {transmit}")
        self.connection_meta_label.configure(text="\n".join(details))

    def _toggle_auto_refresh(self):
        if self.auto_refresh_switch.get():
            self.status_label.configure(text="Auto-refresh enabled")
            self._schedule_auto_refresh()
        else:
            self._cancel_auto_refresh()
            self.status_label.configure(text="Auto-refresh disabled")

    def _schedule_auto_refresh(self):
        self._cancel_auto_refresh()
        if self.auto_refresh_switch.get():
            self.auto_refresh_job = self.after(self.AUTO_REFRESH_MS, self._auto_refresh)

    def _cancel_auto_refresh(self):
        if self.auto_refresh_job is not None:
            self.after_cancel(self.auto_refresh_job)
            self.auto_refresh_job = None

    def _auto_refresh(self):
        self.auto_refresh_job = None
        if self.busy:
            self._schedule_auto_refresh()
            return
        self.refresh_networks()

    def _show_empty_state(self, message):
        ctk.CTkLabel(
            self.main_frame,
            text=message,
            font=ctk.CTkFont(size=15),
            text_color=("gray40", "gray65"),
        ).pack(pady=70)

    def _submit_task(self, worker, on_success):
        def run():
            try:
                self.task_results.put(("success", on_success, worker()))
            except Exception as exc:
                self.task_results.put(("error", None, exc))

        threading.Thread(target=run, daemon=True).start()

    def _process_task_results(self):
        while True:
            try:
                result_type, callback, payload = self.task_results.get_nowait()
            except queue.Empty:
                break

            if result_type == "success":
                callback(payload)
            else:
                self._handle_error(payload)
        self.after(75, self._process_task_results)

    def _handle_error(self, error):
        self._set_busy(False, "Operation failed")
        self._schedule_auto_refresh()
        message = str(error) if isinstance(error, WiFiBackendError) else f"Unexpected error: {error}"
        messagebox.showerror("Wi-Fi operation failed", message, parent=self)

    def _close(self):
        self._cancel_auto_refresh()
        self.destroy()

    @staticmethod
    def _signal_color(signal):
        if signal >= 70:
            return "#2e9f6b"
        if signal >= 40:
            return "#d08a24"
        return "#c94b45"

    @staticmethod
    def _format_rate(rate):
        if rate is None:
            return "-"
        return f"{rate:g} Mbps"


if __name__ == "__main__":
    app = WiFiManagerApp()
    app.mainloop()
