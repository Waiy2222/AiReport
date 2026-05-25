App({
  globalData: {
    openid: "",
    baseUrl: "http://localhost:8003",
  },

  onLaunch() {
    this.getOpenid();
  },

  getOpenid() {
    wx.login({
      success: (res) => {
        if (res.code) {
          wx.request({
            url: `${this.globalData.baseUrl}/api/wechat/login`,
            method: "POST",
            data: { js_code: res.code },
            success: (resp) => {
              if (resp.data && resp.data.openid) {
                this.globalData.openid = resp.data.openid;
              }
            },
            fail: () => {
              console.warn("登录接口未就绪，使用本地模式");
            },
          });
        }
      },
    });
  },
});
