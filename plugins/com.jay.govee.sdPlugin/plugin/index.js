// StreamDock starts this with Node and the usual -port/-pluginUUID/-registerEvent/-info args.
// It just launches the Python backend (plugin.py) with the same args and mirrors its lifetime.
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

let python = 'pythonw';
try {
  const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, 'config.json'), 'utf8'));
  if (cfg.python) python = cfg.python;
} catch (e) { /* no config: use pythonw from PATH */ }

const child = spawn(python, [path.join(__dirname, 'plugin.py'), ...process.argv.slice(2)], {
  cwd: __dirname, stdio: 'ignore', windowsHide: true,
});
child.on('error', (e) => {
  fs.appendFileSync(path.join(__dirname, 'log.txt'), `${new Date().toISOString()} node: could not start ${python}: ${e}\n`);
  process.exit(1);
});
child.on('exit', (code) => process.exit(code || 0));
const stop = () => { try { child.kill(); } catch (e) {} process.exit(0); };
process.on('SIGTERM', stop);
process.on('SIGINT', stop);
process.on('disconnect', stop);
