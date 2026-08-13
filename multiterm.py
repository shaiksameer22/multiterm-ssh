#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gtk, Vte, GLib, Pango, Gdk
import os
import json

CONFIG_DIR = os.path.expanduser("~/.config/multiterm")
PROFILES_FILE = os.path.join(CONFIG_DIR, "profiles.json")
ASKPASS_DIR = os.path.expanduser("~/.local/share/multiterm")
ASKPASS_SCRIPT = os.path.join(ASKPASS_DIR, "askpass.sh")

class MultiTerm(Gtk.Window):
    def __init__(self):
        super().__init__(title="MultiTerm SSH")
        self.set_default_size(1000, 700)
        
        # Force Dark Theme
        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-application-prefer-dark-theme", True)
        
        # Ensure directories exist
        os.makedirs(CONFIG_DIR, exist_ok=True)
        os.makedirs(ASKPASS_DIR, exist_ok=True)
        
        # Secure tmpfs directory for askpass scripts
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
        import tempfile
        self.askpass_dir = tempfile.mkdtemp(prefix="multiterm_", dir=runtime_dir)
            
        self.profiles = self.load_profiles()
        self.settings = self.load_settings()
        self.active_terminal = None
        
        # CSD HeaderBar
        self.header = Gtk.HeaderBar()
        self.header.set_show_close_button(True)
        self.header.set_title("MultiTerm SSH")
        self.set_titlebar(self.header)
        
        # Tabs container
        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.apply_tab_position()
        self.add(self.notebook)
        
        # Left side: (+) button
        new_tab_btn = Gtk.Button.new_from_icon_name("tab-new-symbolic", Gtk.IconSize.BUTTON)
        new_tab_btn.connect("clicked", self.on_new_tab_clicked)
        new_tab_btn.set_tooltip_text("New Local Tab (Ctrl+Shift+T)")
        self.header.pack_start(new_tab_btn)
        
        # Right side: SSH Box & Profiles
        right_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        
        # Profiles Button
        self.profiles_btn = Gtk.MenuButton()
        icon = Gtk.Image.new_from_icon_name("view-list-symbolic", Gtk.IconSize.BUTTON)
        self.profiles_btn.add(icon)
        self.profiles_btn.set_tooltip_text("Saved Profiles")
        self.setup_profiles_popover()
        right_box.pack_start(self.profiles_btn, False, False, 0)
        
        self.user_entry = Gtk.Entry(placeholder_text="User")
        self.user_entry.set_width_chars(10)
        right_box.pack_start(self.user_entry, False, False, 0)
        
        self.host_entry = Gtk.Entry(placeholder_text="Host")
        self.host_entry.set_width_chars(15)
        right_box.pack_start(self.host_entry, False, False, 0)
        
        self.port_entry = Gtk.Entry(placeholder_text="Port", text="22")
        self.port_entry.set_width_chars(4)
        right_box.pack_start(self.port_entry, False, False, 0)
        
        self.pass_entry = Gtk.Entry(placeholder_text="Pass")
        self.pass_entry.set_visibility(False)
        self.pass_entry.set_width_chars(10)
        right_box.pack_start(self.pass_entry, False, False, 0)
        
        connect_btn = Gtk.Button(label="Connect")
        connect_btn.get_style_context().add_class("suggested-action")
        connect_btn.connect("clicked", self.on_connect_ssh)
        right_box.pack_start(connect_btn, False, False, 0)
        
        save_prof_btn = Gtk.Button.new_from_icon_name("document-save-symbolic", Gtk.IconSize.BUTTON)
        save_prof_btn.set_tooltip_text("Save as Profile")
        save_prof_btn.connect("clicked", self.on_save_profile)
        right_box.pack_start(save_prof_btn, False, False, 0)
        
        pref_btn = Gtk.Button.new_from_icon_name("preferences-system-symbolic", Gtk.IconSize.BUTTON)
        pref_btn.set_tooltip_text("Preferences")
        pref_btn.connect("clicked", self.on_preferences_clicked)
        right_box.pack_start(pref_btn, False, False, 0)
        
        self.header.pack_end(right_box)
        
        # Keyboard shortcuts
        self.connect("key-press-event", self.on_key_press)
        
        # Apply window_state
        state = self.settings.get("window_state", "normal")
        if state == "maximized":
            self.maximize()
        elif state == "fullscreen":
            self.fullscreen()

        # Apply hide_titlebar
        if self.settings.get("hide_titlebar", False):
            self.header.hide()

        # Load environment
        self.env = [f"{k}={v}" for k, v in os.environ.items()]
        
        # Add first local tab
        self.on_new_tab_clicked(None)

    def load_settings(self):
        default_settings = {
            "font": "Ubuntu Mono 13",
            "bg_color": "#300A24",
            "fg_color": "#FFFFFF",
            "scrollback_lines": 10000,
            "show_scrollbar": True,
            "cursor_shape": "block",
            "cursor_blink": True,
            "scroll_on_keystroke": True,
            "scroll_on_output": False,
            "allow_bold": True,
            "rewrap_on_resize": True,
            "tab_position": "top",
            "audible_bell": False,
            "bg_opacity": 1.0,
            "copy_on_selection": False,
            "window_state": "normal",
            "hide_titlebar": False,
            "word_chars": "-A-Za-z0-9,./?%&#:_=+@~",
            "scrollback_infinite": False,
            "use_system_font": False
        }
        settings_file = os.path.join(CONFIG_DIR, "settings.json")
        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r") as f:
                    user_settings = json.load(f)
                    if isinstance(user_settings, dict):
                        for k, v in user_settings.items():
                            if k in default_settings and (type(v) == type(default_settings[k]) or (isinstance(v, (int, float)) and isinstance(default_settings[k], (int, float)))):
                                default_settings[k] = v
            except:
                pass
        return default_settings

    def apply_tab_position(self):
        tab_pos_str = self.settings.get("tab_position", "top").lower()
        if tab_pos_str == "bottom":
            self.notebook.set_tab_pos(Gtk.PositionType.BOTTOM)
        elif tab_pos_str == "left":
            self.notebook.set_tab_pos(Gtk.PositionType.LEFT)
        elif tab_pos_str == "right":
            self.notebook.set_tab_pos(Gtk.PositionType.RIGHT)
        else:
            self.notebook.set_tab_pos(Gtk.PositionType.TOP)

    def save_settings(self):
        settings_file = os.path.join(CONFIG_DIR, "settings.json")
        with open(settings_file, "w") as f:
            json.dump(self.settings, f, indent=4)
        os.chmod(settings_file, 0o600)

    def load_profiles(self):
        if os.path.exists(PROFILES_FILE):
            try:
                with open(PROFILES_FILE, "r") as f:
                    return json.load(f)
            except:
                pass
        return []

    def save_profiles(self):
        with open(PROFILES_FILE, "w") as f:
            json.dump(self.profiles, f, indent=4)
        # Restrict permissions to prevent unauthorized access
        os.chmod(PROFILES_FILE, 0o600)
        self.setup_profiles_popover()

    def setup_profiles_popover(self):
        popover = Gtk.Popover()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.set_border_width(10)
        
        if not self.profiles:
            vbox.pack_start(Gtk.Label(label="No profiles saved."), False, False, 0)
        else:
            for prof in self.profiles:
                btn = Gtk.Button(label=f"{prof.get('user', '')}@{prof.get('host', '')}")
                btn.connect("clicked", self.on_profile_clicked, prof)
                
                del_btn = Gtk.Button.new_from_icon_name("edit-delete-symbolic", Gtk.IconSize.BUTTON)
                del_btn.connect("clicked", self.on_delete_profile, prof)
                
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                hbox.pack_start(btn, True, True, 0)
                hbox.pack_start(del_btn, False, False, 0)
                vbox.pack_start(hbox, False, False, 0)
                
        vbox.show_all()
        popover.add(vbox)
        self.profiles_btn.set_popover(popover)

    def on_profile_clicked(self, btn, prof):
        self.user_entry.set_text(prof.get("user", ""))
        self.host_entry.set_text(prof.get("host", ""))
        self.port_entry.set_text(prof.get("port", "22"))
        self.pass_entry.set_text(prof.get("password", ""))
        self.profiles_btn.get_popover().popdown()
        self.on_connect_ssh(None)

    def on_delete_profile(self, btn, prof):
        if prof in self.profiles:
            self.profiles.remove(prof)
            self.save_profiles()
            self.profiles_btn.get_popover().popdown()

    def on_save_profile(self, btn):
        user = self.user_entry.get_text().strip()
        host = self.host_entry.get_text().strip()
        if not host:
            return
            
        port = self.port_entry.get_text().strip() or "22"
        password = self.pass_entry.get_text()
        
        # Update existing profile if it matches host, user, and port
        for p in self.profiles:
            if p.get("host") == host and p.get("user", "") == user and p.get("port", "22") == port:
                p["password"] = password
                self.save_profiles()
                return
                
        prof = {
            "user": user,
            "host": host,
            "port": port,
            "password": password
        }
        self.profiles.append(prof)
        self.save_profiles()

    def on_key_press(self, widget, event):
        state = event.state & Gtk.accelerator_get_default_mod_mask()
        ctrl_shift = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
        ctrl = Gdk.ModifierType.CONTROL_MASK
        
        if state == ctrl_shift:
            if event.keyval in (Gdk.KEY_T, Gdk.KEY_t):
                self.on_new_tab_clicked(None)
                return True
            elif event.keyval in (Gdk.KEY_W, Gdk.KEY_w):
                if self.active_terminal:
                    self.on_close_terminal(None, self.active_terminal)
                return True
            elif event.keyval in (Gdk.KEY_C, Gdk.KEY_c):
                if self.active_terminal:
                    self.active_terminal.copy_clipboard_format(Vte.Format.TEXT)
                return True
            elif event.keyval in (Gdk.KEY_V, Gdk.KEY_v):
                if self.active_terminal:
                    self.active_terminal.paste_clipboard()
                return True
            elif event.keyval in (Gdk.KEY_O, Gdk.KEY_o):
                self.split_active_terminal(Gtk.Orientation.HORIZONTAL)
                return True
            elif event.keyval in (Gdk.KEY_E, Gdk.KEY_e):
                self.split_active_terminal(Gtk.Orientation.VERTICAL)
                return True
        elif state == ctrl:
            if event.keyval == Gdk.KEY_Page_Down:
                self.notebook.next_page()
                return True
            elif event.keyval == Gdk.KEY_Page_Up:
                self.notebook.prev_page()
                return True
        return False

    def create_terminal_widget(self, command_list, label_text, custom_env=None):
        terminal = Vte.Terminal()
        
        bg = Gdk.RGBA()
        bg.parse(self.settings.get("bg_color", "#300A24"))
        bg.alpha = float(self.settings.get("bg_opacity", 1.0))
        fg = Gdk.RGBA()
        fg.parse(self.settings.get("fg_color", "#FFFFFF"))
        
        terminal.set_colors(foreground=fg, background=bg, palette=[])
        if self.settings.get("use_system_font", False):
            terminal.set_font(None)
        else:
            terminal.set_font(Pango.FontDescription(self.settings.get("font", "Ubuntu Mono 13")))
            
        if self.settings.get("scrollback_infinite", False):
            terminal.set_scrollback_lines(-1)
        else:
            terminal.set_scrollback_lines(self.settings.get("scrollback_lines", 10000))
            
        terminal.set_word_char_exceptions(self.settings.get("word_chars", "-A-Za-z0-9,./?%&#:_=+@~"))
        
        # Connect selection-changed to conditionally copy to clipboard
        terminal.connect("selection-changed", lambda term: term.copy_clipboard_format(Vte.Format.TEXT) if self.settings.get("copy_on_selection", False) and term.get_has_selection() else None)
        
        # --- Apply new preferences ---
        shape = self.settings.get("cursor_shape", "block")
        if shape == "underline":
            terminal.set_cursor_shape(Vte.CursorShape.UNDERLINE)
        elif shape == "ibeam":
            terminal.set_cursor_shape(Vte.CursorShape.IBEAM)
        else:
            terminal.set_cursor_shape(Vte.CursorShape.BLOCK)
            
        terminal.set_cursor_blink_mode(Vte.CursorBlinkMode.ON if self.settings.get("cursor_blink", True) else Vte.CursorBlinkMode.OFF)
        terminal.set_scroll_on_keystroke(self.settings.get("scroll_on_keystroke", True))
        terminal.set_scroll_on_output(self.settings.get("scroll_on_output", False))
        terminal.set_allow_bold(self.settings.get("allow_bold", True))
        terminal.set_rewrap_on_resize(self.settings.get("rewrap_on_resize", True))
        terminal.set_audible_bell(self.settings.get("audible_bell", False))
        
        terminal.spawn_cmd = command_list
        terminal.spawn_label = label_text
        terminal.custom_env = custom_env
        
        envv = custom_env if custom_env is not None else self.env
        
        try:
            terminal.spawn_async(
                Vte.PtyFlags.DEFAULT,
                os.environ.get('HOME', '/'),
                command_list,
                envv,
                GLib.SpawnFlags.DEFAULT,
                None, None,
                -1,
                None, None
            )
        except Exception as e:
            print("Failed to spawn:", e)
            
        terminal.connect("child-exited", self.on_child_exited)
        terminal.connect("focus-in-event", self.on_terminal_focus_in)
        terminal.connect("button-press-event", self.on_terminal_button_press)
        
        scrollbar = Gtk.Scrollbar(orientation=Gtk.Orientation.VERTICAL, adjustment=terminal.get_vadjustment())
        if not self.settings.get("show_scrollbar", True):
            scrollbar.set_no_show_all(True)
        
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.pack_start(terminal, True, True, 0)
        box.pack_start(scrollbar, False, False, 0)
        box.terminal = terminal
        
        return box

    def on_terminal_focus_in(self, terminal, event):
        self.active_terminal = terminal

    def spawn_new_tab(self, command_list, label_text, custom_env=None):
        term_box = self.create_terminal_widget(command_list, label_text, custom_env)
        
        tab_root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tab_root.pack_start(term_box, True, True, 0)
        
        label_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        label = Gtk.Label(label=label_text)
        close_btn = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.connect("clicked", lambda b, r=tab_root: self.close_tab_root(r))
        
        label_box.pack_start(label, True, True, 0)
        label_box.pack_start(close_btn, False, False, 0)
        label_box.show_all()
        
        self.notebook.append_page(tab_root, label_box)
        tab_root.show_all()
        self.notebook.set_current_page(self.notebook.get_n_pages() - 1)
        term_box.terminal.grab_focus()

    def auto_split_terminal(self, terminal):
        alloc = terminal.get_allocation()
        if alloc.width > alloc.height:
            self.split_specific_terminal(terminal, Gtk.Orientation.HORIZONTAL)
        else:
            self.split_specific_terminal(terminal, Gtk.Orientation.VERTICAL)

    def duplicate_terminal_in_new_tab(self, terminal):
        if getattr(terminal, 'spawn_cmd', None):
            cmd = terminal.spawn_cmd
            if cmd[0] == "/usr/bin/ssh":
                self.spawn_new_tab(cmd, terminal.spawn_label, getattr(terminal, 'custom_env', None))
                return
        shell = os.environ.get("SHELL", "/bin/bash")
        self.spawn_new_tab([shell], "Local")

    def on_terminal_button_press(self, terminal, event):
        if event.button == 3: # Right click
            self.show_context_menu(terminal, event)
            return True
        return False

    def show_context_menu(self, terminal, event):
        menu = Gtk.Menu()
        menu.attach_to_widget(terminal, None)
        
        item_copy = Gtk.MenuItem(label="Copy")
        item_copy.connect("activate", lambda w: terminal.copy_clipboard_format(Vte.Format.TEXT))
        menu.append(item_copy)
        
        item_paste = Gtk.MenuItem(label="Paste")
        item_paste.connect("activate", lambda w: terminal.paste_clipboard())
        menu.append(item_paste)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        item_autosplit = Gtk.MenuItem(label="Auto Split")
        item_autosplit.connect("activate", lambda w: self.auto_split_terminal(terminal))
        menu.append(item_autosplit)
        
        item_hsplit = Gtk.MenuItem(label="Split Horizontally")
        item_hsplit.connect("activate", lambda w: self.split_specific_terminal(terminal, Gtk.Orientation.HORIZONTAL))
        menu.append(item_hsplit)
        
        item_vsplit = Gtk.MenuItem(label="Split Vertically")
        item_vsplit.connect("activate", lambda w: self.split_specific_terminal(terminal, Gtk.Orientation.VERTICAL))
        menu.append(item_vsplit)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        item_newtab = Gtk.MenuItem(label="Open Tab")
        item_newtab.connect("activate", lambda w: self.duplicate_terminal_in_new_tab(terminal))
        menu.append(item_newtab)
        
        item_close = Gtk.MenuItem(label="Close")
        item_close.connect("activate", lambda w: self.on_close_terminal(None, terminal))
        menu.append(item_close)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        item_zoomin = Gtk.MenuItem(label="Zoom In")
        item_zoomin.connect("activate", lambda w: terminal.set_font_scale(terminal.get_font_scale() + 0.1))
        menu.append(item_zoomin)
        
        item_zoomout = Gtk.MenuItem(label="Zoom Out")
        item_zoomout.connect("activate", lambda w: terminal.set_font_scale(max(0.1, terminal.get_font_scale() - 0.1)))
        menu.append(item_zoomout)
        
        item_zoomreset = Gtk.MenuItem(label="Reset Zoom")
        item_zoomreset.connect("activate", lambda w: terminal.set_font_scale(1.0))
        menu.append(item_zoomreset)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        is_ro = terminal.get_input_enabled() == False
        item_ro = Gtk.CheckMenuItem(label="Read-Only")
        item_ro.set_active(is_ro)
        item_ro.connect("toggled", lambda w: terminal.set_input_enabled(not w.get_active()))
        menu.append(item_ro)
        
        menu.append(Gtk.SeparatorMenuItem())
        item_prefs = Gtk.MenuItem(label="Preferences")
        item_prefs.connect("activate", self.on_preferences_clicked)
        menu.append(item_prefs)
        
        menu.show_all()
        # Destroy menu when selection is made or menu is dismissed
        menu.connect("selection-done", lambda w: w.destroy())
        menu.popup_at_pointer(event)

    def split_active_terminal(self, orientation):
        self.split_specific_terminal(self.active_terminal, orientation)

    def split_specific_terminal(self, term, orientation):
        if not term:
            return
            
        term_box = term.get_parent()
        parent = term_box.get_parent()
        
        # Get exact dimensions to calculate a perfect 50/50 split handle position
        alloc = term_box.get_allocation()
        if orientation == Gtk.Orientation.HORIZONTAL:
            half_size = alloc.width // 2
        else:
            half_size = alloc.height // 2
        
        paned = Gtk.Paned(orientation=orientation)
        
        if isinstance(parent, Gtk.Paned):
            if parent.get_child1() == term_box:
                parent.remove(term_box)
                parent.add1(paned)
            else:
                parent.remove(term_box)
                parent.add2(paned)
        elif isinstance(parent, Gtk.Box):
            parent.remove(term_box)
            parent.pack_start(paned, True, True, 0)
            
        paned.add1(term_box)
        
        new_term_box = self.create_terminal_widget(term.spawn_cmd, term.spawn_label, getattr(term, 'custom_env', None))
        paned.add2(new_term_box)
        paned.show_all()
        
        # Explicitly set the paned position to guarantee perfect 50/50 splits
        paned.set_position(half_size)
        
        new_term_box.terminal.grab_focus()

    def on_new_tab_clicked(self, button):
        if self.active_terminal and getattr(self.active_terminal, 'spawn_cmd', None):
            cmd = self.active_terminal.spawn_cmd
            if cmd[0] == "/usr/bin/ssh":
                self.spawn_new_tab(cmd, self.active_terminal.spawn_label, getattr(self.active_terminal, 'custom_env', None))
                return
                
        shell = os.environ.get("SHELL", "/bin/bash")
        self.spawn_new_tab([shell], "Local")
        
    def on_connect_ssh(self, button):
        user = self.user_entry.get_text().strip()
        host = self.host_entry.get_text().strip()
        port = self.port_entry.get_text().strip() or "22"
        password = self.pass_entry.get_text()
        
        if not host:
            return
            
        cm_path = os.path.expanduser("~/.ssh/cm-%r@%h:%p")
        os.makedirs(os.path.expanduser("~/.ssh"), exist_ok=True)
        
        target = host if not user else f"{user}@{host}"
        
        cmd = [
            "/usr/bin/ssh",
            "-o", "ControlMaster=auto",
            "-o", f"ControlPath={cm_path}",
            "-o", "ControlPersist=10m",
            "-p", port,
            "--",  # Prevent argument injection
            target
        ]
        
        custom_env = list(self.env)
        if password:
            import base64
            import hashlib
            
            # Base64 encode to prevent python/shell injection inside the askpass script
            encoded_pass = base64.b64encode(password.encode()).decode()
            pass_hash = hashlib.sha256(password.encode()).hexdigest()[:12]
            askpass_path = os.path.join(self.askpass_dir, f"askpass_{pass_hash}.py")
            
            if not os.path.exists(askpass_path):
                with open(askpass_path, 'w') as f:
                    f.write(f'#!/usr/bin/env python3\nimport base64\nprint(base64.b64decode("{encoded_pass}").decode())\n')
                os.chmod(askpass_path, 0o500)
                
            custom_env.append(f"SSH_ASKPASS={askpass_path}")
            custom_env.append("SSH_ASKPASS_REQUIRE=force")
            custom_env.append("DISPLAY=dummy:0")
        
        self.spawn_new_tab(cmd, f"SSH: {target}", custom_env)

    def on_close_terminal(self, button, terminal):
        if not terminal: return
        term_box = terminal.get_parent()
        if not term_box: return
        parent = term_box.get_parent()
        if not parent: return
        
        if self.active_terminal == terminal:
            self.active_terminal = None
            
        if isinstance(parent, Gtk.Paned):
            other_child = parent.get_child1() if parent.get_child2() == term_box else parent.get_child2()
            if other_child:
                parent.remove(other_child)
                grandparent = parent.get_parent()
                if isinstance(grandparent, Gtk.Paned):
                    if grandparent.get_child1() == parent:
                        grandparent.remove(parent)
                        grandparent.add1(other_child)
                    else:
                        grandparent.remove(parent)
                        grandparent.add2(other_child)
                elif isinstance(grandparent, Gtk.Box):
                    grandparent.remove(parent)
                    grandparent.pack_start(other_child, True, True, 0)
                parent.destroy()
                
                # Give focus to the remaining split terminal
                if hasattr(other_child, 'terminal'):
                    other_child.terminal.grab_focus()
        elif isinstance(parent, Gtk.Box):
            self.close_tab_root(parent)

    def close_tab_root(self, tab_root):
        page_num = self.notebook.page_num(tab_root)
        if page_num >= 0:
            self.notebook.remove_page(page_num)
            
        if self.active_terminal:
            parent = self.active_terminal.get_parent()
            while parent:
                if parent == tab_root:
                    self.active_terminal = None
                    break
                parent = parent.get_parent()
        
        # CRITICAL: Destroy the hierarchy to terminate running subprocesses
        tab_root.destroy() 
        
        if self.notebook.get_n_pages() == 0:
            self.destroy()

    def on_child_exited(self, terminal, status):
        self.on_close_terminal(None, terminal)

    def on_preferences_clicked(self, btn):
        if hasattr(self, 'pref_dialog') and self.pref_dialog:
            self.pref_dialog.present()
            return
            
        self.pref_dialog = Gtk.Dialog(title="Preferences", parent=self, flags=Gtk.DialogFlags.MODAL)
        dialog = self.pref_dialog
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        dialog.set_default_size(600, 500)
        
        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_border_width(10)
        
        notebook = Gtk.Notebook()
        box.pack_start(notebook, True, True, 0)
        
        # Schema definition
        schema = {
            "Appearance": [
                {"id": "use_system_font", "label": "Use System Font", "type": "bool", "default": False},
                {"id": "font", "label": "Font", "type": "font", "default": "Ubuntu Mono 13"},
                {"id": "bg_color", "label": "Background Color", "type": "color", "default": "#300A24"},
                {"id": "bg_opacity", "label": "Background Opacity", "type": "float", "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05},
                {"id": "fg_color", "label": "Text Color", "type": "color", "default": "#FFFFFF"},
                {"id": "cursor_shape", "label": "Cursor Shape", "type": "combo", "default": "block", "options": [("block", "Block"), ("ibeam", "I-Beam"), ("underline", "Underline")]},
                {"id": "tab_position", "label": "Tab Position", "type": "combo", "default": "top", "options": [("top", "Top"), ("bottom", "Bottom"), ("left", "Left"), ("right", "Right")]},
                {"id": "window_state", "label": "Window State", "type": "combo", "default": "normal", "options": [("normal", "Normal"), ("maximized", "Maximized"), ("fullscreen", "Fullscreen")]},
                {"id": "hide_titlebar", "label": "Hide Titlebar", "type": "bool", "default": False},
                {"id": "allow_bold", "label": "Allow Bold Text", "type": "bool", "default": True},
            ],
            "Behavior": [
                {"id": "scrollback_infinite", "label": "Infinite Scrollback", "type": "bool", "default": False},
                {"id": "scrollback_lines", "label": "Scrollback Lines", "type": "int", "default": 10000, "min": 100, "max": 100000, "step": 100},
                {"id": "show_scrollbar", "label": "Show Scrollbar", "type": "bool", "default": True},
                {"id": "cursor_blink", "label": "Cursor Blink", "type": "bool", "default": True},
                {"id": "scroll_on_keystroke", "label": "Scroll on Keystroke", "type": "bool", "default": True},
                {"id": "scroll_on_output", "label": "Scroll on Output", "type": "bool", "default": False},
                {"id": "rewrap_on_resize", "label": "Rewrap on Resize", "type": "bool", "default": True},
                {"id": "audible_bell", "label": "Audible Bell", "type": "bool", "default": False},
                {"id": "copy_on_selection", "label": "Copy on Selection", "type": "bool", "default": False},
                {"id": "word_chars", "label": "Word Characters", "type": "string", "default": "-A-Za-z0-9,./?%&#:_=+@~"},
            ]
        }
        
        widgets_map = {}
        
        for tab_name, settings_list in schema.items():
            grid = Gtk.Grid(column_spacing=10, row_spacing=10)
            grid.set_border_width(10)
            
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scrolled.add(grid)
            
            notebook.append_page(scrolled, Gtk.Label(label=tab_name))
            
            for row, item in enumerate(settings_list):
                grid.attach(Gtk.Label(label=item["label"] + ":"), 0, row, 1, 1)
                
                val = self.settings.get(item["id"], item["default"])
                w = None
                
                if item["type"] == "bool":
                    w = Gtk.CheckButton()
                    w.set_active(val)
                elif item["type"] == "font":
                    w = Gtk.FontButton.new_with_font(val)
                elif item["type"] == "color":
                    rgba = Gdk.RGBA()
                    rgba.parse(val)
                    w = Gtk.ColorButton(rgba=rgba)
                elif item["type"] == "combo":
                    w = Gtk.ComboBoxText()
                    for opt_id, opt_lbl in item["options"]:
                        w.append(opt_id, opt_lbl)
                    w.set_active_id(val)
                elif item["type"] == "int":
                    adj = Gtk.Adjustment(value=val, lower=item["min"], upper=item["max"], step_increment=item["step"])
                    w = Gtk.SpinButton(adjustment=adj, numeric=True)
                elif item["type"] == "float":
                    adj = Gtk.Adjustment(value=val, lower=item["min"], upper=item["max"], step_increment=item["step"])
                    w = Gtk.SpinButton(adjustment=adj, numeric=False, digits=2)
                elif item["type"] == "string":
                    w = Gtk.Entry()
                    w.set_text(val)
                    
                if w:
                    w.set_hexpand(True)
                    grid.attach(w, 1, row, 1, 1)
                    widgets_map[item["id"]] = {"widget": w, "type": item["type"]}
        
        box.show_all()
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            for sid, info in widgets_map.items():
                w = info["widget"]
                t = info["type"]
                if t == "bool":
                    self.settings[sid] = w.get_active()
                elif t == "font":
                    self.settings[sid] = w.get_font_name()
                elif t == "color":
                    self.settings[sid] = w.get_rgba().to_string()
                elif t == "combo":
                    self.settings[sid] = w.get_active_id()
                elif t == "int":
                    self.settings[sid] = int(w.get_value())
                elif t == "float":
                    self.settings[sid] = w.get_value()
                elif t == "string":
                    self.settings[sid] = w.get_text()
        grid_beh.attach(bell_check, 1, 6, 1, 1)
        
        box.show_all()
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.settings["font"] = font_btn.get_font_name()
            self.settings["bg_color"] = bg_btn.get_rgba().to_string()
            self.settings["fg_color"] = fg_btn.get_rgba().to_string()
            self.settings["scrollback_lines"] = int(scroll_spin.get_value())
            self.settings["show_scrollbar"] = scroll_check.get_active()
            
            self.settings["cursor_shape"] = cursor_combo.get_active_id() or "block"
            self.settings["tab_position"] = tab_combo.get_active_id() or "top"
            self.settings["allow_bold"] = allow_bold_check.get_active()
            
            self.settings["cursor_blink"] = blink_check.get_active()
            self.settings["scroll_on_keystroke"] = scroll_key_check.get_active()
            self.settings["scroll_on_output"] = scroll_out_check.get_active()
            self.settings["rewrap_on_resize"] = rewrap_check.get_active()
            self.settings["audible_bell"] = bell_check.get_active()
            
            self.save_settings()
            self.apply_settings_to_all_terminals()
            
        dialog.destroy()
        self.pref_dialog = None

    def apply_settings_to_all_terminals(self):
        bg = Gdk.RGBA()
        bg.parse(self.settings.get("bg_color", "#300A24"))
        bg.alpha = float(self.settings.get("bg_opacity", 1.0))
        fg = Gdk.RGBA()
        fg.parse(self.settings.get("fg_color", "#FFFFFF"))
        
        use_sys_font = self.settings.get("use_system_font", False)
        font_desc = None if use_sys_font else Pango.FontDescription(self.settings.get("font", "Ubuntu Mono 13"))
        
        infinite_scroll = self.settings.get("scrollback_infinite", False)
        lines = -1 if infinite_scroll else self.settings.get("scrollback_lines", 10000)
        
        show_sb = self.settings.get("show_scrollbar", True)
        word_chars = self.settings.get("word_chars", "-A-Za-z0-9,./?%&#:_=+@~")
        
        shape_str = self.settings.get("cursor_shape", "block")
        if shape_str == "underline":
            cursor_shape = Vte.CursorShape.UNDERLINE
        elif shape_str == "ibeam":
            cursor_shape = Vte.CursorShape.IBEAM
        else:
            cursor_shape = Vte.CursorShape.BLOCK
            
        cursor_blink = Vte.CursorBlinkMode.ON if self.settings.get("cursor_blink", True) else Vte.CursorBlinkMode.OFF
        scroll_key = self.settings.get("scroll_on_keystroke", True)
        scroll_out = self.settings.get("scroll_on_output", False)
        allow_bold = self.settings.get("allow_bold", True)
        rewrap = self.settings.get("rewrap_on_resize", True)
        bell = self.settings.get("audible_bell", False)
        
        self.apply_tab_position()
        
        # Apply window state
        state = self.settings.get("window_state", "normal")
        if state == "maximized":
            self.maximize()
        elif state == "fullscreen":
            self.fullscreen()
        else:
            self.unmaximize()
            self.unfullscreen()
            
        # Apply hide titlebar
        if self.settings.get("hide_titlebar", False):
            self.header.hide()
        else:
            self.header.show()
        
        def update_widget(widget):
            if isinstance(widget, Vte.Terminal):
                widget.set_colors(foreground=fg, background=bg, palette=[])
                if font_desc:
                    widget.set_font(font_desc)
                else:
                    widget.set_font(None)
                widget.set_scrollback_lines(lines)
                widget.set_word_char_exceptions(word_chars)
                
                widget.set_cursor_shape(cursor_shape)
                widget.set_cursor_blink_mode(cursor_blink)
                widget.set_scroll_on_keystroke(scroll_key)
                widget.set_scroll_on_output(scroll_out)
                widget.set_allow_bold(allow_bold)
                widget.set_rewrap_on_resize(rewrap)
                widget.set_audible_bell(bell)
                
            elif isinstance(widget, Gtk.Scrollbar):
                if show_sb:
                    widget.set_no_show_all(False)
                    widget.show()
                else:
                    widget.hide()
                    widget.set_no_show_all(True)
            if isinstance(widget, Gtk.Container):
                widget.foreach(update_widget)
                
        self.notebook.foreach(update_widget)
        self.notebook.show_all()

    def cleanup(self):
        import shutil
        try:
            shutil.rmtree(self.askpass_dir)
        except Exception:
            pass

if __name__ == "__main__":
    win = MultiTerm()
    win.connect("destroy", lambda w: (win.cleanup(), Gtk.main_quit()))
    win.show_all()
    Gtk.main()
