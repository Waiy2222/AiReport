const api = require("../../utils/api.js");

Page({
  data: {
    videoId: "",
    title: "",
    videoUrl: "",
    coverUrl: "",
    duration: 0,
    loading: true,
  },

  onLoad(options) {
    const videoId = options.id || "";
    if (!videoId) {
      wx.showToast({ title: "参数错误", icon: "none" });
      wx.navigateBack();
      return;
    }

    this.setData({ videoId });
    this.loadVideoInfo();
  },

  async loadVideoInfo() {
    try {
      const status = await api.getVideoStatus(this.data.videoId);
      this.setData({
        title: status.title || "AI 视频早报",
        videoUrl: api.getVideoFileUrl(this.data.videoId),
        coverUrl: api.getVideoCoverUrl(this.data.videoId),
        duration: status.duration_seconds || 0,
        loading: false,
      });

      // 如果视频还在处理中
      if (status.status === "processing" || status.status === "pending") {
        wx.showToast({ title: "视频处理中，请稍后", icon: "none" });
      }
    } catch (e) {
      console.error("loadVideoInfo failed:", e);
      wx.showToast({ title: "加载视频失败", icon: "none" });
      this.setData({ loading: false });
    }
  },

  // ══════ 分享 ══════
  onShareAppMessage() {
    return {
      title: this.data.title || "AI 视频早报",
      path: `/pages/video-player/video-player?id=${this.data.videoId}`,
      imageUrl: this.data.coverUrl || "",
    };
  },

  onVideoError(e) {
    console.error("Video error:", e.detail);
    wx.showToast({ title: "视频加载失败", icon: "none" });
  },

  onVideoEnd() {
    // 视频播放完毕
  },
});
