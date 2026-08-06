# MultiTerm SSH 🚀

MultiTerm SSH is a **100% native Linux GTK3 terminal emulator** built with Python and VTE (the exact same core engine that powers GNOME Terminal). 

It was built specifically to solve the biggest annoyance in remote development: **SSH connection management.**

MultiTerm natively integrates an SSH connection bar into a sleek, borderless Client-Side Decoration (CSD) header bar. Once you connect to a server, MultiTerm uses advanced SSH socket multiplexing (`ControlMaster`) behind the scenes. This allows you to instantly open unlimited clone tabs to the same server—completely bypassing password prompts on all subsequent tabs!

## ✨ Key Features
- **Zero Borders**: Uses native GTK3 HeaderBars for a sleek, edge-to-edge dark appearance (matching native Ubuntu Aubergine aesthetics).
- **Native Rendering**: Powered by VTE, ensuring 100% compatibility with all Linux terminal applications, color codes, and features.
- **Magic SSH Multiplexing**: Log in once natively, open infinite tabs instantly.
- **Context-Aware Tabs**: Clicking `(+)` while viewing a local tab opens a new local bash tab. Clicking it while viewing an SSH tab instantly clones that SSH connection.
- **Auto Password Injection**: Seamlessly hands your password to `ssh` using `SSH_ASKPASS`, completely hiding the interactive prompt.

---

## 🐧 Installation (Debian / Ubuntu / Linux Mint)

### 1. Install Dependencies
MultiTerm relies on standard Python 3 GTK bindings and the VTE terminal widget. Install them via your package manager:
```bash
sudo apt-get update
sudo apt-get install -y python3-gi gir1.2-vte-2.91 gir1.2-gtk-3.0
```

### 2. Install MultiTerm
Clone this repository and run the installation script. This will place the executable in your local `bin` folder and integrate it into your system's application launcher.
```bash
git clone https://github.com/shaiksameer22/multiterm-ssh.git
cd multiterm-ssh
./install.sh
```

You can now search for **MultiTerm SSH** in your Application Menu (GNOME Activities, Dash, etc.) and pin it to your dock!

---

## 🪟 Installation (Windows)

Because MultiTerm uses deep, native Linux GTK integration for its seamless UI and terminal emulation, it is designed for Linux. 

However, you can run it perfectly on Windows 10 and 11 using **WSL2** (Windows Subsystem for Linux) and **WSLg** (which provides native GUI support).

### 1. Install WSL2 (if you haven't already)
Open PowerShell as Administrator and run:
```powershell
wsl --install
```
*Restart your computer if prompted, and complete the Ubuntu setup.*

### 2. Install inside Ubuntu (WSL)
Open your WSL Ubuntu terminal and follow the exact same steps as Linux:
```bash
sudo apt-get update
sudo apt-get install -y python3-gi gir1.2-vte-2.91 gir1.2-gtk-3.0
git clone https://github.com/shaiksameer22/multiterm-ssh.git
cd multiterm-ssh
./install.sh
```

### 3. Launch from Windows
Thanks to WSLg, MultiTerm SSH will actually appear in your native **Windows Start Menu**! Just press the Windows key, search for **MultiTerm SSH**, and it will launch perfectly as a floating GUI application on your Windows desktop.

---

## 🛠️ Usage
1. **Local Tabs**: Upon launching, a standard local `bash` terminal opens.
2. **SSH Connection**: Fill in your `User`, `Host`, `Port`, and `Pass` in the top right. Click **Connect SSH**.
3. **Cloning Tabs**: While focused on an SSH tab, simply hit the `(+)` button in the top left. A new tab will instantly spawn connected to the same server—no password required.

## 🤝 Contributing
Feel free to fork this project and submit pull requests. MultiTerm is designed to be the absolute best lightweight SSH-focused terminal for power users!
