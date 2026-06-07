/**
 * start.js — Bật dashboard + tự động chạy pipeline lấy dữ liệu mới.
 *
 * Khi gõ `npm start`:
 *   1. Spawn python pipeline/refresh.py để lấy giá mới + cập nhật KPI.
 *   2. Spawn Vite dev server (mở port 5173 mặc định).
 *
 * Pipeline chạy nền, không chặn dev server. Cả 2 đều log ra cùng terminal.
 * Ctrl+C dừng cả hai.
 */
import { spawn } from 'node:child_process'

const isWin = process.platform === 'win32'
const PY = process.env.PYTHON || (isWin ? 'python' : 'python3')

function colorize(prefix, color) {
  // ANSI colors: 36 cyan, 33 yellow
  return `\x1b[${color}m[${prefix}]\x1b[0m`
}

function pipe(child, label, color) {
  const pre = colorize(label, color)
  child.stdout?.on('data', d => process.stdout.write(`${pre} ${d}`))
  child.stderr?.on('data', d => process.stderr.write(`${pre} ${d}`))
  child.on('exit', code => {
    console.log(`${pre} exited with code ${code}`)
  })
}

console.log('━'.repeat(64))
console.log(' VN-30 Dashboard — Realtime Mode')
console.log('━'.repeat(64))
console.log('  📦 Pipeline: tự cập nhật giá + KPI từ vnstock (~ vài phút)')
console.log('  🌐 Vite dev: http://localhost:5173')
console.log('━'.repeat(64))

// 1. Pipeline (chạy nền)
const pipeline = spawn(PY, ['pipeline/refresh.py'], {
  shell: true,
  cwd: process.cwd(),
})
pipe(pipeline, 'pipeline', '36')

// 2. Vite dev server (foreground)
const vite = spawn('npx', ['vite'], {
  shell: true,
  cwd: process.cwd(),
  stdio: 'inherit',
})

process.on('SIGINT', () => {
  console.log('\n[start.js] Stopping...')
  try { pipeline.kill() } catch {}
  try { vite.kill() } catch {}
  process.exit(0)
})
