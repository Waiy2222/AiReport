const app = getApp();
const api = require("../../utils/api.js");

Page({
  data: {
    openid: "",
    openidMasked: "",
    morningEnabled: false,
    eveningEnabled: false,
    allTags: [],
    selectedTags: [],
    loadingTags: true,
    // Phase 3: 信源健康度
    sourceHealth: [],
    pendingRecommendations: 0,
  },

  onLoad() {
    const openid = app.globalData.openid || "mock_openid_user_001";
    const storedTags = wx.getStorageSync("userTags") || [];
    app.globalData.userTags = storedTags;
    this.setData({
      openid,
      openidMasked: openid.substring(0, 8) + "***" + openid.slice(-4),
    });
    this.loadTagsAndPreferences();
    this.loadSourcesHealth();
  },

  onShow() {
    if (this.data.openid) {
      this.loadTagsAndPreferences();
      this.loadSourcesHealth();
    }
  },

  async loadTagsAndPreferences() {
    try {
      const tagsResp = await api.getTags();
      const catalogTags = tagsResp.tags || [];

      let savedTags = [];
      try {
        const prefs = await api.getPreferences(this.data.openid);
        savedTags = prefs.tags || [];
      } catch (e) {
        console.warn("获取偏好失败", e);
      }

      // 从全局读取首页已缓存的活跃标签（首页加载简报时自动收集）
      const activeTagSet = app.globalData.activeTagSet || {};
      const hasActiveData = Object.keys(activeTagSet).length > 0;

      // 剔除已失效的标签（之前选了但现在无新闻）
      const validSelected = hasActiveData
        ? savedTags.filter(t => activeTagSet[t])
        : savedTags;

      const allTags = catalogTags.map((t) => ({
        ...t,
        selected: validSelected.indexOf(t.tag) >= 0,
        disabled: hasActiveData && !activeTagSet[t.tag],
        hasNews: !hasActiveData || !!activeTagSet[t.tag],
      }));

      this.setData({ allTags, selectedTags: validSelected, loadingTags: false });
    } catch (e) {
      console.error("加载标签失败", e);
      this.setData({ loadingTags: false });
    }
  },

  onTagTap(e) {
    const tag = e.currentTarget.dataset.tag;
    const { allTags, selectedTags } = this.data;
    const activeTagSet = app.globalData.activeTagSet || {};

    // 简报里没有相关新闻的标签不可选
    if (Object.keys(activeTagSet).length > 0 && !activeTagSet[tag]) {
      wx.showToast({ title: "暂无相关新闻", icon: "none", duration: 1000 });
      return;
    }

    const idx = selectedTags.indexOf(tag);
    const newSelected = idx >= 0
      ? selectedTags.filter((t) => t !== tag)
      : [...selectedTags, tag];

    const newAllTags = allTags.map((t) => ({
      ...t,
      selected: newSelected.indexOf(t.tag) >= 0,
    }));

    this.setData({ allTags: newAllTags, selectedTags: newSelected });
  },

  async onSavePreferences() {
    const { openid, selectedTags } = this.data;
    try {
      await api.setPreferences(openid, selectedTags);
      app.globalData.userTags = selectedTags;
      wx.setStorageSync("userTags", selectedTags);
      wx.showToast({ title: "已保存，内容已过滤", icon: "success" });
    } catch (e) {
      wx.showToast({ title: "保存失败", icon: "none" });
    }
  },

  onToggleMorning(e) {
    this.setData({ morningEnabled: e.detail.value });
    this.saveSubscription();
  },

  onToggleEvening(e) {
    this.setData({ eveningEnabled: e.detail.value });
    this.saveSubscription();
  },

  async saveSubscription() {
    const { openid, morningEnabled, eveningEnabled } = this.data;
    try {
      if (morningEnabled || eveningEnabled) {
        await api.subscribe(openid, morningEnabled, eveningEnabled);
      } else {
        await api.unsubscribe(openid);
      }
      wx.showToast({ title: "已保存", icon: "success" });
    } catch (err) {
      wx.showToast({ title: "保存失败", icon: "none" });
    }
  },

  // Phase 3: 加载信源健康度
  async loadSourcesHealth() {
    try {
      const resp = await api.getSourcesHealth();
      const items = resp.items || [];
      const pending = items.reduce(
        (sum, item) => sum + (item.recommendations_pending || 0),
        0,
      );
      this.setData({ sourceHealth: items, pendingRecommendations: pending });
    } catch (e) {
      console.warn("加载信源健康度失败", e);
      // 静默失败，不影响主功能
    }
  },

  onAbout() {
    wx.showModal({
      title: "AI 资讯简报",
      content: "每天 8:00 / 20:00 自动推送 AI 和智能体领域精选开源资讯。由 AI 评分、去重、摘要后生成中英双语简报。",
      showCancel: false,
    });
  },
});
