// ============================================================
// App lifecycle & global data — Module C Miniprogram
// ============================================================
App({
  globalData: {
    // ---- API ----
    apiBaseUrl: 'http://localhost:8003',

    // ---- User ----
    openid: null,       // set after wx.login / wechat auth
    isSubscribed: false,
    morningEnabled: true,
    eveningEnabled: true,

    // ---- Cache ----
    latestMorning: null,
    latestEvening: null,
  },

  onLaunch() {
    // Generate a mock openid for development (replace with real wx.login flow)
    this._initOpenid();

    // Check local-stored subscription preferences
    this._loadPreferences();
  },

  _initOpenid() {
    let openid = wx.getStorageSync('openid');
    if (!openid) {
      openid = 'dev_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
      wx.setStorageSync('openid', openid);
    }
    this.globalData.openid = openid;
  },

  _loadPreferences() {
    const morning = wx.getStorageSync('morning_enabled');
    const evening = wx.getStorageSync('evening_enabled');
    const subscribed = wx.getStorageSync('is_subscribed');

    if (typeof morning === 'boolean') {
      this.globalData.morningEnabled = morning;
    }
    if (typeof evening === 'boolean') {
      this.globalData.eveningEnabled = evening;
    }
    if (typeof subscribed === 'boolean') {
      this.globalData.isSubscribed = subscribed;
    }
  },

  /**
   * Save subscription status locally.
   */
  setSubscription(subscribed, morning, evening) {
    this.globalData.isSubscribed = subscribed;
    this.globalData.morningEnabled = morning;
    this.globalData.eveningEnabled = evening;

    wx.setStorageSync('is_subscribed', subscribed);
    wx.setStorageSync('morning_enabled', morning);
    wx.setStorageSync('evening_enabled', evening);
  },
});
