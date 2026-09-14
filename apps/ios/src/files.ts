import { Directory, File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import type { ExportFiles } from './exporter';
export const files: ExportFiles = {
  open(name) {
    const dir = new Directory(Paths.cache, 'canopy-exports');
    dir.create({ idempotent: true, intermediates: true });
    const file = new File(dir, name); file.create({ overwrite: true });
    const handle = file.open();
    return { uri: file.uri, append: text => handle.writeBytes(new TextEncoder().encode(text)), close: () => handle.close() };
  },
  async share(uri, kind) {
    if (!(await Sharing.isAvailableAsync())) throw new Error('이 기기에서 파일 공유를 사용할 수 없습니다.');
    await Sharing.shareAsync(uri, { UTI: kind === 'gps' ? 'public.plain-text' : 'public.json',
      mimeType: kind === 'gps' ? 'text/plain' : 'application/json', dialogTitle: 'Canopy 데이터 공유' });
  },
};
