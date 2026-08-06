#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gtk, Vte, GLib, Pango, Gdk
import os

class MultiTerm(Gtk.Window):
    def __init__(self):
        super().__init__(title="MultiTerm SSH")
        self.set_default_size(1000, 700)
        
        # CSD HeaderBar (No window manager borders!)
        self.header = Gtk.HeaderBar()
        self.header.set_show_close_button(True)
        self.header.set_title("MultiTerm SSH")
        self.set_titlebar(self.header)
        
        # Tabs container
        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.add(self.notebook)
        
        # Left side: (+) button
        new_tab_btn = Gtk.Button.new_from_icon_name("tab-new-symbolic", Gtk.IconSize.BUTTON)
        new_tab_btn.connect("clicked", self.on_new_tab_clicked)
        new_tab_btn.set_tooltip_text("New Local Tab")
        self.header.pack_start(new_tab_btn)
        
        # Right side: SSH Box
        ssh_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        
        self.user_entry = Gtk.Entry(placeholder_text="User")
        self.user_entry.set_width_chars(10)
        ssh_box.pack_start(self.user_entry, False, False, 0)
        
        self.host_entry = Gtk.Entry(placeholder_text="Host")
        self.host_entry.set_width_chars(15)
        ssh_box.pack_start(self.host_entry, False, False, 0)
        
        self.port_entry = Gtk.Entry(placeholder_text="Port", text="22")
        self.port_entry.set_width_chars(4)
        ssh_box.pack_start(self.port_entry, False, False, 0)
        
        self.pass_entry = Gtk.Entry(placeholder_text="Pass")
        self.pass_entry.set_visibility(False)
        self.pass_entry.set_width_chars(10)
        ssh_box.pack_start(self.pass_entry, False, False, 0)
        
        connect_btn = Gtk.Button(label="Connect SSH")
        connect_btn.get_style_context().add_class("suggested-action")
        connect_btn.connect("clicked", self.on_connect_ssh)
        ssh_box.pack_start(connect_btn, False, False, 0)
        
        self.header.pack_end(ssh_box)
        
        # Load environment
        self.env = []
        for k, v in os.environ.items():
            self.env.append(f"{k}={v}")
        
        # Add first local tab
        self.on_new_tab_clicked(None)
        
    def spawn_terminal(self, command_list, label_text, custom_env=None):
        terminal = Vte.Terminal()
        
        # Native Ubuntu Aubergine theme matching GNOME Terminal
        terminal.set_colors(
            foreground=Gdk.RGBA(1.0, 1.0, 1.0, 1.0),
            background=Gdk.RGBA(48/255.0, 10/255.0, 36/255.0, 1.0),
            palette=[]
        )
        terminal.set_font(Pango.FontDescription("Ubuntu Mono 13"))
        terminal.set_scrollback_lines(10000)
        
        terminal.spawn_cmd = command_list
        terminal.spawn_label = label_text
        
        
        envv = custom_env if custom_env is not None else self.env
        
        # Spawn the process
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
        
        # Tab label with close button
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        label = Gtk.Label(label=label_text)
        close_btn = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.connect("clicked", self.on_close_tab, terminal)
        
        box.pack_start(label, True, True, 0)
        box.pack_start(close_btn, False, False, 0)
        box.show_all()
        
        self.notebook.append_page(terminal, box)
        terminal.show()
        self.notebook.set_current_page(self.notebook.get_n_pages() - 1)
        terminal.grab_focus()

    def on_new_tab_clicked(self, button):
        current_page = self.notebook.get_current_page()
        if current_page >= 0:
            terminal = self.notebook.get_nth_page(current_page)
            if hasattr(terminal, 'spawn_cmd') and terminal.spawn_cmd[0] == "/usr/bin/ssh":
                self.spawn_terminal(terminal.spawn_cmd, terminal.spawn_label)
                return
                
        # Default to local tab
        shell = os.environ.get("SHELL", "/bin/bash")
        self.spawn_terminal([shell], "Local")
        
    def on_connect_ssh(self, button):
        user = self.user_entry.get_text().strip()
        host = self.host_entry.get_text().strip()
        port = self.port_entry.get_text().strip()
        password = self.pass_entry.get_text()
        
        if not host:
            return
            
        if not port:
            port = "22"
            
        # SSH command with ControlMaster for multiplexing
        cm_path = os.path.expanduser("~/.ssh/cm-%r@%h:%p")
        os.makedirs(os.path.expanduser("~/.ssh"), exist_ok=True)
        
        target = host if not user else f"{user}@{host}"
        
        cmd = [
            "/usr/bin/ssh",
            "-o", "ControlMaster=auto",
            "-o", f"ControlPath={cm_path}",
            "-o", "ControlPersist=10m",
            "-p", port,
            target
        ]
        
        custom_env = list(self.env)
        if password:
            askpass_script = os.path.expanduser("~/.multiterm_askpass.sh")
            with open(askpass_script, "w") as f:
                f.write(f"#!/bin/bash\necho \"$MULTITERM_PASS\"\n")
            os.chmod(askpass_script, 0o700)
            
            custom_env.append(f"MULTITERM_PASS={password}")
            custom_env.append(f"SSH_ASKPASS={askpass_script}")
            custom_env.append("SSH_ASKPASS_REQUIRE=force")
            custom_env.append("DISPLAY=dummy:0")
        
        self.spawn_terminal(cmd, f"SSH: {target}", custom_env)

    def on_close_tab(self, button, terminal):
        page_num = self.notebook.page_num(terminal)
        if page_num >= 0:
            self.notebook.remove_page(page_num)
        if self.notebook.get_n_pages() == 0:
            self.destroy()

    def on_child_exited(self, terminal, status):
        self.on_close_tab(None, terminal)

if __name__ == "__main__":
    win = MultiTerm()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
