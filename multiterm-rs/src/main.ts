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

async function createTerminalPane(): Promise<TerminalInstance> {
  const id = `term-${terminalInstances.length + 1}`;
  
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
    fontFamily: '"Fira Code", monospace',
    fontSize: 14,
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
    if (instance.ptyId) {
      await invoke("write_pty", { id: instance.ptyId, data });
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
      terminalInstances[terminalInstances.length - 1].term.focus();
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
});
