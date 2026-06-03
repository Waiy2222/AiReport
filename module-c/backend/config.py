"""Module C 配置 — 所有环境变量集中管理"""
import os


class Settings:
    # 数据库
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ai_news"
    )

    # 微信小程序 — 环境变量名与 docker-compose.yml 保持一致
    WX_APPID: str = os.getenv("WECHAT_APPID", "")
    WX_SECRET: str = os.getenv("WECHAT_SECRET", "")

    # 订阅消息模板 ID（在微信公众平台申请）
    WX_TEMPLATE_ID: str = os.getenv("WX_TEMPLATE_ID", "")

    # 微信公众号（Phase 2 新增）— 环境变量名与 docker-compose.yml 保持一致
    WX_OA_TOKEN: str = os.getenv("WEIXIN_OA_TOKEN", "")
    WX_OA_APPID: str = os.getenv("WEIXIN_OA_APPID", "")
    WX_OA_SECRET: str = os.getenv("WEIXIN_OA_SECRET", "")
    WX_OA_ENCODING_AES_KEY: str = os.getenv("WEIXIN_OA_ENCODING_AES_KEY", "")

    # H5 基础地址（用于生成偏好设置链接）
    H5_BASE_URL: str = os.getenv("H5_BASE_URL", "http://localhost:8003/h5")

    # 服务端口
    PORT: int = int(os.getenv("PORT", "8003"))

    def validate(self) -> list[str]:
        """检查必填项，返回缺失项列表"""
        missing = []
        if not self.DATABASE_URL:
            missing.append("DATABASE_URL")
        return missing


settings = Settings()
