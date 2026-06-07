import queue
import threading
from tkinter import messagebox, simpledialog

import customtkinter as ctk

from wifi_backend import WiFiBackend, WiFiBackendError


ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class WiFiManagerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("WiFi Manager")
        self.geometry("920x640")
        self.minsize(760, 520)

        self.backend = WiFiBackend()
        self.networks = []
        self.saved_profiles = set()
        self.current_ssid = None
        self.action_buttons = []
        self.busy = False
        self.filter_mode = "All"
        self.task_results = queue.Queue()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._create_sidebar()
        self._create_main_area()
        self.bind("<F5>", lambda _event: self.refresh_networks())
        self.bind("<Control-f>", lambda _event: self.search_entry.focus_set())
        self.after(75, self._process_task_results)
        self.refresh_networks()

    def _create_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(6, weight=1)

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
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=170,
        )
        self.current_net_label.grid(row=4, column=0, padx=24, pady=(6, 2), sticky="ew")

        self.status_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="Starting",
            anchor="w",
            justify="left",
            wraplength=170,
            text_color=("gray40", "gray65"),
        )
        self.status_label.grid(row=5, column=0, padx=24, sticky="ew")

        ctk.CTkLabel(
            self.sidebar_frame,
            text="APPEARANCE",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("gray40", "gray65"),
        ).grid(row=7, column=0, padx=24, pady=(0, 6), sticky="w")
        self.appearance_menu = ctk.CTkOptionMenu(
            self.sidebar_frame,
            values=["System", "Light", "Dark"],
            command=ctk.set_appearance_mode,
        )
        self.appearance_menu.set("System")
        self.appearance_menu.grid(row=8, column=0, padx=24, pady=(0, 24), sticky="ew")

    def _create_main_area(self):
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=0, column=1, padx=24, pady=22, sticky="nsew")
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Available networks",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        self.summary_label = ctk.CTkLabel(
            header,
            text="Scanning...",
            text_color=("gray40", "gray65"),
        )
        self.summary_label.grid(row=1, column=0, pady=(0, 14), sticky="w")

        controls = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        controls.grid(row=1, column=0, pady=(0, 12), sticky="ew")
        controls.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            controls,
            placeholder_text="Search networks",
            height=36,
        )
        self.search_entry.grid(row=0, column=0, padx=(0, 12), sticky="ew")
        self.search_entry.bind("<KeyRelease>", lambda _event: self._render_networks())

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
        self._set_busy(True, "Scanning for networks...")
        self.summary_label.configure(text="Scanning...")
        self._submit_task(self._load_snapshot, self._finish_refresh)

    def _load_snapshot(self):
        return {
            "networks": self.backend.scan_networks(),
            "current_ssid": self.backend.get_current_connection(),
            "saved_profiles": set(self.backend.get_saved_profiles()),
        }

    def _finish_refresh(self, snapshot, status=None):
        self.networks = snapshot["networks"]
        self.current_ssid = snapshot["current_ssid"]
        self.saved_profiles = snapshot["saved_profiles"]
        self._set_busy(False, status or "Ready")
        self._update_connection_label()
        self._render_networks()

    def _render_networks(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()
        self.action_buttons.clear()

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

        count = len(self.networks)
        saved_count = sum(network["ssid"] in self.saved_profiles for network in self.networks)
        self.summary_label.configure(
            text=f"{count} found  |  {saved_count} saved"
        )

        if not visible:
            message = "No networks match your filters." if self.networks else "No Wi-Fi networks found."
            ctk.CTkLabel(
                self.main_frame,
                text=message,
                font=ctk.CTkFont(size=15),
                text_color=("gray40", "gray65"),
            ).pack(pady=70)
            return

        for network in visible:
            self._create_network_item(network)
        self._update_action_button_states()

    def _create_network_item(self, network):
        ssid = network["ssid"]
        signal = network["signal"]
        is_connected = ssid == self.current_ssid
        is_saved = ssid in self.saved_profiles

        card = ctk.CTkFrame(
            self.main_frame,
            border_width=1 if is_connected else 0,
            border_color=("#2f80ed", "#4c9aff"),
        )
        card.pack(fill="x", padx=2, pady=6)
        card.grid_columnconfigure(1, weight=1)

        signal_frame = ctk.CTkFrame(card, width=94, fg_color="transparent")
        signal_frame.grid(row=0, column=0, padx=(16, 10), pady=16, sticky="ns")
        ctk.CTkLabel(
            signal_frame,
            text=f"{signal}%",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack()
        progress = ctk.CTkProgressBar(signal_frame, width=72, height=6)
        progress.set(max(0, min(signal, 100)) / 100)
        progress.pack(pady=(5, 0))

        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=0, column=1, pady=14, sticky="ew")

        title = ssid + ("  -  Connected" if is_connected else "")
        ctk.CTkLabel(
            info_frame,
            text=title,
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        ).pack(fill="x")

        details = [network["auth"]]
        if network.get("bands"):
            details.append(" / ".join(network["bands"]))
        if is_saved:
            details.append("Saved")
        ctk.CTkLabel(
            info_frame,
            text="  |  ".join(details),
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        button_frame = ctk.CTkFrame(card, fg_color="transparent")
        button_frame.grid(row=0, column=2, padx=14, pady=14)

        if is_saved:
            key_button = ctk.CTkButton(
                button_frame,
                text="Show key",
                width=74,
                fg_color=("gray70", "gray30"),
                hover_color=("gray60", "gray40"),
                command=lambda name=ssid: self.show_password_action(name),
            )
            key_button.pack(side="left", padx=(0, 8))
            self.action_buttons.append(key_button)

        if is_connected:
            action_button = ctk.CTkButton(
                button_frame,
                text="Disconnect",
                width=92,
                fg_color="#c0392b",
                hover_color="#962d22",
                command=self.disconnect_action,
            )
        else:
            action_button = ctk.CTkButton(
                button_frame,
                text="Connect",
                width=92,
                command=lambda item=network: self.connect_action(item),
            )
        action_button.pack(side="left")
        self.action_buttons.append(action_button)

    def show_password_action(self, ssid):
        if self.busy:
            return
        if not messagebox.askyesno(
            "Show saved key",
            f"Reveal the saved Wi-Fi key for {ssid}?\n\nAnyone viewing your screen can see it.",
            parent=self,
        ):
            return

        self._set_busy(True, f"Retrieving key for {ssid}...")

        def show_password(password):
            self._set_busy(False, "Ready")
            if password:
                messagebox.showinfo(
                    f"Saved key for {ssid}",
                    password,
                    parent=self,
                )
            else:
                messagebox.showerror(
                    "Key unavailable",
                    "Windows did not return a saved key. Administrator access may be required.",
                    parent=self,
                )

        self._submit_task(
            lambda: self.backend.get_profile_password(ssid),
            show_password,
        )

    def connect_action(self, network):
        if self.busy:
            return
        ssid = network["ssid"]
        authentication = network["auth"]

        if ssid in self.saved_profiles:
            operation = lambda: self.backend.connect_to_profile(ssid)
        elif self.backend.is_open_network(authentication):
            operation = lambda: self.backend.connect_new_network(ssid, authentication)
        elif self.backend.supports_password_profile(authentication):
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
                ssid, authentication, password
            )
        else:
            messagebox.showinfo(
                "Windows setup required",
                f"{authentication} networks need credentials or certificates configured through Windows.",
                parent=self,
            )
            return

        self._set_busy(True, f"Connecting to {ssid}...")

        def connect_and_reload():
            operation()
            if not self.backend.wait_for_connection(ssid):
                raise WiFiBackendError(
                    f"Windows did not connect to {ssid}. Check the password and signal."
                )
            return self._load_snapshot()

        self._submit_task(
            connect_and_reload,
            lambda snapshot: self._finish_refresh(snapshot, f"Connected to {ssid}"),
        )

    def disconnect_action(self):
        if self.busy:
            return
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

    def _set_filter(self, value):
        self.filter_mode = value
        self._render_networks()

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

    def _update_connection_label(self):
        if self.current_ssid:
            self.current_net_label.configure(
                text=self.current_ssid,
                text_color=("#16734a", "#4cd49a"),
            )
        else:
            self.current_net_label.configure(
                text="Not connected",
                text_color=("gray40", "gray65"),
            )

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
        message = str(error) if isinstance(error, WiFiBackendError) else f"Unexpected error: {error}"
        messagebox.showerror("Wi-Fi operation failed", message, parent=self)


if __name__ == "__main__":
    app = WiFiManagerApp()
    app.mainloop()
