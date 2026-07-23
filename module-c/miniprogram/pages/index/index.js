const api = require("../../utils/api.js");
const { formatFullDate } = require("../../utils/date.js");
const { filterByTags } = require("../../utils/filter.js");
const app = getApp();

// 从简报数据提取所有标签，存到全局
function cacheActiveTags(briefing) {
  if (!briefing) return;
  const tagSet = app.globalData.activeTagSet || {};
  (briefing.sections || []).forEach(sec => {
    (sec.items || []).forEach(item => {
      (item.tags || []).forEach(t => { tagSet[t] = true; });
    });
  });
  app.globalData.activeTagSet = tagSet;
}

Page({
  data: {
    currentTab: "morning",
    briefing: null,
    dateText: "",
    totalItems: 0,
    headlineItem: {},
    stats: {},
    sectionsExpanded: {},
    loading: true,
    activeTags: [],
    // 个性化简报
    interestPanelExpanded: false,
    interestText: "",
    quickTags: [],
    selectedQuickTags: [],
    generating: false,
    taskId: null,
    pollTimer: null,
    pollCount: 0,
    MAX_POLLS: 90,
    isPersonalized: false,
    personalizedTags: [],
  },

  onLoad() {
    if (!app.globalData.activeTagSet) app.globalData.activeTagSet = {};
    this.fetchLatest("morning");
  },

  onShow() {
    // 如果正在展示个性化简报，不刷新为通用简报
    if (this.data.isPersonalized && this.data.briefing) return;

    const tags = app.globalData.userTags || wx.getStorageSync("userTags") || [];
    if (tags.join(",") !== (this.data.activeTags || []).join(",")) {
      this.setData({ activeTags: tags });
      const type = this.data.currentTab;
      this.fetchLatest(type);
    }
  },

  onPullDownRefresh() {
    this.fetchLatest(this.data.currentTab);
  },

  onTabTap(e) {
    const type = e.currentTarget.dataset.type;
    if (type === this.data.currentTab) return;
    this.setData({ currentTab: type });
    this.fetchLatest(type);
  },

  async fetchLatest(type) {
    this.setData({ loading: true });
    try {
      const data = await api.getLatestBriefing(type);
      cacheActiveTags(data);

      const tags = app.globalData.userTags || wx.getStorageSync("userTags") || [];
      const filtered = filterByTags(data, tags);

      // 展开前2个 section，其余折叠
      const expanded = {};
      (filtered.sections || []).forEach((s, i) => {
        expanded[i] = i < 2;
      });

      // 计算总条目数
      const totalItems = (filtered.sections || []).reduce(
        (sum, s) => sum + (s.items || []).length, 0
      );

      // 提取头条对应的原始 item（用于显示标签和分数）
      let headlineItem = {};
      // 取评分最高的 item 作为头条展示
      const allItems = [];
      (filtered.sections || []).forEach(s => (s.items || []).forEach(i => allItems.push(i)));
      for (const it of allItems) {
        if ((it.score || 0) >= (headlineItem.score || 0)) {
          headlineItem = it;
        }
      }

      // 提取统计信息
      const rawStats = data.raw_stats || {};
      const stats = {
        fetched: rawStats.fetched || 0,
        scored: rawStats.scored || 0,
        passed: rawStats.passed || 0,
        final_count: rawStats.final_count || totalItems,
        dedup_url_removed: rawStats.dedup_url_removed || 0,
        dedup_semantic_removed: rawStats.dedup_semantic_removed || 0,
        headline_title: (rawStats.headline || {}).title || "",
      };

      this.setData({
        briefing: filtered,
        dateText: formatFullDate(data.date),
        totalItems,
        headlineItem,
        stats,
        sectionsExpanded: expanded,
        loading: false,
        activeTags: tags,
      });
    } catch (err) {
      console.error("fetchLatest failed:", err);
      this.setData({ loading: false });
      wx.showToast({ title: "加载失败", icon: "none" });
    }
    wx.stopPullDownRefresh();
  },

  onSectionToggle(e) {
    const idx = e.currentTarget.dataset.index;
    const key = String(idx);
    this.setData({
      [`sectionsExpanded.${key}`]: !this.data.sectionsExpanded[key],
    });
  },

  onCardTap(e) {
    const id = e.currentTarget.dataset.id || (this.data.briefing && this.data.briefing.id);
    if (id) {
      wx.navigateTo({ url: `/pages/detail/detail?id=${id}` });
    }
  },

  onArticleTap(e) {
    const id = this.data.briefing && this.data.briefing.id;
    if (id) {
      wx.navigateTo({ url: `/pages/detail/detail?id=${id}` });
    }
  },

  onMiniImageError(e) {
    const { section, index } = e.currentTarget.dataset;
    const path = `briefing.sections[${section}].items[${index}]._imgHide`;
    this.setData({ [path]: true });
  },

  // ══════ 个性化简报 ══════

  onToggleInterestPanel() {
    const expanded = !this.data.interestPanelExpanded;
    this.setData({ interestPanelExpanded: expanded });
    if (expanded && this.data.quickTags.length === 0) {
      this._loadQuickTags();
    }
  },

  async _loadQuickTags() {
    try {
      const data = await api.getTags();
      const allTags = (data.tags || []).map(function (t) {
        t.selected = false;
        return t;
      });
      const activeSet = app.globalData.activeTagSet || {};
      const hasActive = Object.keys(activeSet).length > 0;
      const available = hasActive
        ? allTags.filter(function (t) { return activeSet[t.tag]; })
        : allTags;
      this.setData({ quickTags: available.slice(0, 8) });
    } catch (e) {
      // 标签加载失败不阻塞
    }
  },

  onQuickTagTap(e) {
    var tag = e.currentTarget.dataset.tag;
    var quickTags = this.data.quickTags.map(function (t) {
      if (t.tag === tag) t.selected = !t.selected;
      return t;
    });
    var selectedQuickTags = quickTags.filter(function (t) { return t.selected; }).map(function (t) { return t.tag; });
    this.setData({ quickTags: quickTags, selectedQuickTags: selectedQuickTags });
  },

  onInterestInput(e) {
    this.setData({ interestText: e.detail.value });
  },

  async onGenerateBriefing() {
    var that = this;
    var interestText = this.data.interestText;
    var selectedQuickTags = this.data.selectedQuickTags;
    if (this.data.generating || !interestText.trim()) return;

    this.setData({ generating: true, pollCount: 0 });

    try {
      var openid = app.globalData.openid || "anonymous";
      var resp = await api.generateBriefing(
        openid, interestText.trim(), selectedQuickTags, this.data.currentTab
      );

      if (!resp.valid) {
        wx.showToast({ title: resp.error || "输入无效", icon: "none", duration: 2500 });
        this.setData({ generating: false });
        return;
      }

      this.setData({ taskId: resp.task_id });
      this._startPolling();
    } catch (e) {
      console.error("Generate briefing failed:", e);
      wx.showToast({ title: "提交失败，请重试", icon: "none" });
      this.setData({ generating: false });
    }
  },

  _startPolling() {
    var that = this;
    function poll() {
      if (that.data.pollCount >= that.data.MAX_POLLS) {
        that.setData({ generating: false });
        wx.showToast({ title: "生成超时，请稍后重试", icon: "none" });
        return;
      }

      api.getGenerateStatus(that.data.taskId).then(function (status) {
        var count = that.data.pollCount + 1;
        that.setData({ pollCount: count });

        if (status.status === "completed" && status.briefing_id) {
          that.setData({ generating: false, interestPanelExpanded: false });
          api.getBriefingDetail(status.briefing_id).then(function (briefing) {
            that._displayPersonalizedBriefing(briefing);
          }).catch(function () {
            wx.showToast({ title: "获取简报失败", icon: "none" });
          });
        } else if (status.status === "failed") {
          that.setData({ generating: false });
          wx.showToast({ title: status.error || "生成失败", icon: "none" });
        } else if (status.status === "cancelled") {
          that.setData({ generating: false });
        } else {
          that.data.pollTimer = setTimeout(poll, 2000);
        }
      }).catch(function () {
        if (that.data.pollCount < 10) {
          that.data.pollTimer = setTimeout(poll, 2000);
        } else {
          that.setData({ generating: false });
          wx.showToast({ title: "网络异常，请重试", icon: "none" });
        }
      });
    }
    poll();
  },

  _displayPersonalizedBriefing(briefing) {
    var tags = briefing.interest_tags || [];
    var expanded = {};
    (briefing.sections || []).forEach(function (s, i) { expanded[i] = i < 2; });
    var totalItems = (briefing.sections || []).reduce(function (sum, s) {
      return sum + (s.items || []).length;
    }, 0);

    this.setData({
      briefing: briefing,
      dateText: formatFullDate(briefing.date),
      totalItems: totalItems,
      sectionsExpanded: expanded,
      loading: false,
      isPersonalized: true,
      personalizedTags: tags,
    });
    wx.pageScrollTo({ scrollTop: 0 });
  },

  onCancelGeneration() {
    if (this.data.pollTimer) {
      clearTimeout(this.data.pollTimer);
    }
    this.setData({ generating: false });
  },
});
