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

  async onload(): Promise<void> {
    await this.loadSettings();

    this.addRibbonIcon("download", "拾笺同步", () => {
      void this.runSync();
    });

    this.addCommand({
      id: "shijian-sync-now",
      name: "立即同步",
      callback: () => {
        void this.runSync();
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
    if (this.pollTimerId !== null) {
      window.clearInterval(this.pollTimerId);
      this.pollTimerId = null;
    }
    const s = this.settings;
    if (s.autoSync && s.baseUrl && s.email && s.password) {
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
    const apiClient = new ApiClient(
      this.settings.baseUrl,
      this.settings.email,
      this.settings.password,
    );
    return new SyncService(
      apiClient,
      this.app.vault,
      this.settings,
      () => this.loadData(),
      (data) => this.saveData(data),
    );
  }

  async runSync(): Promise<void> {
    if (this.syncing) return;
    if (
      !this.settings.baseUrl ||
      !this.settings.email ||
      !this.settings.password
    ) {
      new Notice("请先在设置中填写后端地址、邮箱和密码");
      return;
    }

    this.syncing = true;
    try {
      const service = this.buildSyncService();
      const result = await service.doSync();
      if (result.synced > 0) {
        new Notice(`拾笺已同步 ${result.synced} 篇`);
      }
      if (result.errors.length > 0) {
        console.error("[shijian-sync] 同步部分失败:", result.errors);
        new Notice(`同步部分失败：${result.errors.length} 项，详见控制台`);
      }
    } catch (err: unknown) {
      console.error("[shijian-sync] 同步失败:", err);
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("401") || msg.includes("登录")) {
        new Notice("登录失败，请检查邮箱密码");
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
