import '@xterm/xterm/css/xterm.css';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import Split from 'split.js';
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

interface TerminalInstance {
  id: string;
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

  // Send input to Rust backend
  term.onData(async (data: string) => {
    await invoke("write_pty", { data });
  });

  const instance = { id, pane, term, fitAddon };
  terminalInstances.push(instance);

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
    
    requestAnimationFrame(() => {
      terminalInstances.forEach(t => t.fitAddon.fit());
    });
  }
}

window.addEventListener('DOMContentLoaded', async () => {
  container = document.getElementById('terminal-container')!;
  
  const firstTerm = await createTerminalPane();
  requestAnimationFrame(() => {
    firstTerm.fitAddon.fit();
  });

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

  // Spawn Rust PTY
  await invoke("spawn_pty");

  // Listen for Rust PTY output and broadcast to the active terminal
  await listen("pty-output", (event) => {
    const uint8Array = new Uint8Array(event.payload as number[]);
    const decoder = new TextDecoder();
    const data = decoder.decode(uint8Array);
    
    // Broadcast data to all terminal panes (for MVP demo purposes)
    terminalInstances.forEach(t => t.term.write(data));
  });
});
