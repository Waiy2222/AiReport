const app = getApp();
const api = require("../../utils/api.js");

Page({
  data: {
    openid: "",
    openidMasked: "",
    // 统计
    stats: { myBriefings: 0, followedTags: 0, subscribed: false },
    // 推送设置
    pushMorning: true,
    pushEvening: true,
    pushSaving: false,
    // 标签
    allTags: [],
    selectedTags: [],
    loadingTags: true,
    // 最近专属简报
    recentBriefings: [],
    loadingRecent: false,
  },

  onLoad() {
    const openid = app.globalData.openid || wx.getStorageSync('openid') || "anonymous";
    const storedTags = wx.getStorageSync("userTags") || [];
    app.globalData.userTags = storedTags;
    this.setData({
      openid,
      openidMasked: openid.substring(0, 8) + "***" + openid.slice(-4),
    });
    this.loadTags();
    // 统计和最近简报延迟加载，不阻塞首屏
    setTimeout(() => { this.loadStats(); this.loadRecentBriefings(); }, 500);
  },

  onShow() {
    // 首次加载由 onLoad 处理，onShow 只在切 tab 回来看是否有新数据
    if (!this._init) { this._init = true; return; }
    this.loadTags();
    this.loadStats();
    this.loadRecentBriefings();
  },

  // ══════ 统计 ══════
  async loadStats() {
    try {
      const [myData, prefData, videoData] = await Promise.all([
        api.getMyBriefings(this.data.openid, 1, 1).catch(() => ({ total: 0 })),
        api.getPreferences(this.data.openid).catch(() => ({})),
        api.getVideoList(1, 1).catch(() => ({ total: 0 })),
      ]);
      const savedTags = wx.getStorageSync("userTags") || [];
      this.setData({
        stats: {
          myBriefings: myData.total || 0,
          followedTags: savedTags.length,
          subscribed: !!(prefData.morning_enabled || prefData.evening_enabled),
          videoCount: videoData.total || 0,
        },
        pushMorning: prefData.morning_enabled !== false,
        pushEvening: prefData.evening_enabled !== false,
      });
    } catch (e) {
      const savedTags = wx.getStorageSync("userTags") || [];
      this.setData({
        stats: {
          ...this.data.stats,
          myBriefings: this.data.stats.myBriefings || 0,
          followedTags: savedTags.length,
          subscribed: this.data.stats.subscribed || false,
        },
      });
    }
  },

  // ══════ 最近专属简报 ══════
  async loadRecentBriefings() {
    this.setData({ loadingRecent: true });
    try {
      const data = await api.getMyBriefings(this.data.openid, 1, 3);
      this.setData({
        recentBriefings: (data.items || []).slice(0, 3),
        loadingRecent: false,
      });
    } catch (e) {
      this.setData({ loadingRecent: false });
    }
  },

  // ══════ 推送设置 ══════
  onToggleMorning() {
    const newVal = !this.data.pushMorning;
    this.setData({ pushMorning: newVal });
    this._savePushSettings();
  },

  onToggleEvening() {
    const newVal = !this.data.pushEvening;
    this.setData({ pushEvening: newVal });
    this._savePushSettings();
  },

  async _savePushSettings() {
    if (this.data.pushSaving) return;
    this.setData({ pushSaving: true });
    try {
      await api.subscribe(this.data.openid, this.data.pushMorning, this.data.pushEvening);
      wx.showToast({ title: "已更新", icon: "success", duration: 1200 });
    } catch (e) {
      console.error("save push settings failed:", e);
    }
    this.setData({ pushSaving: false });
  },

  // ══════ 标签（动态：用户实际兴趣 + 系统标签）══════
  async loadTags() {
    try {
      const savedTags = wx.getStorageSync("userTags") || [];
      // 用户最近搜索过的兴趣词（从活标签取）
      const liveTags = wx.getStorageSync("liveTags") || [];
      // 已生成过的兴趣标签
      const personalizedTags = wx.getStorageSync("personalizedTags") || [];

      // 合并去重：用户活标签优先 → 个性化标签 → 系统标签
      const mergedSet = new Set([...liveTags, ...personalizedTags, ...savedTags]);

      let allTags = [];
      // 用户自己搜过的标签排前面
      mergedSet.forEach(tag => {
        allTags.push({
          tag: tag,
          label_zh: tag,
          selected: savedTags.indexOf(tag) >= 0,
          isUserTag: true,
        });
      });

      this.setData({ allTags, selectedTags: savedTags, loadingTags: false });
    } catch (e) {
      console.error("loadTags failed", e);
      this.setData({ loadingTags: false });
    }
  },

  onTagTap(e) {
    // 防止 ✕ 删除按钮冒泡触发 tag 切换
    if (e.target.dataset.action === 'remove') return;

    const tag = e.currentTarget.dataset.tag;
    const { allTags, selectedTags } = this.data;
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

  onRemoveTag(e) {
    const tag = e.currentTarget.dataset.tag;
    // 从展示列表移除
    const allTags = this.data.allTags.filter(t => t.tag !== tag);
    const selectedTags = this.data.selectedTags.filter(t => t !== tag);
    // 从存储移除
    wx.setStorageSync('userTags', selectedTags);
    const liveTags = (wx.getStorageSync('liveTags') || []).filter(t => t !== tag);
    wx.setStorageSync('liveTags', liveTags);
    const personalizedTags = (wx.getStorageSync('personalizedTags') || []).filter(t => t !== tag);
    wx.setStorageSync('personalizedTags', personalizedTags);
    this.setData({ allTags, selectedTags, stats: { ...this.data.stats, followedTags: selectedTags.length } });
  },

  async onSavePreferences() {
    const { selectedTags } = this.data;
    app.globalData.userTags = selectedTags;
    wx.setStorageSync("userTags", selectedTags);

    // 同步到服务器
    try {
      await api.setPreferences(this.data.openid, selectedTags);
    } catch (e) {
      console.error("sync preferences failed:", e);
    }

    this.setData({ stats: { ...this.data.stats, followedTags: selectedTags.length } });
    wx.showToast({ title: "已保存 ✓", icon: "success" });

    setTimeout(() => {
      wx.switchTab({ url: '/pages/index/index' });
    }, 800);
  },

  // ══════ 专属简报跳转 ══════
  onBriefingTap(e) {
    const id = e.currentTarget.dataset.id;
    if (id) wx.navigateTo({ url: `/pages/detail/detail?id=${id}` });
  },

  onViewAllBriefings() {
    wx.switchTab({ url: '/pages/history/history' });
    // 通过全局变量传递筛选意图
    app.globalData.historyFilter = 'personalized';
  },

  // ══════ 设置 ══════
  onClearCache() {
    wx.showModal({
      title: "清除缓存",
      content: "将清除本地标签偏好和活标签数据，不会影响已生成的简报。确定清除吗？",
      success: (res) => {
        if (res.confirm) {
          wx.removeStorageSync("userTags");
          wx.removeStorageSync("liveTags");
          wx.removeStorageSync("personalizedTags");
          app.globalData.userTags = [];
          app.globalData.activeTagSet = {};
          this.setData({
            selectedTags: [],
            allTags: this.data.allTags.map(t => ({ ...t, selected: false })),
            stats: { ...this.data.stats, followedTags: 0 },
          });
          wx.showToast({ title: "已清除", icon: "success" });
        }
      },
    });
  },

  onAbout() {
    wx.showModal({
      title: "AI 资讯简报",
      content: "按你的兴趣，AI 每日精选科技资讯。\n\n在「专属简报」输入感兴趣的领域，即可生成量身定制的新闻简报。\n\n在「我的」设置兴趣标签，通用简报会自动筛选相关内容。\n\n在「视频」输入关键词生成 AI 视频早报。",
      showCancel: false,
    });
  },

  onGoVideo() {
    wx.switchTab({ url: '/pages/video/video' });
  },
});
