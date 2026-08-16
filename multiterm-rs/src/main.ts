import '@xterm/xterm/css/xterm.css';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import Split from 'split.js';
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

interface TerminalInstance {
  id: string; // The split.js pane ID
  ptyId: string | null; // The Rust PTY UUID
  pane: HTMLElement;
  term: Terminal;
  fitAddon: FitAddon;
  decoder: TextDecoder;
}

const terminalInstances: TerminalInstance[] = [];
let splitInstance: Split.Instance | null = null;
let container: HTMLElement;

let activeTerminalId: string | null = null;
let isBroadcastMode = false;
let terminalIdCounter = 0;

async function createTerminalPane(): Promise<TerminalInstance> {
  terminalIdCounter++;
  const id = `term-${terminalIdCounter}`;
  
  const pane = document.createElement('div');
  pane.className = 'terminal-pane';
  pane.id = id;
  container.appendChild(pane);

  const term = new Terminal({
    theme: {
      background: '#1e1e1e',
      foreground: '#f6f6f6',
      cursor: '#f6f6f6',
      selectionBackground: '#3d3d3d',
    },
    cursorBlink: true,
    fontFamily: '"Fira Code", Consolas, "Courier New", monospace',
    fontSize: 14,
    scrollback: 100000,
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

  const fitAddon = new FitAddon();
  term.loadAddon(fitAddon);
  term.open(pane);

  const instance: TerminalInstance = { id, ptyId: null, pane, term, fitAddon, decoder: new TextDecoder() };
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

  // Ask Rust to spawn a new backend shell for this specific terminal pane
  instance.ptyId = await invoke("spawn_pty", {
    rows: term.rows,
    cols: term.cols
  });

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

async function splitTerminal() {
  await createTerminalPane();
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
      if (e.key.toLowerCase() === 'd') {
        e.preventDefault();
        splitTerminal();
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
});
