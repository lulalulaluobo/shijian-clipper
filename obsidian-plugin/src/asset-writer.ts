import type { Vault } from "obsidian";
import { normalizePath } from "obsidian";
import type { ApiClient } from "./api-client";
import type { NoteEntry } from "./types";
import { ensureDir, resolveConflictPath } from "./note-writer";

/**
 * 把 URL 做 SHA-256，取前 6 字节 hex（共 12 字符）作为文件名前缀。
 * 不依赖第三方包，用 WebCrypto。
 */
async function hashUrl(url: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(url);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray
    .slice(0, 6)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * 从 URL 或 mime 推断扩展名（不带点）。
 */
function inferExtension(urlOrMime: string): string {
  const lower = urlOrMime.toLowerCase();
  if (lower.includes("png") || lower.includes("image/png")) return "png";
  if (lower.includes("jpg") || lower.includes("jpeg") || lower.includes("image/jpeg"))
    return "jpg";
  if (lower.includes("gif") || lower.includes("image/gif")) return "gif";
  if (lower.includes("webp") || lower.includes("image/webp")) return "webp";
  if (lower.includes("svg") || lower.includes("image/svg")) return "svg";
  if (lower.includes("bmp") || lower.includes("image/bmp")) return "bmp";
  if (lower.includes(".pdf") || lower.includes("application/pdf")) return "pdf";
  if (lower.includes(".xlsx") || lower.includes("spreadsheet"))
    return "xlsx";
  if (lower.includes(".xls")) return "xls";
  if (lower.includes(".docx")) return "docx";
  if (lower.includes(".doc")) return "doc";
  if (lower.includes(".pptx")) return "pptx";
  if (lower.includes(".ppt")) return "ppt";
  if (lower.includes(".zip")) return "zip";
  if (lower.includes(".mp4")) return "mp4";
  if (lower.includes("text/plain")) return "txt";
  if (lower.includes("text/html")) return "html";
  return "bin";
}

/**
 * 计算 articlesDir 到 attachmentsDir 的相对路径，用于在 Markdown 中嵌入图片。
 * 例如 articlesDir=公众号收藏，attachmentsDir=公众号收藏/assets → "assets"
 * 若两者无包含关系，则退化为 attachmentsDir 本身（Obsidian 也支持）。
 */
function relativeAttachmentsPath(
  articlesDir: string,
  attachmentsDir: string,
): string {
  const a = normalizePath(articlesDir);
  const b = normalizePath(attachmentsDir);
  if (b === a) return ".";
  if (b.startsWith(a + "/")) {
    return b.slice(a.length + 1);
  }
  return b;
}

/**
 * 下载图片字节并写入附件目录，同时把 Markdown 中的远程 URL 替换为相对路径。
 *
 * 单张失败不抛出，保留原 URL。
 */
export async function downloadAndSaveImages(
  vault: Vault,
  content: string,
  imageUrls: string[],
  articlesDir: string,
  attachmentsDir: string,
  apiClient: ApiClient,
): Promise<string> {
  if (imageUrls.length === 0) return content;
  await ensureDir(vault, attachmentsDir);
  let updatedContent = content;
  const relBase = relativeAttachmentsPath(articlesDir, attachmentsDir);

  for (const imageUrl of imageUrls) {
    if (!imageUrl) continue;
    try {
      const { arrayBuffer, contentType } = await apiClient.downloadImageBytes(imageUrl);
      const hash = await hashUrl(imageUrl);
      let ext = inferExtension(contentType);
      if (ext === "bin") {
        ext = inferExtension(imageUrl);
      }
      const filename = `${hash}.${ext}`;
      const fullPath = normalizePath(`${attachmentsDir}/${filename}`);

      if (!(await vault.adapter.exists(fullPath))) {
        await vault.createBinary(fullPath, arrayBuffer);
      }

      // Obsidian 对 ![](path) 中带空格或中文的路径需要用相对路径
      const embedPath = `${relBase}/${filename}`;
      updatedContent = updatedContent.split(imageUrl).join(embedPath);
    } catch (err) {
      console.warn("[shijian-sync] 图片下载失败，保留原 URL:", imageUrl, err);
    }
  }

  return updatedContent;
}

/**
 * 把附件字节写入附件目录，文件名优先用服务端提供的 attachment_filename。
 */
export async function saveAttachmentFile(
  vault: Vault,
  note: NoteEntry,
  attachmentsDir: string,
  bytes: ArrayBuffer,
): Promise<string> {
  await ensureDir(vault, attachmentsDir);
  const filename =
    note.attachment_filename || note.filename || `attachment-${note.id}`;
  const fullPath = await resolveConflictPath(
    vault,
    normalizePath(`${attachmentsDir}/${filename}`),
  );
  await vault.createBinary(fullPath, bytes);
  return fullPath;
}
