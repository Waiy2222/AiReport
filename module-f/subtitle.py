"""Subtitle generation with Whisper (OpenAI / local).

Generates .srt or .ass subtitles from the final video audio track.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", "./output")).resolve()
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")  # small for Chinese accuracy
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "zh")


class SubtitleGenerator:
    """Whisper-based subtitle engine."""

    def __init__(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self._model = None  # lazy load

    async def generate(
        self,
        audio_path: str,
        output_path: str | None = None,
        format: str = "srt",
    ) -> str | None:
        """Generate subtitles from an audio file. Returns path to .srt file."""
        output_path = output_path or str(
            OUTPUT_DIR / f"{Path(audio_path).stem}.{format}"
        )

        try:
            import whisper

            model = self._load_model(whisper)
            result = model.transcribe(
                audio_path,
                language=WHISPER_LANGUAGE,
                verbose=False,
            )

            # Write SRT
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(self._to_srt(result["segments"]))

            logger.info("Subtitles generated: %s (%d segments)",
                        output_path, len(result["segments"]))
            return output_path

        except ImportError:
            logger.warning("openai-whisper not installed — using mock")
            return self._mock_srt(audio_path, output_path)
        except Exception:
            logger.exception("Subtitle generation failed")
            return None

    async def generate_from_video(
        self,
        video_path: str,
        output_path: str | None = None,
    ) -> str | None:
        """Extract audio from video and generate subtitles."""
        import subprocess

        audio_path = str(Path(video_path).parent / f"{Path(video_path).stem}_audio.wav")

        # extract audio
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            audio_path,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=120, check=True,
                           encoding="utf-8", errors="replace")
        except Exception:
            logger.warning("Audio extraction failed for %s", video_path)
            return None

        result = await self.generate(audio_path, output_path)

        # clean up temp audio
        if Path(audio_path).exists():
            Path(audio_path).unlink()

        return result

    # ---- internal -----------------------------------------------------

    def _load_model(self, whisper_module):
        if self._model is None:
            self._model = whisper_module.load_model(WHISPER_MODEL)
        return self._model

    @staticmethod
    def _to_srt(segments: list[dict]) -> str:
        """Convert Whisper segments to SRT format with simplified Chinese."""
        lines: list[str] = []
        for i, seg in enumerate(segments, 1):
            start = _format_srt_time(seg["start"])
            end = _format_srt_time(seg["end"])
            text = _to_simplified(seg["text"].strip())
            lines.append(f"{i}\n{start} --> {end}\n{text}\n")
        return "\n".join(lines)

    def _mock_srt(self, audio_path: str, output_path: str) -> str:
        """Create a minimal .srt for testing."""
        content = (
            "1\n"
            "00:00:00,000 --> 00:00:05,000\n"
            "[Mock] AI 资讯每周视频 — 字幕待生成\n\n"
        )
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        return output_path


# Common traditional → simplified Chinese character map for Whisper output correction
_T2S_MAP = str.maketrans({
    '體': '体', '臺': '台', '雲': '云', '為': '为', '於': '于',
    '會': '会', '個': '个', '時': '时', '來': '来', '開': '开',
    '關': '关', '對': '对', '說': '说', '還': '还', '這': '这',
    '進': '进', '過': '过', '發': '发', '現': '现', '後': '后',
    '當': '当', '經': '经', '從': '从', '動': '动', '實': '实',
    '點': '点', '機': '机', '氣': '气', '電': '电', '話': '话',
    '長': '长', '門': '门', '間': '间', '學': '学', '業': '业',
    '萬': '万', '與': '与', '專': '专', '義': '义', '頭': '头',
    '無': '无', '見': '见', '問': '问', '寫': '写', '樣': '样',
    '應': '应', '組': '组', '總': '总', '線': '线', '繫': '系',
    '網': '网', '節': '节', '術': '术', '數': '数', '據': '据',
    '視': '视', '認': '认', '識': '识', '讓': '让', '設': '设',
    '計': '计', '語': '语', '調': '调', '論': '论', '變': '变',
    '軍': '军', '備': '备', '賽': '赛', '爭': '争', '戰': '战',
    '協': '协', '構': '构', '標': '标', '準': '准', '顯': '显',
    '麗': '丽', '極': '极', '預': '预', '領': '领', '導': '导',
    '層': '层', '創': '创', '劃': '划', '劇': '剧', '優': '优',
    '勢': '势', '嚴': '严', '帶': '带', '廣': '广', '廠': '厂',
    '際': '际', '斷': '断', '異': '异', '終': '终',
    '亞': '亚', '衛': '卫', '衝': '冲', '擊': '击', '償': '偿',
    '彌': '弥', '歐': '欧', '將': '将', '轉': '转', '達': '达',
    '質': '质', '遠': '远', '連': '连',
    '奮': '奋', '擁': '拥', '護': '护', '歷': '历',
    '風': '风', '險': '险', '級': '级', '圍': '围',
    '並': '并', '復': '复', '題': '题', '熱': '热', '競': '竞',
    '資': '资', '軟': '软', '銀': '银', '錯': '错', '誤': '误',
    '鏡': '镜', '頭': '头', '買': '买', '賣': '卖', '飛': '飞',
    '馬': '马', '魚': '鱼', '鳥': '鸟', '龍': '龙', '華': '华',
    '員': '员', '園': '园', '國': '国', '圖': '图', '團': '团',
    '場': '场', '塊': '块', '備': '备', '傳': '传', '傷': '伤',
    '億': '亿', '僅': '仅', '儘': '尽', '價': '价', '儲': '储',
    '幣': '币', '劑': '剂', '劉': '刘', '剛': '刚', '則': '则',
    '剝': '剥', '務': '务', '勢': '势', '區': '区', '協': '协',
    '卻': '却', '厲': '厉', '參': '参', '叢': '丛', '嚇': '吓',
    '員': '员', '單': '单', '嗎': '吗', '嚴': '严', '團': '团',
    '壓': '压', '鹽': '盐', '廳': '厅', '狀': '状', '獨': '独',
    '環': '环', '畫': '画', '當': '当', '疊': '叠', '盡': '尽',
    '盤': '盘', '眾': '众', '睜': '睁', '碼': '码', '礎': '础',
    '積': '积', '築': '筑', '範': '范', '簽': '签', '節': '节',
    '糧': '粮', '紀': '纪', '約': '约', '級': '级', '納': '纳',
    '純': '纯', '紙': '纸', '紛': '纷', '組': '组', '結': '结',
    '絕': '绝', '統': '统', '絲': '丝', '經': '经', '維': '维',
    '綜': '综', '緊': '紧', '線': '线', '編': '编', '緣': '缘',
    '縣': '县', '縱': '纵', '縮': '缩', '績': '绩', '織': '织',
    '罰': '罚', '義': '义', '習': '习', '聯': '联', '聽': '听',
    '腳': '脚', '臉': '脸', '膽': '胆', '與': '与', '興': '兴',
    '舉': '举', '舊': '旧', '臺': '台', '船': '船', '艦': '舰',
    '獲': '获', '蘇': '苏', '處': '处', '虛': '虚', '號': '号',
    '術': '术', '衛': '卫', '補': '补', '裝': '装', '製': '制',
    '複': '复', '規': '规', '覺': '觉', '覽': '览', '觸': '触',
    '訂': '订', '計': '计', '訊': '讯', '討': '讨', '訓': '训',
    '記': '记', '許': '许', '設': '设', '訴': '诉', '評': '评',
    '詞': '词', '詢': '询', '該': '该', '詳': '详', '認': '认',
    '誌': '志', '誤': '误', '說': '说', '讀': '读', '誰': '谁',
    '論': '论', '調': '调', '談': '谈', '謀': '谋', '講': '讲',
    '證': '证', '識': '识', '議': '议', '護': '护', '譽': '誉',
    '讀': '读', '變': '变', '讓': '让', '貝': '贝', '負': '负',
    '財': '财', '責': '责', '貨': '货', '貧': '贫', '費': '费',
    '買': '买', '貸': '贷', '貿': '贸', '資': '资', '賓': '宾',
    '賜': '赐', '質': '质', '賴': '赖', '賺': '赚', '贊': '赞',
    '賽': '赛', '贏': '赢', '賣': '卖', '購': '购', '賠': '赔',
    '養': '养', '駕': '驾', '驗': '验', '馬': '马', '魚': '鱼',
})


def _to_simplified(text: str) -> str:
    """Convert common traditional Chinese chars to simplified."""
    text = text.translate(_T2S_MAP)
    # Remove markdown artifacts that Edge TTS might read aloud
    text = text.replace('#', '').replace('*', '').replace('`', '')
    text = text.replace('警號', '').replace('警号', '')
    return text


def _format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
