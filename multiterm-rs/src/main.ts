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
}

const terminalInstances: TerminalInstance[] = [];
let splitInstance: Split.Instance | null = null;
let container: HTMLElement;

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

  const instance: TerminalInstance = { id, ptyId: null, pane, term, fitAddon };
  terminalInstances.push(instance);

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
  if (splitInstance) {
    splitInstance.destroy();
    splitInstance = null;
  }

  const paneIds = terminalInstances.map(t => `#${t.id}`);
  
  if (paneIds.length > 1) {
    const size = 100 / paneIds.length;
    const sizes = Array(paneIds.length).fill(size);
    
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
  
  const instance = terminalInstances.pop();
  if (instance) {
    instance.term.dispose();
    container.removeChild(instance.pane);
    updateSplits();
    
    // Ideally we would also call a Rust command to close the PTY, 
    // but the slave shell should naturally exit when the master is dropped if we manage lifecycle.
    
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
      const decoder = new TextDecoder();
      instance.term.write(decoder.decode(uint8Array));
    }
  });
});
