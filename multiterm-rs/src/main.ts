import '@xterm/xterm/css/xterm.css';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import Split from 'split.js';
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

interface AppSettings {
  fontFamily: string;
  fontSize: number;
  bgColor: string;
  fgColor: string;
  cursorStyle: 'block' | 'underline' | 'bar';
  cursorBlink: boolean;
  scrollback: number;
  rightClickSelectsWord: boolean;
}

const defaultSettings: AppSettings = {
  fontFamily: '"Fira Code", Consolas, "Courier New", monospace',
  fontSize: 14,
  bgColor: '#1e1e1e',
  fgColor: '#f6f6f6',
  cursorStyle: 'block',
  cursorBlink: true,
  scrollback: 10000,
  rightClickSelectsWord: true,
};

function loadSettings(): AppSettings {
  const saved = localStorage.getItem('multitermSettings');
  if (saved) {
    try {
      return { ...defaultSettings, ...JSON.parse(saved) };
    } catch (e) {
      console.error("Failed to parse settings", e);
    }
  }
  const oldBg = localStorage.getItem('termBgColor');
  if (oldBg) {
    return { ...defaultSettings, bgColor: oldBg };
  }
  return { ...defaultSettings };
}

let appSettings = loadSettings();

function saveSettings(newSettings: Partial<AppSettings>) {
  appSettings = { ...appSettings, ...newSettings };
  localStorage.setItem('multitermSettings', JSON.stringify(appSettings));
  applySettingsToAllTerminals();
}

function applySettingsToAllTerminals() {
  terminalInstances.forEach(t => {
    t.term.options.fontFamily = appSettings.fontFamily;
    t.term.options.fontSize = appSettings.fontSize;
    t.term.options.theme = {
      background: appSettings.bgColor,
      foreground: appSettings.fgColor,
      cursor: appSettings.fgColor,
      selectionBackground: '#3d3d3d',
    };
    t.term.options.cursorStyle = appSettings.cursorStyle;
    t.term.options.cursorBlink = appSettings.cursorBlink;
    t.term.options.scrollback = appSettings.scrollback;
    t.term.options.rightClickSelectsWord = appSettings.rightClickSelectsWord;

    t.pane.style.backgroundColor = appSettings.bgColor;
    t.fitAddon.fit();
  });
}

interface TerminalInstance {
  id: string; // The split.js pane ID
  ptyId: string | null; // The Rust PTY UUID
  pane: HTMLElement;
  term: Terminal;
  fitAddon: FitAddon;
  decoder: TextDecoder;
  command?: string;
  args?: string[];
}

const terminalInstances: TerminalInstance[] = [];
let splitInstance: Split.Instance | null = null;
let container: HTMLElement;

let activeTerminalId: string | null = null;
let isBroadcastMode = false;
let terminalIdCounter = 0;

async function createTerminalPane(command?: string, args?: string[]): Promise<TerminalInstance> {
  terminalIdCounter++;
  const id = `term-${terminalIdCounter}`;
  
  const pane = document.createElement('div');
  pane.className = 'terminal-pane';
  pane.id = id;
  container.appendChild(pane);

  pane.style.backgroundColor = appSettings.bgColor;

  const term = new Terminal({
    theme: {
      background: appSettings.bgColor,
      foreground: appSettings.fgColor,
      cursor: appSettings.fgColor,
      selectionBackground: '#3d3d3d',
    },
    cursorBlink: appSettings.cursorBlink,
    cursorStyle: appSettings.cursorStyle,
    fontFamily: appSettings.fontFamily,
    fontSize: appSettings.fontSize,
    scrollback: appSettings.scrollback,
    rightClickSelectsWord: appSettings.rightClickSelectsWord,
    windowsMode: true,
  } as any);

  term.attachCustomKeyEventHandler((e) => {
    if (e.ctrlKey && e.shiftKey) {
      const key = e.key.toLowerCase();
      if (['d', 't', 'w', 'b', 'p', 'e'].includes(key)) {
        if (e.type === 'keydown') {
          return false;
        }
      }
    }
    return true;
  });

  // Regex Highlighting via LinkProvider (IP Addresses for MVP)
  term.registerLinkProvider({
    provideLinks(bufferLineNumber: number, callback: (links: any[] | undefined) => void): void {
      const line = term.buffer.active.getLine(bufferLineNumber - 1)?.translateToString(true) || '';
      const links: any[] = [];
      const ipRegex = /\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b/g;
      let match;
      while ((match = ipRegex.exec(line)) !== null) {
        links.push({
          range: {
            start: { x: match.index + 1, y: bufferLineNumber },
            end: { x: match.index + match[0].length, y: bufferLineNumber }
          },
          text: match[0],
          activate: (_e: Event, text: string) => {
            // Copy to clipboard or trigger action
            navigator.clipboard.writeText(text).catch(console.error);
          }
        });
      }
      callback(links.length > 0 ? links : undefined);
    }
  });

  // OSC 1337 Interceptor for File Exfiltration
  term.parser.registerOscHandler(1337, (data) => {
    if (data.startsWith('File=')) {
      const b64Data = data.split('inline=1:')[1];
      if (b64Data) {
        try {
          const byteCharacters = atob(b64Data);
          const byteNumbers = new Array(byteCharacters.length);
          for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i);
          }
          const byteArray = new Uint8Array(byteNumbers);
          const blob = new Blob([byteArray], { type: 'application/gzip' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = 'multiterm_exfil.tar.gz';
          a.click();
          URL.revokeObjectURL(url);
        } catch (err) {
          console.error("Failed to decode exfiltrated payload", err);
        }
      }
    }
    return true; // Hides the sequence from the terminal screen
  });

  const fitAddon = new FitAddon();
  term.loadAddon(fitAddon);
  term.open(pane);

  const instance: TerminalInstance = { id, ptyId: null, pane, term, fitAddon, decoder: new TextDecoder(), command, args };
  terminalInstances.push(instance);

  // Track active terminal via DOM
  pane.addEventListener('focusin', () => {
    activeTerminalId = id;
  });
  pane.addEventListener('click', () => {
    activeTerminalId = id;
  });
  term.focus();

  // We fit first so that the initial rows/cols are accurate before spawning PTY
  fitAddon.fit();

  // Send input to Rust backend, specifying this exact PTY
  term.onData(async (data: string) => {
    if (isBroadcastMode) {
      for (const t of terminalInstances) {
        if (t.ptyId) {
          await invoke("write_pty", { id: t.ptyId, data });
        }
      }
    } else {
      if (instance.ptyId) {
        await invoke("write_pty", { id: instance.ptyId, data });
      }
    }
  });

  // Notify Rust when the terminal window resizes
  term.onResize(async (size) => {
    if (instance.ptyId) {
      await invoke("resize_pty", { id: instance.ptyId, rows: size.rows, cols: size.cols });
    }
  });

  // Ask Rust to spawn a new backend shell asynchronously
  invoke("spawn_pty", {
    rows: term.rows,
    cols: term.cols,
    command,
    args
  }).then((ptyId: any) => {
    instance.ptyId = ptyId as string;
    // CRITICAL: If pane was closed while we were waiting for PTY spawn, clean it up immediately
    if (!terminalInstances.find(t => t.id === id)) {
      invoke("close_pty", { id: ptyId }).catch(console.error);
    }
  }).catch(console.error);

  return instance;
}

function updateSplits() {
  let oldSizes: number[] = [];
  if (splitInstance) {
    oldSizes = splitInstance.getSizes();
    splitInstance.destroy();
    splitInstance = null;
  }

  const paneIds = terminalInstances.map(t => `#${t.id}`);
  
  if (paneIds.length > 1) {
    // Distribute sizes smoothly when adding/removing panes
    let sizes = Array(paneIds.length).fill(100 / paneIds.length);
    if (oldSizes.length > 0 && oldSizes.length === paneIds.length - 1) {
      // Added a pane: scale old ones down slightly, give new one a share
      const newShare = 100 / paneIds.length;
      const scale = (100 - newShare) / 100;
      sizes = [...oldSizes.map(s => s * scale), newShare];
    } else if (oldSizes.length > 0 && oldSizes.length === paneIds.length + 1) {
      // Removed a pane: we just default to equal sizes for MVP, 
      // full proportional redistribution is complex
      sizes = Array(paneIds.length).fill(100 / paneIds.length);
    }
    
    // @ts-ignore
    splitInstance = Split(paneIds, {
      sizes,
      minSize: 100,
      gutterSize: 5,
      direction: 'horizontal',
      onDragEnd: () => {
        terminalInstances.forEach(t => t.fitAddon.fit());
      }
    });
  }
}

async function splitTerminal(command?: string, args?: string[]) {
  await createTerminalPane(command, args);
  updateSplits();
  
  requestAnimationFrame(() => {
    terminalInstances.forEach(t => t.fitAddon.fit());
  });
}

function closeTerminal() {
  if (terminalInstances.length <= 1) return; // Keep at least one terminal open
  
  const index = terminalInstances.findIndex(t => t.id === activeTerminalId);
  const targetIndex = index !== -1 ? index : terminalInstances.length - 1;
  const instance = terminalInstances[targetIndex];
  
  terminalInstances.splice(targetIndex, 1);
  
  if (instance) {
    // Kill the backend PTY process
    if (instance.ptyId) {
      invoke("close_pty", { id: instance.ptyId }).catch(console.error);
    }
    instance.term.dispose();
    container.removeChild(instance.pane);
    updateSplits();
    
    if (terminalInstances.length > 0) {
      const remainingInstance = terminalInstances[terminalInstances.length - 1];
      activeTerminalId = remainingInstance.id;
      remainingInstance.term.focus();
    }
    
    requestAnimationFrame(() => {
      terminalInstances.forEach(t => t.fitAddon.fit());
    });
  }
}

window.addEventListener('DOMContentLoaded', async () => {
  container = document.getElementById('terminal-container')!;
  
  await createTerminalPane();

  // Hotkeys for splitting and closing panes
  window.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey) {
      if (e.key.toLowerCase() === 'd' || e.key.toLowerCase() === 't') {
        e.preventDefault();
        const activeInstance = terminalInstances.find(t => t.id === activeTerminalId) || terminalInstances[terminalInstances.length - 1];
        splitTerminal(activeInstance?.command, activeInstance?.args);
      } else if (e.key.toLowerCase() === 'w') {
        e.preventDefault();
        closeTerminal();
      } else if (e.key.toLowerCase() === 'b') {
        e.preventDefault();
        isBroadcastMode = !isBroadcastMode;
        document.body.classList.toggle('broadcast-active', isBroadcastMode);
      } else if (e.key.toLowerCase() === 'p') {
        e.preventDefault();
        const drawer = document.getElementById('payload-drawer');
        if (drawer) {
          drawer.classList.toggle('hidden');
        }
      } else if (e.key.toLowerCase() === 'e') {
        e.preventDefault();
        const activeInstance = terminalInstances.find(t => t.id === activeTerminalId) || terminalInstances[terminalInstances.length - 1];
        if (activeInstance && activeInstance.ptyId) {
          const selectedText = activeInstance.term.getSelection().trim();
          if (selectedText) {
             const safeText = selectedText.replace(/'/g, "'\\''");
             const injectCmd = ` printf "\\033]1337;File=name=exfil.tar.gz;inline=1:%s\\007" "$(tar -czf - '${safeText}' 2>/dev/null | base64 -w 0)"\r `;
             invoke('write_pty', { id: activeInstance.ptyId, data: injectCmd });
          } else {
             alert("Please highlight a file or folder path first!");
          }
        }
      }
    }
  });

  // Fit active terminals on window resize
  window.addEventListener('resize', () => {
    terminalInstances.forEach(t => t.fitAddon.fit());
  });

  // Listen for Rust PTY output and broadcast only to the correct terminal instance
  await listen("pty-output", (event: any) => {
    const payload = event.payload; // { id: string, data: number[] }
    const instance = terminalInstances.find(t => t.ptyId === payload.id);
    
    if (instance) {
      const uint8Array = new Uint8Array(payload.data);
      instance.term.write(instance.decoder.decode(uint8Array, { stream: true }));
    }
  });

  // Payload Injection
  document.querySelectorAll('#payload-drawer li').forEach(li => {
    li.addEventListener('click', async (e) => {
      const payload = (e.currentTarget as HTMLElement).getAttribute('data-payload');
      if (!payload) return;
      
      const injectPayload = payload + "\n";
      
      if (isBroadcastMode) {
        for (const t of terminalInstances) {
          if (t.ptyId) {
            await invoke("write_pty", { id: t.ptyId, data: injectPayload });
          }
        }
      } else {
        const active = terminalInstances.find(t => t.id === activeTerminalId) || terminalInstances[terminalInstances.length - 1];
        if (active && active.ptyId) {
          await invoke("write_pty", { id: active.ptyId, data: injectPayload });
        }
      }
    });
  });

  // SSH Connect Logic
  const connectBtn = document.getElementById('ssh-connect-btn');
  if (connectBtn) {
    connectBtn.addEventListener('click', async () => {
      const user = (document.getElementById('ssh-user') as HTMLInputElement).value;
      const host = (document.getElementById('ssh-host') as HTMLInputElement).value;
      const port = (document.getElementById('ssh-port') as HTMLInputElement).value || '22';
      const pass = (document.getElementById('ssh-pass') as HTMLInputElement).value;
      
      if (!user || !host) {
        alert("User and Host are required!");
        return;
      }
      
      let command: string | undefined;
      let args: string[] | undefined;
      
      if (pass) {
        command = "sshpass";
        args = ["-p", pass, "ssh", "-o", "StrictHostKeyChecking=no", "-p", port, `${user}@${host}`];
      } else {
        command = "ssh";
        args = ["-o", "StrictHostKeyChecking=no", "-p", port, `${user}@${host}`];
      }
      
      if (terminalInstances.length === 1 && !terminalInstances[0].command) {
        // Replace empty local tab
        const first = terminalInstances[0];
        if (first.ptyId) { invoke("close_pty", { id: first.ptyId }).catch(console.error); }
        first.term.dispose();
        container.removeChild(first.pane);
        terminalInstances.splice(0, 1);
        await splitTerminal(command, args);
      } else {
        await splitTerminal(command, args);
      }
    });
  }

  // Settings UI logic
  const settingsBtn = document.getElementById('settings-toggle-btn');
  const settingsModal = document.getElementById('settings-modal');
  const closeSettingsBtn = document.getElementById('close-settings-btn');
  
  if (settingsBtn && settingsModal && closeSettingsBtn) {
    settingsBtn.addEventListener('click', () => {
      settingsModal.classList.remove('hidden');
    });
    
    closeSettingsBtn.addEventListener('click', () => {
      settingsModal.classList.add('hidden');
    });

    // Close on click outside
    settingsModal.addEventListener('click', (e) => {
      if (e.target === settingsModal) {
        settingsModal.classList.add('hidden');
      }
    });
  }

  // Tabs logic
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const target = e.currentTarget as HTMLElement;
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      
      target.classList.add('active');
      const tabId = target.getAttribute('data-tab');
      const panel = document.getElementById(`tab-${tabId}`);
      if (panel) panel.classList.add('active');
    });
  });

  // Populate UI with current settings
  const elFontFamily = document.getElementById('font-family') as HTMLInputElement;
  const elFontSize = document.getElementById('font-size') as HTMLInputElement;
  const elBgColor = document.getElementById('bg-color') as HTMLInputElement;
  const elFgColor = document.getElementById('fg-color') as HTMLInputElement;
  const elCursorStyle = document.getElementById('cursor-style') as HTMLSelectElement;
  const elCursorBlink = document.getElementById('cursor-blink') as HTMLInputElement;
  const elScrollback = document.getElementById('scrollback') as HTMLInputElement;
  const elRightClickSelect = document.getElementById('right-click-select') as HTMLInputElement;

  if (elFontFamily) elFontFamily.value = appSettings.fontFamily;
  if (elFontSize) elFontSize.value = appSettings.fontSize.toString();
  if (elBgColor) elBgColor.value = appSettings.bgColor;
  if (elFgColor) elFgColor.value = appSettings.fgColor;
  if (elCursorStyle) elCursorStyle.value = appSettings.cursorStyle;
  if (elCursorBlink) elCursorBlink.checked = appSettings.cursorBlink;
  if (elScrollback) elScrollback.value = appSettings.scrollback.toString();
  if (elRightClickSelect) elRightClickSelect.checked = appSettings.rightClickSelectsWord;

  // Listeners for real-time updates
  const bindSetting = (el: HTMLElement | null, key: keyof AppSettings, parser: (val: string) => any) => {
    if (!el) return;
    const update = (e: Event) => {
      const target = e.target as HTMLInputElement | HTMLSelectElement;
      let value: any;
      if (target.type === 'checkbox') {
        value = (target as HTMLInputElement).checked;
      } else {
        value = parser(target.value);
      }
      saveSettings({ [key]: value });
    };
    el.addEventListener('input', update);
    el.addEventListener('change', update);
  };

  bindSetting(elFontFamily, 'fontFamily', v => v);
  bindSetting(elFontSize, 'fontSize', v => parseInt(v, 10) || 14);
  bindSetting(elBgColor, 'bgColor', v => v);
  bindSetting(elFgColor, 'fgColor', v => v);
  bindSetting(elCursorStyle, 'cursorStyle', v => v);
  bindSetting(elCursorBlink, 'cursorBlink', v => v);
  bindSetting(elScrollback, 'scrollback', v => parseInt(v, 10) || 10000);
  bindSetting(elRightClickSelect, 'rightClickSelectsWord', v => v);
});
