import { type App, PluginSettingTab, Setting } from "obsidian";
import type ShijianSyncPlugin from "./main";
import { DEFAULT_SETTINGS } from "./types";

export class ShijianSettingTab extends PluginSettingTab {
  plugin: ShijianSyncPlugin;

  constructor(app: App, plugin: ShijianSyncPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl("h2", { text: "拾笺同步设置" });

    new Setting(containerEl)
      .setName("后端服务地址")
      .setDesc("拾笺后端的 HTTPS 地址，如 https://wechat.example.com")
      .addText((text) =>
        text
          .setPlaceholder("https://...")
          .setValue(this.plugin.settings.baseUrl)
          .onChange(async (v) => {
            this.plugin.settings.baseUrl = v.trim();
            await this.plugin.saveSettings();
            this.plugin.restartPolling();
          }),
      );

    new Setting(containerEl)
      .setName("邮箱")
      .setDesc("注册账号的邮箱")
      .addText((text) =>
        text
          .setPlaceholder("you@example.com")
          .setValue(this.plugin.settings.email)
          .onChange(async (v) => {
            this.plugin.settings.email = v.trim();
            await this.plugin.saveSettings();
            this.plugin.restartPolling();
          }),
      );

    new Setting(containerEl)
      .setName("密码")
      .setDesc("账号密码（明文保存在本地 data.json，请确保设备安全）")
      .addText((text) => {
        text
          .setPlaceholder("••••••••")
          .setValue(this.plugin.settings.password)
          .onChange(async (v) => {
            this.plugin.settings.password = v;
            await this.plugin.saveSettings();
          });
        text.inputEl.type = "password";
      });

    new Setting(containerEl)
      .setName("文章目录")
      .setDesc("公众号文章保存的 Vault 目录，默认「公众号收藏」")
      .addText((text) =>
        text
          .setValue(this.plugin.settings.articlesDir)
          .onChange(async (v) => {
            this.plugin.settings.articlesDir =
              v.trim() || DEFAULT_SETTINGS.articlesDir;
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("附件目录")
      .setDesc("图片与附件保存的 Vault 目录，默认「公众号收藏/assets」")
      .addText((text) =>
        text
          .setValue(this.plugin.settings.attachmentsDir)
          .onChange(async (v) => {
            this.plugin.settings.attachmentsDir =
              v.trim() || DEFAULT_SETTINGS.attachmentsDir;
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("轮询间隔（秒）")
      .setDesc("多久轮询一次后端，范围 5-300，默认 5 秒")
      .addText((text) =>
        text
          .setValue(String(this.plugin.settings.pollIntervalSeconds))
          .onChange(async (v) => {
            const parsed = parseInt(v, 10);
            const n = Math.max(
              5,
              Math.min(300, Number.isFinite(parsed) ? parsed : 5),
            );
            this.plugin.settings.pollIntervalSeconds = n;
            await this.plugin.saveSettings();
            this.plugin.restartPolling();
          }),
      );

    new Setting(containerEl)
      .setName("自动同步")
      .setDesc("开启后按轮询间隔自动拉取；关闭后只响应手动「立即同步」命令")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.autoSync)
          .onChange(async (v) => {
            this.plugin.settings.autoSync = v;
            await this.plugin.saveSettings();
            this.plugin.restartPolling();
          }),
      );
  }
}
