// Record what dist/ was built from, so a test can tell a stale committed build from a
// fresh one without Node: the SHA-256 of each source (line endings normalized to LF)
// and the exact installed versions of the packages the kits are checked against.
import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'

const SOURCES = ['index.html', 'package.json', 'package-lock.json', 'src/main.tsx', 'vite.config.ts']
const PACKAGES = ['@koobiq/react-components', 'react-select', '@xyflow/react', 'react', 'react-dom']

const sources = {}
for (const file of SOURCES) {
  const text = readFileSync(file, 'utf8').replace(/\r\n/g, '\n')
  sources[file] = createHash('sha256').update(text, 'utf8').digest('hex')
}
const packages = {}
for (const name of PACKAGES) {
  packages[name] = JSON.parse(readFileSync(`node_modules/${name}/package.json`, 'utf8')).version
}
writeFileSync('dist/stand.json', JSON.stringify({ sources, packages }, null, 2) + '\n')
