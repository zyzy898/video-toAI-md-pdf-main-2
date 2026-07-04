export type UploadSourceFile = Pick<File, "name" | "size" | "lastModified">;

export type DedupeBatchUploadResult<T extends UploadSourceFile> = {
  files: T[];
  duplicateCount: number;
  duplicateNames: string[];
};

export const buildUploadSourceKey = (file: UploadSourceFile) => {
  const name = String(file.name || "").trim().toLowerCase();
  const size = Number(file.size) || 0;
  const lastModified = Number(file.lastModified) || 0;
  return JSON.stringify([name, size, lastModified]);
};

export const dedupeBatchUploadFiles = <T extends UploadSourceFile>(
  files: T[],
  existingSourceKeys: Iterable<string> = [],
): DedupeBatchUploadResult<T> => {
  const seen = new Set(existingSourceKeys);
  const deduped: T[] = [];
  const duplicateNames: string[] = [];

  for (const file of files) {
    const sourceKey = buildUploadSourceKey(file);
    if (seen.has(sourceKey)) {
      duplicateNames.push(String(file.name || "未命名视频"));
      continue;
    }
    seen.add(sourceKey);
    deduped.push(file);
  }

  return {
    files: deduped,
    duplicateCount: duplicateNames.length,
    duplicateNames: Array.from(new Set(duplicateNames)),
  };
};
