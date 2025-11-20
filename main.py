import customtkinter as ctk
from wifi_backend import WiFiBackend
import threading
from tkinter import messagebox
import time

ctk.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

class WiFiManagerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("WiFi Manager")
        self.geometry("800x600")

        self.backend = WiFiBackend()
        self.networks = []
        self.saved_profiles = []
        self.current_ssid = None

        # Layout configuration
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._create_sidebar()
        self._create_main_area()

        # Initial scan
        self.refresh_networks()

    def _create_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="WiFi Manager", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.refresh_button = ctk.CTkButton(self.sidebar_frame, text="Refresh Networks", command=self.refresh_networks)
        self.refresh_button.grid(row=1, column=0, padx=20, pady=10)

        self.status_label = ctk.CTkLabel(self.sidebar_frame, text="Status: Idle", anchor="w")
        self.status_label.grid(row=2, column=0, padx=20, pady=(10, 0))
        
        self.current_net_label = ctk.CTkLabel(self.sidebar_frame, text="Not Connected", anchor="w", text_color="gray")
        self.current_net_label.grid(row=3, column=0, padx=20, pady=(0, 10))

    def _create_main_area(self):
        self.main_frame = ctk.CTkScrollableFrame(self, label_text="Available Networks")
        self.main_frame.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")

    def refresh_networks(self):
        self.status_label.configure(text="Status: Scanning...")
        self.refresh_button.configure(state="disabled")
        
        # Run in thread to avoid freezing UI
        thread = threading.Thread(target=self._scan_thread)
        thread.start()

    def _scan_thread(self):
        self.networks = self.backend.scan_networks()
        self.current_ssid = self.backend.get_current_connection()
        self.saved_profiles = self.backend.get_saved_profiles()
        self.after(0, self._update_ui_after_scan)

    def _update_ui_after_scan(self):
        # Clear existing items
        for widget in self.main_frame.winfo_children():
            widget.destroy()

        # Update status
        self.status_label.configure(text="Status: Idle")
        self.refresh_button.configure(state="normal")
        
        if self.current_ssid:
            self.current_net_label.configure(text=f"Connected: {self.current_ssid}", text_color="green")
        else:
            self.current_net_label.configure(text="Not Connected", text_color="gray")

        # Populate list
        for net in self.networks:
            self._create_network_item(net)

    def _create_network_item(self, net):
        ssid = net['ssid']
        signal = net['signal']
        auth = net['auth']
        
        is_connected = (ssid == self.current_ssid)
        is_saved = (ssid in self.saved_profiles)
        
        card = ctk.CTkFrame(self.main_frame)
        card.pack(fill="x", padx=5, pady=5)
        
        # Icon/Signal
        signal_text = f"{signal}%"
        icon_label = ctk.CTkLabel(card, text=signal_text, width=40)
        icon_label.pack(side="left", padx=10)
        
        # Info
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.pack(side="left", fill="x", expand=True, padx=5)
        
        name_label = ctk.CTkLabel(info_frame, text=ssid, font=ctk.CTkFont(size=14, weight="bold"), anchor="w")
        name_label.pack(fill="x")
        
        details_text = f"Security: {auth}"
        if is_saved:
            details_text += " (Saved)"
        details_label = ctk.CTkLabel(info_frame, text=details_text, font=ctk.CTkFont(size=10), text_color="gray", anchor="w")
        details_label.pack(fill="x")
        
        # Buttons Frame
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="right", padx=10, pady=10)

        # Show Password Button (only if saved)
        if is_saved:
            pass_btn = ctk.CTkButton(btn_frame, text="Key", width=40, fg_color="gray", hover_color="darkgray",
                                     command=lambda s=ssid: self.show_password_action(s))
            pass_btn.pack(side="left", padx=5)

        # Connect/Disconnect Button
        if is_connected:
            btn = ctk.CTkButton(btn_frame, text="Disconnect", fg_color="red", hover_color="darkred", width=80,
                                command=lambda: self.disconnect_action())
        else:
            btn = ctk.CTkButton(btn_frame, text="Connect", width=80,
                                command=lambda s=ssid: self.connect_action(s))
        btn.pack(side="left", padx=5)

    def show_password_action(self, ssid):
        password = self.backend.get_profile_password(ssid)
        if password:
            messagebox.showinfo(f"Password for {ssid}", f"Password: {password}")
            # Also copy to clipboard? Maybe later.
        else:
            messagebox.showerror("Error", f"Could not retrieve password for {ssid}")

    def connect_action(self, ssid):
        # Check if we need a password (simple check based on auth string)
        # In a real app, we'd check if a profile exists first.
        # For this demo, we'll ask for password if it's not Open.
        
        # Ideally we check if profile exists:
        # if self.backend.has_profile(ssid): ...
        # But for now let's just prompt if it looks secure.
        
        dialog = ctk.CTkInputDialog(text=f"Enter password for {ssid}:", title="Connect to Network")
        password = dialog.get_input()
        
        if password is not None: # User didn't cancel
            self.status_label.configure(text=f"Connecting to {ssid}...")
            
            def run_connect():
                if password:
                    res = self.backend.connect_with_password(ssid, password)
                else:
                    # Try connecting without password (open or saved)
                    res = self.backend.connect_to_profile(ssid)
                
                print(res) # Debug
                # Refresh after a delay
                time.sleep(3) 
                self.refresh_networks()

            threading.Thread(target=run_connect).start()

    def disconnect_action(self):
        self.status_label.configure(text="Disconnecting...")
        def run_disconnect():
            self.backend.disconnect()
            time.sleep(1)
            self.refresh_networks()
            
        threading.Thread(target=run_disconnect).start()

if __name__ == "__main__":
    app = WiFiManagerApp()
    app.mainloop()
