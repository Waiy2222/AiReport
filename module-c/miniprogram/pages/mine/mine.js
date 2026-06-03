const app = getApp();
const api = require("../../utils/api.js");

Page({
  data: {
    openid: "",
    openidMasked: "",
    morningEnabled: false,
    eveningEnabled: false,
    // Phase 2: 标签偏好
    allTags: [],
    selectedTags: [],
    loadingTags: true,
    // Phase 3: 信源健康度
    sourceHealth: [],
    pendingRecommendations: 0,
  },

  onLoad() {
    const openid = app.globalData.openid || "mock_openid_user_001";
    this.setData({
      openid,
      openidMasked: openid.substring(0, 8) + "***" + openid.slice(-4),
    });
    this.loadTagsAndPreferences();
    this.loadSourcesHealth();
  },

  onShow() {
    // 页面显示时刷新偏好
    if (this.data.openid) {
      this.loadTagsAndPreferences();
      this.loadSourcesHealth();
    }
  },

  async loadTagsAndPreferences() {
    try {
      const tagsResp = await api.getTags();
      const tags = tagsResp.tags || [];

      let selectedTags = [];
      try {
        const prefs = await api.getPreferences(this.data.openid);
        selectedTags = prefs.tags || [];
      } catch (e) {
        console.warn("获取偏好失败", e);
      }

      // 标记已选中的标签
      const allTags = tags.map((t) => ({
        ...t,
        selected: selectedTags.indexOf(t.tag) >= 0,
      }));

      this.setData({
        allTags,
        selectedTags,
        loadingTags: false,
      });
    } catch (e) {
      console.error("加载标签失败", e);
      this.setData({ loadingTags: false });
    }
  },

  onTagTap(e) {
    const tag = e.currentTarget.dataset.tag;
    const { allTags, selectedTags } = this.data;
    const idx = selectedTags.indexOf(tag);
    let newSelected;

    if (idx >= 0) {
      newSelected = selectedTags.filter((t) => t !== tag);
    } else {
      newSelected = [...selectedTags, tag];
    }

    const newAllTags = allTags.map((t) => ({
      ...t,
      selected: newSelected.indexOf(t.tag) >= 0,
    }));

    this.setData({
      allTags: newAllTags,
      selectedTags: newSelected,
    });
  },

  async onSavePreferences() {
    const { openid, selectedTags } = this.data;
    try {
      await api.setPreferences(openid, selectedTags);
      wx.showToast({ title: "已保存", icon: "success" });
    } catch (e) {
      wx.showToast({ title: "保存失败", icon: "none" });
    }
  },

  onToggleMorning(e) {
    const enabled = e.detail.value;
    this.setData({ morningEnabled: enabled });
    this.saveSubscription();
  },

  onToggleEvening(e) {
    const enabled = e.detail.value;
    this.setData({ eveningEnabled: enabled });
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
      content:
        "每天 8:00 / 20:00 自动推送 AI 和智能体领域精选开源资讯。由 AI 评分、去重、摘要后生成中英双语简报。",
      showCancel: false,
    });
  },
});
