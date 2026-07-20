import { requestUrl } from "obsidian";
import type { AckResponse, SyncChangesResponse } from "./types";

/**
 * 后端 API 封装。
 *
 * 全部走 Obsidian 的 requestUrl（绕过浏览器 CORS 与证书限制），
 * 不使用 fetch。使用 API Token 直接鉴权，无需登录流程。
 */
export class ApiClient {
  private readonly baseUrl: string;
  private readonly apiToken: string;

  constructor(baseUrl: string, apiToken: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.apiToken = apiToken;
  }

  async pullChanges(
    sinceIso: string,
    limit: number = 50,
  ): Promise<SyncChangesResponse> {
    const url =
      `${this.baseUrl}/v1/sync/changes?since=${encodeURIComponent(sinceIso)}` +
      `&limit=${limit}`;
    const resp = await requestUrl({
      url,
      method: "GET",
      headers: this.authHeaders(),
    });
    return resp.json as SyncChangesResponse;
  }

  async ack(noteIds: string[]): Promise<AckResponse> {
    if (noteIds.length === 0) return { acked: 0 };
    const resp = await requestUrl({
      url: `${this.baseUrl}/v1/sync/ack`,
      method: "POST",
      headers: { ...this.authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ note_ids: noteIds }),
    });
    return resp.json as AckResponse;
  }

  async downloadAttachment(noteId: string): Promise<ArrayBuffer> {
    const resp = await requestUrl({
      url: `${this.baseUrl}/v1/sync/notes/${encodeURIComponent(noteId)}/attachment`,
      method: "GET",
      headers: this.authHeaders(),
    });
    return resp.arrayBuffer;
  }

  /**
   * 直接下载微信图片字节。微信图床不需要后端鉴权，
   * 但需要 Obsidian 的 requestUrl 来绕过浏览器 CORS。
   */
  async downloadImageBytes(url: string): Promise<{ arrayBuffer: ArrayBuffer; contentType: string }> {
    const resp = await requestUrl({ url, method: "GET" });
    return {
      arrayBuffer: resp.arrayBuffer,
      contentType: resp.headers["content-type"] || "",
    };
  }

  private authHeaders(): Record<string, string> {
    return { Authorization: `Bearer ${this.apiToken}` };
  }
}
