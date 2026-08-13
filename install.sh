#!/usr/bin/env bash
set -e

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting MultiTerm SSH Installation...${NC}"

# 1. Verify source file exists
if [ ! -f "multiterm.py" ]; then
    echo -e "${RED}Error: multiterm.py not found in the current directory.${NC}"
    echo "Please run this script from the root of the cloned repository."
    exit 1
fi

# 2. Check for required system commands
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

if ! command_exists python3; then
    echo -e "${RED}Error: python3 is not installed.${NC}"
    exit 1
fi

if ! command_exists ssh; then
    echo -e "${RED}Error: ssh client is not installed.${NC}"
    exit 1
fi

# 3. Check for Python dependencies (PyGObject, GTK3, VTE)
echo "Checking Python dependencies..."
if ! python3 -c "import gi; gi.require_version('Gtk', '3.0'); gi.require_version('Vte', '2.91'); from gi.repository import Gtk, Vte" 2>/dev/null; then
    echo -e "${RED}Error: Missing required Python GTK3 or VTE libraries.${NC}"
    echo -e "To install dependencies, run the following command for your system:"
    echo -e "  - Debian/Ubuntu: ${YELLOW}sudo apt install python3-gi gir1.2-vte-2.91 gir1.2-gtk-3.0${NC}"
    echo -e "  - Fedora:        ${YELLOW}sudo dnf install python3-gobject vte291${NC}"
    echo -e "  - Arch Linux:    ${YELLOW}sudo pacman -S python-gobject vte3${NC}"
    exit 1
fi
echo -e "${GREEN}Dependencies satisfied.${NC}"

# 4. Setup directories
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"

echo "Creating directories..."
mkdir -p "$BIN_DIR" "$APP_DIR"

# 5. Install executable
echo "Installing executable..."
cp multiterm.py "$BIN_DIR/multiterm"
chmod +x "$BIN_DIR/multiterm"

# 6. Install Desktop entry
echo "Setting up desktop entry..."
cat > "$APP_DIR/multiterm.desktop" <<EOF
[Desktop Entry]
Version=1.0
Name=MultiTerm SSH
Comment=A custom GTK terminal with native SSH multiplexing tabs
Exec=$BIN_DIR/multiterm
Icon=utilities-terminal
Terminal=false
Type=Application
Categories=System;TerminalEmulator;
Keywords=shell;prompt;command;commandline;cmd;ssh;
StartupNotify=true
EOF

# 7. Update desktop database
if command_exists update-desktop-database; then
    echo "Updating desktop database..."
    update-desktop-database "$APP_DIR" || echo -e "${YELLOW}Warning: update-desktop-database failed, but installation will continue.${NC}"
else
    echo -e "${YELLOW}Warning: update-desktop-database not found. You might need to restart your session or GNOME shell for the app to appear in your menu.${NC}"
fi

# 8. Check if BIN_DIR is in PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "${YELLOW}Warning: $BIN_DIR is not in your PATH.${NC}"
    echo "Consider adding 'export PATH=\"\$HOME/.local/bin:\$PATH\"' to your ~/.bashrc or ~/.zshrc."
fi

echo -e "${GREEN}MultiTerm SSH installed successfully! 🚀${NC}"
echo "You can now launch it from your application menu or by running 'multiterm' in your terminal."
