"""Module C 配置 — 所有环境变量集中管理"""
import os


class Settings:
    # 数据库
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ai_news"
    )

    # 微信小程序
    WX_APPID: str = os.getenv("WX_APPID", "")
    WX_SECRET: str = os.getenv("WX_SECRET", "")

    # 订阅消息模板 ID（在微信公众平台申请）
    WX_TEMPLATE_ID: str = os.getenv("WX_TEMPLATE_ID", "")

    # 服务端口
    PORT: int = int(os.getenv("PORT", "8003"))

    def validate(self) -> list[str]:
        """检查必填项，返回缺失项列表"""
        missing = []
        if not self.DATABASE_URL:
            missing.append("DATABASE_URL")
        return missing


settings = Settings()
