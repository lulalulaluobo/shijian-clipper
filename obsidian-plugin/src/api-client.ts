import { requestUrl } from "obsidian";
import type { AckResponse, LoginResponse, SyncChangesResponse } from "./types";

/**
 * 后端 API 封装。
 *
 * 全部走 Obsidian 的 requestUrl（绕过浏览器 CORS 与证书限制），
 * 不使用 fetch。token 仅缓存在内存，重启插件后失效。
 */
export class ApiClient {
  private token: string | null = null;
  private readonly baseUrl: string;

  constructor(
    baseUrl: string,
    private readonly email: string,
    private readonly password: string,
  ) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  static async login(
    baseUrl: string,
    email: string,
    password: string,
  ): Promise<LoginResponse> {
    const root = baseUrl.replace(/\/$/, "");
    const resp = await requestUrl({
      url: `${root}/v1/auth/login`,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    return resp.json as LoginResponse;
  }

  async ensureToken(): Promise<void> {
    if (this.token) return;
    const resp = await ApiClient.login(this.baseUrl, this.email, this.password);
    this.token = resp.token;
  }

  async pullChanges(
    sinceIso: string,
    limit: number = 50,
  ): Promise<SyncChangesResponse> {
    await this.ensureToken();
    const url =
      `${this.baseUrl}/v1/sync/changes?since=${encodeURIComponent(sinceIso)}` +
      `&limit=${limit}`;
    let resp = await requestUrl({
      url,
      method: "GET",
      headers: this.authHeaders(),
    });
    if (resp.status === 401) {
      // token 失效，重新登录后重试一次
      this.token = null;
      await this.ensureToken();
      resp = await requestUrl({
        url,
        method: "GET",
        headers: this.authHeaders(),
      });
    }
    return resp.json as SyncChangesResponse;
  }

  async ack(noteIds: string[]): Promise<AckResponse> {
    if (noteIds.length === 0) return { acked: 0 };
    await this.ensureToken();
    const resp = await requestUrl({
      url: `${this.baseUrl}/v1/sync/ack`,
      method: "POST",
      headers: { ...this.authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ note_ids: noteIds }),
    });
    return resp.json as AckResponse;
  }

  async downloadAttachment(noteId: string): Promise<ArrayBuffer> {
    await this.ensureToken();
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
  async downloadImageBytes(url: string): Promise<ArrayBuffer> {
    const resp = await requestUrl({ url, method: "GET" });
    return resp.arrayBuffer;
  }

  private authHeaders(): Record<string, string> {
    return this.token ? { Authorization: `Bearer ${this.token}` } : {};
  }
}
