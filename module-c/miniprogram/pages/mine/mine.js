// ============================================================
// Mine Page — Subscription Settings & About
// ============================================================
const api = require('../../utils/api');

Page({
  data: {
    // ---- Subscription ----
    isSubscribed: false,
    morningEnabled: true,
    eveningEnabled: true,

    // ---- UI State ----
    subscribing: false,
    unsubscribing: false,
  },

  onLoad() {
    this._syncFromApp();
  },

  onShow() {
    this._syncFromApp();
  },

  _syncFromApp() {
    const app = getApp();
    this.setData({
      isSubscribed: app.globalData.isSubscribed,
      morningEnabled: app.globalData.morningEnabled,
      eveningEnabled: app.globalData.eveningEnabled,
    });
  },

  // ---- Event Handlers ----

  /** Toggle morning subscription */
  onMorningToggle(e) {
    const value = e.detail.value;
    this.setData({ morningEnabled: value });
    this._updateSubscription(value, this.data.eveningEnabled);
  },

  /** Toggle evening subscription */
  onEveningToggle(e) {
    const value = e.detail.value;
    this.setData({ eveningEnabled: value });
    this._updateSubscription(this.data.morningEnabled, value);
  },

  /** Update subscription preferences on the server */
  async _updateSubscription(morning, evening) {
    const app = getApp();
    const { openid, isSubscribed } = app.globalData;

    if (!isSubscribed) return; // Only update if already subscribed

    try {
      await api.subscribe(openid, morning, evening);
      app.setSubscription(true, morning, evening);
    } catch (err) {
      console.error('[Mine] update subscription error:', err);
      // Revert toggle on failure
      this._syncFromApp();
    }
  },

  /** Subscribe action */
  async onSubscribeTap() {
    const app = getApp();
    const { openid, morningEnabled, eveningEnabled } = app.globalData;

    this.setData({ subscribing: true });

    try {
      await api.subscribe(openid, morningEnabled, eveningEnabled);
      app.setSubscription(true, morningEnabled, eveningEnabled);
      this.setData({ isSubscribed: true, subscribing: false });
      wx.showToast({ title: '订阅成功', icon: 'success' });
    } catch (err) {
      console.error('[Mine] subscribe error:', err);
      this.setData({ subscribing: false });
    }
  },

  /** Unsubscribe action */
  async onUnsubscribeTap() {
    const app = getApp();

    wx.showModal({
      title: '确认取消订阅',
      content: '取消后将不再接收AI资讯推送通知',
      confirmText: '确认取消',
      confirmColor: '#e74c3c',
      success: async (res) => {
        if (!res.confirm) return;

        this.setData({ unsubscribing: true });

        try {
          await api.unsubscribe(app.globalData.openid);
          app.setSubscription(false, app.globalData.morningEnabled, app.globalData.eveningEnabled);
          this.setData({
            isSubscribed: false,
            unsubscribing: false,
          });
          wx.showToast({ title: '已取消订阅', icon: 'none' });
        } catch (err) {
          console.error('[Mine] unsubscribe error:', err);
          this.setData({ unsubscribing: false });
        }
      },
    });
  },

  /** About item tap */
  onAboutTap() {
    wx.showModal({
      title: '关于 AI资讯简报',
      content:
        'AI资讯简报是一款基于人工智能的每日新闻聚合摘要工具。\n\n' +
        '支持早报和晚报推送，为您筛选最值得关注的AI领域动态，提供简洁明了的要点总结。\n\n' +
        '版本：v1.0.0\n' +
        '开发团队：AI News Briefing Team',
      showCancel: false,
      confirmText: '知道了',
    });
  },

  /** Feedback */
  onFeedbackTap() {
    wx.showToast({ title: '反馈功能开发中', icon: 'none' });
  },
});
