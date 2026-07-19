import type { Vault } from "obsidian";
import { normalizePath } from "obsidian";
import type { NoteEntry } from "./types";

/**
 * 递归创建目录（如果不存在）。空字符串或根路径不做任何操作。
 */
export async function ensureDir(vault: Vault, dir: string): Promise<void> {
  const normalized = normalizePath(dir);
  if (normalized === "" || normalized === "/" || normalized === ".") return;
  if (!(await vault.adapter.exists(normalized))) {
    await vault.createFolder(normalized);
  }
}

/**
 * 文件名冲突时追加 -1、-2 后缀；100 次仍冲突则用时间戳兜底。
 */
export async function resolveConflictPath(
  vault: Vault,
  fullPath: string,
): Promise<string> {
  if (!(await vault.adapter.exists(fullPath))) return fullPath;
  const dotIdx = fullPath.lastIndexOf(".");
  const stem = dotIdx > 0 ? fullPath.slice(0, dotIdx) : fullPath;
  const ext = dotIdx > 0 ? fullPath.slice(dotIdx) : "";
  for (let i = 1; i < 100; i++) {
    const candidate = `${stem}-${i}${ext}`;
    if (!(await vault.adapter.exists(candidate))) return candidate;
  }
  return `${stem}-${Date.now()}${ext}`;
}

/**
 * 把一篇文章以 Markdown 形式写入 Vault。
 *
 * - 已存在则跳过（返回原路径），不做差异更新。
 * - 文件名冲突时追加后缀。
 */
export async function writeNote(
  vault: Vault,
  note: NoteEntry,
  articlesDir: string,
  content: string,
): Promise<{ path: string; created: boolean }> {
  await ensureDir(vault, articlesDir);
  const filename = note.filename || `${note.title || note.id}.md`;
  const fullPath = await resolveConflictPath(
    vault,
    normalizePath(`${articlesDir}/${filename}`),
  );
  const created = !(await vault.adapter.exists(fullPath));
  if (!created) {
    // resolveConflictPath 保证返回的是不存在的路径，理论上不会走到这里
    return { path: fullPath, created: false };
  }
  await vault.create(fullPath, content);
  return { path: fullPath, created: true };
}
