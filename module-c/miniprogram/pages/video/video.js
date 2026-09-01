const api = require("../../utils/api.js");
const app = getApp();

Page({
  data: {
    keyword: "",
    generating: false,
    videoId: null,
    pollTimer: null,
    pollCount: 0,
    genProgress: 0,
    MAX_POLLS: 300,

    // 视频列表
    videos: [],
    loading: true,
    page: 1,
    hasMore: true,
  },

  onLoad() {
    this._firstLoad = true;
    this.loadVideos();
  },

  onHide() {
    if (this.data.pollTimer) {
      clearTimeout(this.data.pollTimer);
      this.data.pollTimer = null;
    }
  },

  onShow() {
    if (!this._firstLoad) {
      this.loadVideos();
    }
    this._firstLoad = false;
    // 如果之前有正在生成的视频，恢复轮询
    if (this.data.videoId && this.data.generating && !this.data.pollTimer) {
      this._startPolling();
    }
  },

  onPullDownRefresh() {
    this.setData({ page: 1, videos: [], hasMore: true });
    this.loadVideos();
  },

  onReachBottom() {
    if (this.data.hasMore && !this.data.loading) {
      this.setData({ page: this.data.page + 1 });
      this.loadVideos();
    }
  },

  // ══════ 视频列表 ══════
  async loadVideos() {
    this.setData({ loading: true });
    try {
      const data = await api.getVideoList(this.data.page, 10);
      const items = (data.items || []).filter(item => item.status === 'done').map(item => ({
        ...item,
        coverUrl: item.cover_path ? api.getVideoCoverUrl(item.id) : "",
      }));
      const videos = this.data.page === 1
        ? items
        : [...this.data.videos, ...items];
      this.setData({
        videos,
        loading: false,
        hasMore: videos.length < (data.total || 0),
      });
    } catch (e) {
      console.error("loadVideos failed:", e);
      this.setData({ loading: false });
    }
    wx.stopPullDownRefresh();
  },

  // ══════ 关键词输入 ══════
  onKeywordInput(e) {
    this.setData({ keyword: e.detail.value });
  },

  onQuickTagTap(e) {
    const tag = e.currentTarget.dataset.tag;
    this.setData({ keyword: tag });
  },

  // ══════ 生成视频 ══════
  async onGenerateVideo() {
    const { keyword, generating } = this.data;
    if (generating || !keyword.trim()) return;

    this.setData({ generating: true, pollCount: 0, genProgress: 0 });

    try {
      const openid = app.globalData.openid || "anonymous";
      const resp = await api.generateVideo(keyword.trim(), openid);
      if (!resp.video_id) {
        throw new Error("服务返回异常");
      }
      this.setData({ videoId: resp.video_id });
      this._startPolling();
    } catch (e) {
      console.error("Generate video failed:", e);
      const errMsg = (e.error && e.message) ? "网络不通，请确认后端服务已启动"
        : (e.statusCode === 503 ? "视频生成服务未启动，请运行 module-f"
        : (e.statusCode >= 500 ? "服务器异常，请稍后重试"
        : "提交失败，请检查网络和服务状态"));
      wx.showToast({ title: errMsg, icon: "none", duration: 3000 });
      this.setData({ generating: false });
    }
  },

  _startPolling() {
    const that = this;
    function poll() {
      if (!that.data.generating) return; // 用户取消了
      if (that.data.pollCount >= that.data.MAX_POLLS) {
        that.setData({ generating: false });
        wx.showToast({ title: "生成超时，请稍后查看列表", icon: "none" });
        return;
      }
      api.getVideoStatus(that.data.videoId).then(status => {
        if (!that.data.generating) return;
        const count = that.data.pollCount + 1;
        const prog = Math.min(count / 60 * 90, 90);
        that.setData({ pollCount: count, genProgress: prog });

        if (status.status === "done" || status.status === "completed") {
          that.setData({ generating: false, page: 1, videos: [], hasMore: true });
          that.loadVideos().then(() => {
            wx.showToast({ title: "视频生成完成！", icon: "success" });
          });
          return;
        } else if (status.status === "failed") {
          that.setData({ generating: false });
          wx.showToast({ title: status.error_msg || "视频生成失败", icon: "none" });
        } else {
          that.data.pollTimer = setTimeout(poll, 2000);
        }
      }).catch(() => {
        if (!that.data.generating) return;
        if (that.data.pollCount < 10) {
          that.data.pollTimer = setTimeout(poll, 2000);
        } else {
          that.setData({ generating: false });
          wx.showToast({ title: "网络异常，请稍后查看", icon: "none" });
        }
      });
    }
    poll();
  },

  onCancelGeneration() {
    if (this.data.pollTimer) {
      clearTimeout(this.data.pollTimer);
      this.data.pollTimer = null;
    }
    this.setData({ generating: false });
  },

  // ══════ 播放视频 ══════
  onPlayVideo(e) {
    const videoId = e.currentTarget.dataset.id;
    if (videoId) {
      wx.navigateTo({ url: `/pages/video-player/video-player?id=${videoId}` });
    }
  },
});
