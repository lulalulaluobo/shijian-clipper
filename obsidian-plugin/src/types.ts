export interface ShijianSettings {
  /** 后端服务地址，如 "https://wechat.lucc.fun" */
  baseUrl: string;
  email: string;
  password: string;
  /** 文章保存目录，默认 "公众号收藏" */
  articlesDir: string;
  /** 图片与附件保存目录，默认 "公众号收藏/assets" */
  attachmentsDir: string;
  /** 轮询间隔（秒），默认 5，范围 5-300 */
  pollIntervalSeconds: number;
  /** 是否自动轮询，默认 true */
  autoSync: boolean;
}

export type NoteKind = "article" | "attachment";

export interface NoteEntry {
  id: string;
  kind: NoteKind;
  source_url: string;
  title: string;
  /** 服务端建议文件名，如 "标题.md" 或 "report.pdf" */
  filename: string;
  /** 仅 kind=article 有 */
  content_md: string;
  /** 仅 kind=article 有，微信图片 URL 列表 */
  images: string[];
  /** 仅 kind=attachment 有 */
  attachment_filename: string;
  attachment_mime: string;
  /** ISO8601 */
  created: string;
}

export interface SyncChangesResponse {
  notes: NoteEntry[];
  /** 本批次最大 note id，作为下次增量请求的 cursor */
  last_id: string;
  /** 服务端当前时间（ISO8601），仅用于调试 */
  server_time: string;
}

export interface AckResponse {
  acked: number;
}

export interface LoginResponse {
  token: string;
  user: { id: string; email: string };
}

export const DEFAULT_SETTINGS: ShijianSettings = {
  baseUrl: "",
  email: "",
  password: "",
  articlesDir: "公众号收藏",
  attachmentsDir: "公众号收藏/assets",
  pollIntervalSeconds: 5,
  autoSync: true,
};
