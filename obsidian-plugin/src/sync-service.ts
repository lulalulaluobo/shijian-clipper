import type { Vault } from "obsidian";
import type { ApiClient } from "./api-client";
import type { NoteEntry, ShijianSettings } from "./types";
import { writeNote } from "./note-writer";
import { downloadAndSaveImages, saveAttachmentFile } from "./asset-writer";

export interface SyncResult {
  synced: number;
  errors: string[];
}

interface PluginData {
  lastSyncCursor?: string;
  [key: string]: unknown;
}

/**
 * 同步主逻辑。
 *
 * cursor 由服务端生成并视为 opaque 值。响应里的 last_id 用作下次请求的 cursor。
 * 单条失败不中断整批；已成功的 note 仍会 ack，避免反复重试。
 */
export class SyncService {
  constructor(
    private readonly apiClient: ApiClient,
    private readonly vault: Vault,
    private readonly settings: ShijianSettings,
    private readonly loadData: () => Promise<Record<string, unknown>>,
    private readonly saveData: (data: Record<string, unknown>) => Promise<void>,
  ) {}

  async doSync(): Promise<SyncResult> {
    const data = (await this.loadData()) as PluginData;
    const cursor: string = data.lastSyncCursor || "";

    const resp = await this.apiClient.pullChanges(cursor, 50);
    const notes = resp.notes || [];
    if (notes.length === 0) {
      return { synced: 0, errors: [] };
    }

    let synced = 0;
    const errors: string[] = [];
    const ackIds: string[] = [];

    for (const note of notes) {
      try {
        await this.processNote(note);
        ackIds.push(note.id);
        synced++;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        const label = note.title || note.filename || note.id;
        errors.push(`[${note.id}] ${label}: ${msg}`);
        console.error("[shijian-sync] 同步单条失败:", note.id, err);
      }
    }

    let acknowledged = ackIds.length === 0;
    if (ackIds.length > 0) {
      try {
        await this.apiClient.ack(ackIds);
        acknowledged = true;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        errors.push(`ack 失败: ${msg}`);
        console.error("[shijian-sync] ack 失败:", err);
      }
    }

    // 仅在整批处理并确认成功后推进 cursor，避免跳过失败或未确认的笔记。
    if (errors.length === 0 && acknowledged && resp.last_id) {
      data.lastSyncCursor = resp.last_id;
      try {
        await this.saveData(data);
      } catch (err) {
        console.error("[shijian-sync] 保存 cursor 失败:", err);
      }
    }

    return { synced, errors };
  }

  private async processNote(note: NoteEntry): Promise<void> {
    if (note.kind === "article") {
      let rewritten = note.content_md || "";
      if (this.settings.downloadImagesLocally) {
        rewritten = await downloadAndSaveImages(
          this.vault,
          note.content_md || "",
          note.images || [],
          this.settings.articlesDir,
          this.settings.attachmentsDir,
          this.apiClient,
        );
      }
      const fullContent = buildArticleContent(note, rewritten);
      await writeNote(this.vault, note, this.settings.articlesDir, fullContent);
    } else if (note.kind === "attachment") {
      try {
        const bytes = await this.apiClient.downloadAttachment(note.id);
        await saveAttachmentFile(
          this.vault,
          note,
          this.settings.attachmentsDir,
          bytes,
        );
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        if (msg.includes("status 404") || msg.includes("status 400")) {
          console.warn(`[shijian-sync] 附件 ${note.id} 在服务器上已不存在，跳过并保存占位符文件:`, err);
          const placeholderText = `[拾笺] 该附件在服务器上不存在或已清空。\n文件名: ${note.attachment_filename || note.filename || note.id}\n源地址: ${note.source_url || ""}`;
          const placeholderBytes = new TextEncoder().encode(placeholderText);
          await saveAttachmentFile(
            this.vault,
            note,
            this.settings.attachmentsDir,
            placeholderBytes.buffer,
          );
        } else {
          throw err;
        }
      }
    } else {
      throw new Error(`未知 kind: ${note.kind}`);
    }
  }
}

/**
 * 加 frontmatter 与标题。title/source 里有冒号或特殊字符时用 JSON 字符串。
 */
function buildArticleContent(note: NoteEntry, markdown: string): string {
  const lines: string[] = [
    "---",
    `title: ${JSON.stringify(note.title || "")}`,
    `source: ${JSON.stringify(note.source_url || "")}`,
    `clipped: ${JSON.stringify(note.created || "")}`,
    `shijian_id: ${JSON.stringify(note.id || "")}`,
    "---",
    "",
    `# ${note.title || ""}`,
    "",
    markdown,
  ];
  return lines.join("\n");
}
