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
 * cursor 使用 server_time（每次响应返回），首次同步从 1970 起。
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
    const cursor: string = data.lastSyncCursor || "1970-01-01T00:00:00Z";

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

    if (ackIds.length > 0) {
      try {
        await this.apiClient.ack(ackIds);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        errors.push(`ack 失败: ${msg}`);
        console.error("[shijian-sync] ack 失败:", err);
      }
    }

    data.lastSyncCursor = resp.server_time;
    try {
      await this.saveData(data);
    } catch (err) {
      console.error("[shijian-sync] 保存 cursor 失败:", err);
    }

    return { synced, errors };
  }

  private async processNote(note: NoteEntry): Promise<void> {
    if (note.kind === "article") {
      const rewritten = await downloadAndSaveImages(
        this.vault,
        note.content_md || "",
        note.images || [],
        this.settings.articlesDir,
        this.settings.attachmentsDir,
        this.apiClient,
      );
      const fullContent = buildArticleContent(note, rewritten);
      await writeNote(this.vault, note, this.settings.articlesDir, fullContent);
    } else if (note.kind === "attachment") {
      const bytes = await this.apiClient.downloadAttachment(note.id);
      await saveAttachmentFile(
        this.vault,
        note,
        this.settings.attachmentsDir,
        bytes,
      );
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
