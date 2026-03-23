import os
import pty
import fcntl
import termios
import struct
import asyncio
import subprocess
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
import json

app = FastAPI()

html_content = """
<!DOCTYPE html>
<html>
  <head>
    <title>Agent Setup Terminal</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css" />
    <script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js"></script>
    <style>
        body { margin: 0; padding: 0; background-color: #1e1e1e; height: 100vh; display: flex; flex-direction: column; }
        #terminal { flex: 1; margin: 10px; padding: 10px; background: #000; border-radius: 5px; }
        .header { color: #fff; padding: 15px 20px; font-family: sans-serif; background-color: #2c2c2c; box-shadow: 0 2px 4px rgba(0,0,0,0.5); display: flex; justify-content: space-between; align-items: center; }
        .status { color: #4caf50; font-size: 0.9em; }
    </style>
  </head>
  <body>
    <div class="header">
        <h2>🤖 Agent Setup Automation Terminal</h2>
        <span class="status">Connected to Claude automated environment</span>
    </div>
    <div id="terminal"></div>
    <script>
      var term = new Terminal({
        cursorBlink: true,
        fontFamily: '"Fira Code", "Cascadia Code", monospace',
        fontSize: 14,
        theme: {
            background: '#000000'
        }
      });
      var fitAddon = new FitAddon.FitAddon();
      term.loadAddon(fitAddon);
      term.open(document.getElementById('terminal'));
      fitAddon.fit();

      window.addEventListener('resize', () => { fitAddon.fit(); });

      var protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
      var ws = new WebSocket(protocol + window.location.host + '/ws');
      
      ws.onmessage = function(event) {
          term.write(event.data);
      };
      
      term.onData(function(data) {
          if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({type: 'data', data: data}));
          }
      });
      
      term.onResize(function(size) {
          if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({type: 'resize', cols: size.cols, rows: size.rows}));
          }
      });

      ws.onopen = function() {
         ws.send(JSON.stringify({type: 'resize', cols: term.cols, rows: term.rows}));
         term.writeln('\x1b[32m[System]\x1b[0m Connected to terminal backend.');
      };

      ws.onclose = function() {
         term.writeln('\r\n\x1b[31m[System]\x1b[0m Disconnected from terminal backend.');
      };
    </script>
  </body>
</html>
"""

@app.get("/")
async def get():
    return HTMLResponse(html_content)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Open a Pseudo-Terminal pair
    master_fd, slave_fd = pty.openpty()
    
    # Start a shell subprocess
    p = subprocess.Popen(
        ["/bin/bash"],
        preexec_fn=os.setsid,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        universal_newlines=True
    )
    os.close(slave_fd) # Close slave fd in parent
    
    def set_winsize(fd, row, col):
        winsize = struct.pack("HHHH", row, col, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    async def read_from_pty():
        loop = asyncio.get_running_loop()
        while True:
            try:
                data = await loop.run_in_executor(None, os.read, master_fd, 4096)
                if not data:
                    break
                await websocket.send_text(data.decode('utf-8', errors='replace'))
            except OSError:
                break
            except Exception as e:
                break

    read_task = asyncio.create_task(read_from_pty())
    
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "data":
                os.write(master_fd, msg["data"].encode('utf-8'))
            elif msg.get("type") == "resize":
                set_winsize(master_fd, msg["rows"], msg["cols"])
    except Exception as e:
        pass
    finally:
        read_task.cancel()
        try:
            os.close(master_fd)
        except:
            pass
        p.terminate()
