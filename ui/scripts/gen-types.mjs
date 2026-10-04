// Generate src/shared/messages.ts from schemas/messages.schema.json.
// `--check` fails when the committed file is stale, so the shell and the
// core's Python models cannot drift.
import { readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { compile } from 'json-schema-to-typescript'

const schemaPath = fileURLToPath(new URL('../../schemas/messages.schema.json', import.meta.url))
const outPath = fileURLToPath(new URL('../src/shared/messages.ts', import.meta.url))

const schema = JSON.parse(await readFile(schemaPath, 'utf8'))
// Pydantic titles every field; json-schema-to-typescript would turn each
// title into its own alias (Type1, V2, ...). Keep titles on definitions only.
for (const definition of Object.values(schema.$defs)) {
  for (const property of Object.values(definition.properties ?? {})) delete property.title
}
const ts = await compile(schema, 'Messages', {
  bannerComment:
    '// Generated from schemas/messages.schema.json by `npm run gen:types`. Do not edit.\n' +
    '// The source of truth is core/src/tft_core/messages.py (`uv run tft-schemas`).',
  unreachableDefinitions: true,
  additionalProperties: false,
  format: true,
  style: { semi: false, singleQuote: true, printWidth: 100 },
})

if (process.argv.includes('--check')) {
  const current = await readFile(outPath, 'utf8').catch(() => '')
  if (current !== ts) {
    console.error(`${outPath} is stale; run \`npm run gen:types\``)
    process.exit(1)
  }
} else {
  await writeFile(outPath, ts)
  console.log(`wrote ${outPath}`)
}
