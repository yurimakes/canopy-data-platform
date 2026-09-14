import type { Storage } from './storage';
export interface ExportFiles {
  open(name: string): { append(text: string): void; close(): void; uri: string };
  share(uri: string, kind: 'gps' | 'metadata'): Promise<void>;
}
export async function exportTrip(db: Storage, files: ExportFiles, id: string, kind: 'gps' | 'metadata', now: string) {
  const summary = await db.summary(id);
  if (summary.status === 'recording') throw new Error('측정 종료와 저장 완료 후 내보내세요.');
  const gps = files.open(`${id}.gps.jsonl`);
  let count = 0;
  try { for await (const row of db.events(id)) { gps.append(row + '\n'); count++; } }
  finally { gps.close(); }
  if (count !== summary.gps_count) throw new Error('내보내기 행 수와 DB 건수가 다릅니다.');
  const { latest: _latest, ...metadata } = summary;
  const diagnostics = await db.diagnostics(id);
  const meta = files.open(`${id}.metadata.json`);
  try { meta.append(JSON.stringify({ ...metadata, diagnostics, diagnostic_count: diagnostics.length, exported_at: now }, null, 2)); }
  finally { meta.close(); }
  await files.share(kind === 'gps' ? gps.uri : meta.uri, kind);
  // Sharing provides no reliable delivery/cancel result. Never delete SQLite source.
}
