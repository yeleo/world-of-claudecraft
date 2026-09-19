import * as esbuild from 'esbuild';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { collectVoiceLines } from './voice_line_catalog.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

export async function loadContent() {
  const build = await esbuild.build({
    stdin: {
      contents:
        "export { NPCS, QUESTS, ESCORTS } from './src/sim/data.ts'; " +
        "export { IGNIVAR_DIALOGUE_LINES } from './src/sim/encounters/ignivar_dialogue.ts'; " +
        "export { VARKHUL_DIALOGUE_LINES } from './src/sim/encounters/varkhul_dialogue.ts';",
      resolveDir: root,
      sourcefile: 'voice-lines-entry.ts',
      loader: 'ts',
    },
    bundle: true,
    platform: 'node',
    format: 'esm',
    write: false,
    logLevel: 'silent',
  });
  const dataUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`;
  return import(dataUrl);
}

export async function getAllLines() {
  const content = await loadContent();
  return collectVoiceLines({
    NPCS: content.NPCS,
    QUESTS: content.QUESTS,
    ESCORTS: content.ESCORTS,
    IGNIVAR_DIALOGUE_LINES: content.IGNIVAR_DIALOGUE_LINES,
    VARKHUL_DIALOGUE_LINES: content.VARKHUL_DIALOGUE_LINES,
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const lines = await getAllLines();
  process.stdout.write(JSON.stringify(lines, null, 2));
}
