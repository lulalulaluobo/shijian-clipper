import { Notice, Plugin } from "obsidian";
import { ApiClient } from "./api-client";
import { ShijianSettingTab } from "./settings";
import { SyncService } from "./sync-service";
import { DEFAULT_SETTINGS, type ShijianSettings } from "./types";

const DEFAULT_SETTINGS_OBJ: ShijianSettings = { ...DEFAULT_SETTINGS };

export default class ShijianSyncPlugin extends Plugin {
  declare settings: ShijianSettings;
  private pollTimerId: number | null = null;
  private syncing = false;
  private apiClient: ApiClient | null = null;

  async onload(): Promise<void> {
    await this.loadSettings();

    this.addRibbonIcon("download", "拾笺同步", () => {
      void this.runSync(true);
    });

    this.addCommand({
      id: "shijian-sync-now",
      name: "立即同步",
      callback: () => {
        void this.runSync(true);
      },
    });

    this.addSettingTab(new ShijianSettingTab(this.app, this));

    this.restartPolling();
  }

  onunload(): void {
    if (this.pollTimerId !== null) {
      window.clearInterval(this.pollTimerId);
      this.pollTimerId = null;
    }
  }

  async loadSettings(): Promise<void> {
    this.settings = Object.assign(
      {},
      DEFAULT_SETTINGS_OBJ,
      await this.loadData(),
    );
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }

  /**
   * 重建轮询定时器。配置不完整或关闭自动同步时不会启动。
   * registerInterval 会让 Obsidian 在插件卸载时自动清理。
   */
  restartPolling(): void {
    this.apiClient = null;
    if (this.pollTimerId !== null) {
      window.clearInterval(this.pollTimerId);
      this.pollTimerId = null;
    }
    const s = this.settings;
    if (s.autoSync && s.baseUrl && s.apiToken) {
      const ms = Math.max(5, s.pollIntervalSeconds) * 1000;
      const id = window.setInterval(() => {
        this.runSync().catch((err) =>
          console.error("[shijian-sync] 自动同步失败:", err),
        );
      }, ms);
      this.pollTimerId = id;
      this.registerInterval(id);
    }
  }

  private buildSyncService(): SyncService {
    if (!this.apiClient) {
      this.apiClient = new ApiClient(
        this.settings.baseUrl,
        this.settings.apiToken,
      );
    }
    return new SyncService(
      this.apiClient,
      this.app.vault,
      this.settings,
      () => this.loadData(),
      (data) => this.saveData(data),
    );
  }

  async runSync(manual = false): Promise<void> {
    if (this.syncing) {
      if (manual) new Notice("同步已在进行中...");
      return;
    }
    if (!this.settings.baseUrl || !this.settings.apiToken) {
      new Notice("请先在设置中填写后端地址和 API Token");
      return;
    }

    if (manual) new Notice("正在同步中...");
    this.syncing = true;
    try {
      const service = this.buildSyncService();
      const result = await service.doSync();
      if (result.synced > 0) {
        new Notice(`拾笺已同步 ${result.synced} 篇`);
      } else if (manual && result.errors.length === 0) {
        new Notice("同步完成，已是最新状态");
      }
      if (result.errors.length > 0) {
        console.error("[shijian-sync] 同步部分失败:", result.errors);
        new Notice(`同步部分失败：${result.errors.length} 项，详见控制台`);
      }
    } catch (err: unknown) {
      console.error("[shijian-sync] 同步失败:", err);
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("401") || msg.includes("Token")) {
        new Notice("认证失败，请检查 API Token 是否正确");
      } else if (
        msg.includes("fetch") ||
        msg.includes("network") ||
        msg.includes("Failed") ||
        msg.includes("ENOTFOUND") ||
        msg.includes("ECONN")
      ) {
        new Notice("网络错误，无法连接后端");
      } else {
        new Notice(`同步失败: ${msg}`);
      }
    } finally {
      this.syncing = false;
    }
  }
}
