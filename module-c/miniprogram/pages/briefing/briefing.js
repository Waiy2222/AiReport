const api = require("../../utils/api.js");
const { formatFullDate } = require("../../utils/date.js");
const app = getApp();

Page({
  data: {
    // 专属简报
    briefing: null,
    headlineItem: {},
    totalItems: 0,
    sectionsExpanded: {},
    isPersonalized: false,
    personalizedTags: [],
    // 输入
    interestText: "",
    quickTags: [],
    selectedQuickTags: [],
    liveTags: [],  // 活标签：生成简报后自动填充，用户可手动删
    // 生成
    generating: false,
    taskId: null,
    pollTimer: null,
    pollCount: 0,
    genProgress: 0,
    MAX_POLLS: 90,
  },

  onLoad() {
    this._loadQuickTags();
    this._loadLiveTags();
  },

  onHide() {
    if (this.data.pollTimer) {
      clearTimeout(this.data.pollTimer);
      this.data.pollTimer = null;
    }
  },

  onShow() {
    this._loadLiveTags();
    if (!this.data.isPersonalized) {
      this._loadQuickTags();
    }
  },

  _loadLiveTags() {
    const tags = wx.getStorageSync('liveTags') || [];
    this.setData({ liveTags: tags });
  },

  _saveLiveTags(tags) {
    wx.setStorageSync('liveTags', tags);
    this.setData({ liveTags: tags });
  },

  onRemoveLiveTag(e) {
    const tag = e.currentTarget.dataset.tag;
    const liveTags = this.data.liveTags.filter(t => t !== tag);
    this._saveLiveTags(liveTags);
  },

  // ══════ 快速标签 ══════
  async _loadQuickTags() {
    try {
      const data = await api.getTags();
      const allTags = (data.tags || []).map(t => ({ ...t, selected: false }));
      const activeSet = app.globalData.activeTagSet || {};
      const hasActive = Object.keys(activeSet).length > 0;
      const available = hasActive ? allTags.filter(t => activeSet[t.tag]) : allTags;
      this.setData({ quickTags: available.slice(0, 8) });
    } catch (e) {}
  },

  onQuickTagTap(e) {
    const tag = e.currentTarget.dataset.tag;
    const quickTags = this.data.quickTags.map(t => {
      if (t.tag === tag) t.selected = !t.selected;
      return t;
    });
    const selectedQuickTags = quickTags.filter(t => t.selected).map(t => t.tag);
    this.setData({ quickTags, selectedQuickTags });
  },

  onInterestInput(e) {
    this.setData({ interestText: e.detail.value });
  },

  // ══════ 生成专属简报 ══════
  async onGenerateBriefing() {
    const { interestText, selectedQuickTags, generating } = this.data;
    if (generating || !interestText.trim()) return;
    this.setData({ generating: true, pollCount: 0, genProgress: 0 });
    try {
      const openid = app.globalData.openid || "anonymous";
      const type = new Date().getHours() < 12 ? "morning" : "evening";
      const resp = await api.generateBriefing(openid, interestText.trim(), selectedQuickTags, type);
      if (!resp.valid) {
        wx.showToast({ title: resp.error || "输入无效", icon: "none", duration: 2500 });
        this.setData({ generating: false });
        return;
      }
      this.setData({ taskId: resp.task_id });
      this._startPolling();
    } catch (e) {
      console.error("Generate failed:", e);
      wx.showToast({ title: "提交失败", icon: "none" });
      this.setData({ generating: false });
    }
  },

  _startPolling() {
    const that = this;
    function poll() {
      if (!that.data.generating) return;
      if (that.data.pollCount >= that.data.MAX_POLLS) {
        that.setData({ generating: false });
        wx.showToast({ title: "生成超时", icon: "none" });
        return;
      }
      api.getGenerateStatus(that.data.taskId).then(status => {
        if (!that.data.generating) return;
        const count = that.data.pollCount + 1;
        const prog = Math.min(count / 25 * 90, 90);
        that.setData({ pollCount: count, genProgress: prog });
        if (status.status === "completed" && status.briefing_id) {
          that.setData({ generating: false });
          api.getBriefingDetail(status.briefing_id).then(briefing => {
            // generating 为 false 表示用户没有发起新一次生成，才展示结果
            if (!that.data.generating) that._displayPersonalizedBriefing(briefing);
          }).catch(() => wx.showToast({ title: "获取失败", icon: "none" }));
        } else if (status.status === "failed") {
          that.setData({ generating: false });
          wx.showToast({ title: status.error || "生成失败", icon: "none" });
        } else if (status.status === "cancelled") {
          that.setData({ generating: false });
        } else {
          that.data.pollTimer = setTimeout(poll, 2000);
        }
      }).catch(() => {
        if (!that.data.generating) return;
        if (that.data.pollCount < 10) that.data.pollTimer = setTimeout(poll, 2000);
        else { that.setData({ generating: false }); wx.showToast({ title: "网络异常", icon: "none" }); }
      });
    }
    poll();
  },

  _displayPersonalizedBriefing(briefing) {
    const tags = briefing.interest_tags || [];
    const expanded = {};
    (briefing.sections || []).forEach((s, i) => { expanded[i] = true; });
    const totalItems = (briefing.sections || []).reduce((sum, s) => sum + (s.items || []).length, 0);

    let headlineItem = {};
    const allItems = [];
    (briefing.sections || []).forEach(s => (s.items || []).forEach(i => allItems.push(i)));
    for (const it of allItems) {
      const itScore = it.score || 0;
      const curScore = headlineItem.score || 0;
      if ((it.image_url && !headlineItem.image_url) || ((it.image_url === headlineItem.image_url) && itScore >= curScore)) {
        headlineItem = it;
      }
    }

    // 活标签：新标签加入队列，最多10个，去重
    wx.setStorageSync('personalizedTags', tags);
    const existingLive = wx.getStorageSync('liveTags') || [];
    const merged = [...new Set([...tags, ...existingLive])].slice(0, 10);
    wx.setStorageSync('liveTags', merged);

    this.setData({
      briefing, headlineItem, totalItems, sectionsExpanded: expanded,
      isPersonalized: true, personalizedTags: tags, liveTags: merged,
    });
    wx.pageScrollTo({ scrollTop: 0 });
  },

  onNewPersonalized() {
    // 完全重置所有状态，确保输入面板和按钮正常显示
    if (this.data.pollTimer) clearTimeout(this.data.pollTimer);
    this.setData({
      isPersonalized: false, briefing: null, headlineItem: {},
      personalizedTags: [], interestText: "", selectedQuickTags: [],
      generating: false, pollCount: 0, genProgress: 0, taskId: null,
    });
  },

  onSectionToggle(e) {
    const idx = String(e.currentTarget.dataset.index);
    this.setData({ [`sectionsExpanded.${idx}`]: !this.data.sectionsExpanded[idx] });
  },

  onCardTap(e) {
    const id = this.data.briefing && this.data.briefing.id;
    if (id) wx.navigateTo({ url: `/pages/detail/detail?id=${id}` });
  },

  onArticleTap() {
    const id = this.data.briefing && this.data.briefing.id;
    if (id) wx.navigateTo({ url: `/pages/detail/detail?id=${id}` });
  },

  onMiniImageError(e) {
    const { section, index } = e.currentTarget.dataset;
    this.setData({ [`briefing.sections[${section}].items[${index}]._imgHide`]: true });
  },

  onHeadImageError() {
    this.setData({ 'headlineItem._headImgHide': true });
  },

  onCancelGeneration() {
    if (this.data.pollTimer) clearTimeout(this.data.pollTimer);
    this.setData({ generating: false });
  },
});
