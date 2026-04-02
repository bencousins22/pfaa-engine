/**
 * Lightweight Node.js client for the JMEM daemon socket.
 * Used by banner.cjs, statusline.cjs for fast JMEM stats.
 *
 * Usage:
 *   const { jmemRequest } = require('./jmem-client.cjs');
 *   const result = jmemRequest('status', {});
 */

const fs = require('fs');

const SOCK_PATH = process.env.JMEM_SOCK || '/tmp/pfaa-jmem.sock';

/**
 * Synchronous JMEM request using Python subprocess.
 * Adds ~50ms overhead but avoids Node async complexity in hook scripts.
 */
function jmemRequest(method, params) {
  if (!fs.existsSync(SOCK_PATH)) return null;
  try {
    const { execFileSync } = require('child_process');
    const script = `
import json, socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(3)
s.connect(${JSON.stringify(SOCK_PATH)})
req = json.dumps({"method": ${JSON.stringify(method)}, "params": ${JSON.stringify(params || {})}}) + "\\n"
s.sendall(req.encode())
d = b""
while True:
    c = s.recv(65536)
    if not c: break
    d += c
    if b"\\n" in d: break
s.close()
r = json.loads(d.decode().strip())
print(json.dumps(r.get("result")))
`;
    const out = execFileSync('python3', ['-c', script], {
      timeout: 4000, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'],
    }).trim();
    return JSON.parse(out);
  } catch {
    return null;
  }
}

function isDaemonRunning() {
  const result = jmemRequest('ping', {});
  return result !== null && result.pong === true;
}

module.exports = { jmemRequest, isDaemonRunning, SOCK_PATH };
