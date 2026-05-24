const app = getApp();
const api = require("../../utils/api.js");

Page({
  data: {
    openid: "",
    openidMasked: "",
    morningEnabled: false,
    eveningEnabled: false,
  },

  onLoad() {
    const openid = app.globalData.openid || "mock_openid_user_001";
    this.setData({
      openid,
      openidMasked: openid.substring(0, 8) + "***" + openid.slice(-4),
    });
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

  onAbout() {
    wx.showModal({
      title: "AI 资讯简报",
      content: "每天 8:00 / 20:00 自动推送 AI 和智能体领域精选开源资讯。由 AI 评分、去重、摘要后生成中英双语简报。",
      showCancel: false,
    });
  },
});
