from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import math
import os
import random
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests
from lunar_python import Solar
try:
    from ichingpy import Hexagram, Line, LineStatus, SixLinesDivinationEngine, Trigram
    ICHINGPY_AVAILABLE = True
    ICHINGPY_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - guarded by runtime checks
    Hexagram = Line = LineStatus = SixLinesDivinationEngine = Trigram = None
    ICHINGPY_AVAILABLE = False
    ICHINGPY_IMPORT_ERROR = exc

logger = logging.getLogger(__name__)
SENSITIVE_KEYWORDS = ("api_key", "apikey", "secret", "token")


class PdfExportError(RuntimeError):
    """Raised when marriage PDF export fails."""


REL_SCORE_CONFIG: Dict[str, Dict[str, Any]] = {
    "default": {
        "weights": {
            "complementarity": 30,
            "day_master": 20,
            "spouse_palace": 20,
            "children_sync": 15,
            "dayun_sync": 15,
        },
        "base": {
            "complementarity": 15,
            "day_master": 10,
            "spouse_palace": 10,
            "children_sync": 8,
            "dayun_sync": 7,
        },
        "bonus": {
            "left_strong_match": 7,
            "right_strong_match": 8,
            "strength_complement": 10,
            "strength_balanced": 10,
            "spouse_he": 10,
            "spouse_tong": 5,
            "spouse_chong": -5,
            "children_he": 7,
            "children_tong": 4,
            "dayun_element_match": 2,
        },
        "clamp": {"min": 40, "max": 99},
    }
}


FIVE_ELEMENTS = ["木", "火", "土", "金", "水"]
TRIGRAMS = ["乾", "兑", "离", "震", "巽", "坎", "艮", "坤"]
TRIGRAM_WUXING = {"乾": "金", "兑": "金", "离": "火", "震": "木", "巽": "木", "坎": "水", "艮": "土", "坤": "土"}
TAROT_CARDS = [
    "愚者",
    "魔术师",
    "女祭司",
    "皇后",
    "皇帝",
    "教皇",
    "恋人",
    "战车",
    "力量",
    "隐者",
    "命运之轮",
    "正义",
    "倒吊人",
    "死神",
    "节制",
    "恶魔",
    "高塔",
    "星星",
    "月亮",
    "太阳",
    "审判",
    "世界",
]

ACTIVITY_MAP = {
    "嫁娶": (["周末", "偶数日"], ["冲日", "破日"]),
    "开业": (["工作日", "三合"], ["月破", "岁破"]),
    "出行": (["晴朗", "吉神"], ["大耗", "天刑"]),
    "签约": (["天德", "月德"], ["劫煞", "灾煞"]),
}

BASE_DIR = Path(__file__).resolve().parent
CLASSICS_DIR = BASE_DIR / "data" / "classics"
ICHING_64_PATH = CLASSICS_DIR / "iching_64.json"
ZIWEI_STARS_PATH = CLASSICS_DIR / "ziwei_stars.json"

GAN_WUXING = {
    "甲": "木",
    "乙": "木",
    "丙": "火",
    "丁": "火",
    "戊": "土",
    "己": "土",
    "庚": "金",
    "辛": "金",
    "壬": "水",
    "癸": "水",
}

ZHI_WUXING = {
    "子": "水",
    "丑": "土",
    "寅": "木",
    "卯": "木",
    "辰": "土",
    "巳": "火",
    "午": "火",
    "未": "土",
    "申": "金",
    "酉": "金",
    "戌": "土",
    "亥": "水",
}

WUXING_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
WUXING_KE = {"木": "土", "火": "金", "土": "水", "金": "木", "水": "火"}
TRIGRAM_GUACI = {
    "乾": "元亨利贞。君子以自强不息。",
    "坤": "元亨，利牝马之贞。君子以厚德载物。",
    "震": "震来虩虩，后笑言哑哑。",
    "巽": "小亨，利有攸往，利见大人。",
    "坎": "习坎，有孚，维心亨，行有尚。",
    "离": "利贞，亨。畜牝牛，吉。",
    "艮": "艮其背，不获其身；行其庭，不见其人。",
    "兑": "亨，利贞。和而悦。",
}

TRIGRAM_BIN_TO_INDEX = {
    "111": 0,  # 乾
    "110": 1,  # 兑
    "101": 2,  # 离
    "100": 3,  # 震
    "011": 4,  # 巽
    "010": 5,  # 坎
    "001": 6,  # 艮
    "000": 7,  # 坤
}

KING_WEN_LOOKUP = [
    [1, 43, 14, 34, 9, 5, 26, 11],
    [10, 58, 38, 54, 61, 60, 41, 19],
    [13, 49, 30, 55, 37, 63, 22, 36],
    [25, 17, 21, 51, 42, 3, 27, 24],
    [44, 28, 50, 32, 57, 48, 18, 46],
    [6, 47, 64, 40, 59, 29, 4, 7],
    [33, 31, 56, 62, 53, 39, 52, 15],
    [12, 45, 35, 16, 20, 8, 23, 2],
]

ZIWEI_PALACES = [
    "命宫",
    "兄弟宫",
    "夫妻宫",
    "子女宫",
    "财帛宫",
    "疾厄宫",
    "迁移宫",
    "交友宫",
    "事业宫",
    "田宅宫",
    "福德宫",
    "父母宫",
]

ZIWEI_STAR_LIBRARY = {
    "紫微": {"五行": "土", "亮度": "帝星", "吉凶": "吉", "象义": "统御、格局、主导力"},
    "天机": {"五行": "木", "亮度": "辅星", "吉凶": "中吉", "象义": "谋略、变化、学习"},
    "太阳": {"五行": "火", "亮度": "主星", "吉凶": "吉", "象义": "外放、名誉、执行"},
    "武曲": {"五行": "金", "亮度": "主星", "吉凶": "中吉", "象义": "财务、决断、纪律"},
    "天同": {"五行": "水", "亮度": "主星", "吉凶": "中", "象义": "福气、调和、享受"},
    "廉贞": {"五行": "火", "亮度": "主星", "吉凶": "中", "象义": "边界、规则、欲望"},
    "天府": {"五行": "土", "亮度": "库星", "吉凶": "吉", "象义": "资源、稳定、守成"},
    "太阴": {"五行": "水", "亮度": "主星", "吉凶": "中吉", "象义": "内在、财库、情绪"},
    "贪狼": {"五行": "木", "亮度": "主星", "吉凶": "中", "象义": "人际、欲望、开创"},
    "巨门": {"五行": "水", "亮度": "主星", "吉凶": "中", "象义": "言语、争议、辨析"},
    "天相": {"五行": "水", "亮度": "辅星", "吉凶": "中吉", "象义": "协作、审慎、公允"},
    "天梁": {"五行": "土", "亮度": "主星", "吉凶": "吉", "象义": "庇护、原则、长辈缘"},
    "七杀": {"五行": "金", "亮度": "将星", "吉凶": "偏凶", "象义": "突破、风险、效率"},
    "破军": {"五行": "水", "亮度": "将星", "吉凶": "偏凶", "象义": "破旧立新、重组"},
}

FOUR_TRANSFORMATIONS = {
    "甲": {"禄": "廉贞", "权": "破军", "科": "武曲", "忌": "太阳"},
    "乙": {"禄": "天机", "权": "天梁", "科": "紫微", "忌": "太阴"},
    "丙": {"禄": "天同", "权": "天机", "科": "文昌", "忌": "廉贞"},
    "丁": {"禄": "太阴", "权": "天同", "科": "天机", "忌": "巨门"},
    "戊": {"禄": "贪狼", "权": "太阴", "科": "右弼", "忌": "天机"},
    "己": {"禄": "武曲", "权": "贪狼", "科": "天梁", "忌": "文曲"},
    "庚": {"禄": "太阳", "权": "武曲", "科": "太阴", "忌": "天同"},
    "辛": {"禄": "巨门", "权": "太阳", "科": "文曲", "忌": "文昌"},
    "壬": {"禄": "天梁", "权": "紫微", "科": "左辅", "忌": "武曲"},
    "癸": {"禄": "破军", "权": "巨门", "科": "太阴", "忌": "贪狼"},
}

ZIWEI_SCHOOL_OFFSETS: Dict[str, Dict[str, int]] = {
    # 三合派口径（当前默认）
    "sanhe": {
        "紫微": 0, "天机": 1, "太阳": 3, "武曲": 4, "天同": 5, "廉贞": 8,
        "天府": 6, "太阴": 7, "贪狼": 9, "巨门": 10, "天相": 11, "天梁": 2,
        "七杀": 5, "破军": 9,
    },
    # 飞星派（简化差异版，用于流派切换）
    "feixing": {
        "紫微": 0, "天机": 2, "太阳": 4, "武曲": 5, "天同": 6, "廉贞": 9,
        "天府": 7, "太阴": 8, "贪狼": 10, "巨门": 11, "天相": 1, "天梁": 3,
        "七杀": 6, "破军": 10,
    },
}

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

AI_KNOWLEDGE = {
    "八字分析命盘解析": [
        "以五行强弱观察个人能量结构，强调平衡而非绝对吉凶。",
        "解释优先采用可行动建议，避免宿命化表达。",
        "分析重点：性格驱动力、压力模式、成长策略。",
    ],
    "每日运势": [
        "日运属于短期趋势观察，适合安排事务优先级。",
        "建议关注情绪稳定、沟通时机与执行节奏。",
    ],
    "合婚分析": [
        "关系分析以沟通模式、边界感、共同目标为核心。",
        "输出需兼顾优势与风险，不做绝对结论。",
    ],
    "事业合作分析": [
        "合作评估重点：决策风格、分工边界、风险共担机制。",
        "建议提供可执行的协作规则。",
    ],
    "婆媳关系分析": [
        "代际关系重点在期待差异与边界协商。",
        "建议使用低冲突表达与周期复盘。",
    ],
    "知己分析": [
        "朋友关系看重价值观匹配与支持方式互补。",
        "建议明确长期互动机制。",
    ],
    "八字关系图谱": [
        "图谱用于识别关系强弱与协作优先级。",
        "适合做关系盘点与行动排序。",
    ],
    "梅花易数每日决策": [
        "决策建议应遵循先验证假设、后投入资源。",
        "强调可逆决策与分步推进。",
    ],
    "六爻占卜": [
        "六爻关注变化节点与关键转折位。",
        "建议输出应包含备选方案。",
    ],
    "塔罗占卜": [
        "塔罗可作为情境反思工具，不替代现实证据。",
        "建议先处理可控问题，再处理情绪波动。",
    ],
    "紫微斗数排盘": [
        "紫微排盘用于结构化观察宫位联动。",
        "重点关注事业、财帛、福德三宫平衡。",
    ],
    "紫微合婚": [
        "双盘对照重在长期相处模式与资源协同。",
        "建议输出应包含现实沟通动作。",
    ],
    "黄历查询": [
        "黄历用于传统文化参考，不能替代现实约束。",
        "建议结合日程、法律与客观条件决策。",
    ],
}


def _load_iching_64() -> Dict[str, Dict[str, Any]]:
    sig = _file_signature(ICHING_64_PATH)
    return _load_iching_64_cached(sig)


@lru_cache(maxsize=32)
def _load_iching_64_cached(sig: str) -> Dict[str, Dict[str, Any]]:
    if not ICHING_64_PATH.exists():
        return {}
    return json.loads(ICHING_64_PATH.read_text(encoding="utf-8"))


def _load_ziwei_stars() -> Dict[str, Dict[str, str]]:
    sig = _file_signature(ZIWEI_STARS_PATH)
    return _load_ziwei_stars_cached(sig)


@lru_cache(maxsize=32)
def _load_ziwei_stars_cached(sig: str) -> Dict[str, Dict[str, str]]:
    if not ZIWEI_STARS_PATH.exists():
        return ZIWEI_STAR_LIBRARY
    return json.loads(ZIWEI_STARS_PATH.read_text(encoding="utf-8"))


def _hex_number_from_lines(coin_sums: List[int]) -> int:
    yang_yin_bits = ["1" if s in (7, 9) else "0" for s in coin_sums]  # 自下而上
    lower_bin = "".join(yang_yin_bits[:3])  # 下卦
    upper_bin = "".join(yang_yin_bits[3:])  # 上卦
    lower_index = TRIGRAM_BIN_TO_INDEX[lower_bin]
    upper_index = TRIGRAM_BIN_TO_INDEX[upper_bin]
    return KING_WEN_LOOKUP[lower_index][upper_index]


def _changed_coin_sums(coin_sums: List[int]) -> List[int]:
    changed: List[int] = []
    for s in coin_sums:
        if s == 6:
            changed.append(7)
        elif s == 9:
            changed.append(8)
        else:
            changed.append(s)
    return changed


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _file_signature(path: Path) -> str:
    if not path.exists():
        return "missing"
    stat = path.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


AI_ENV_KEYS = (
    "LLM_PROTOCOL",
    "LLM_BASE_URL_OPENAI",
    "LLM_BASE_URL",
    "LLM_BASE_URL_ANTHROPIC",
    "LLM_API_KEY_OPENAI",
    "LLM_API_KEY_ANTHROPIC",
    "LLM_API_KEY",
    "LLM_MODEL_OPENAI",
    "LLM_MODEL_ANTHROPIC",
    "LLM_MODEL",
    "LLM_PROVIDER",
    "LLM_DEEP_THINKING",
    "LLM_REASONING_EFFORT",
    "LLM_THINKING_BUDGET_TOKENS",
    "LLM_MAX_TOKENS",
    "LLM_ANTHROPIC_VERSION",
    "LLM_TIMEOUT_SEC",
)


def _ai_settings() -> Dict[str, str]:
    env_sig = tuple(_env(k, "") for k in AI_ENV_KEYS)
    return _ai_settings_cached(env_sig)


@lru_cache(maxsize=16)
def _ai_settings_cached(env_sig: Tuple[str, ...]) -> Dict[str, str]:
    values = dict(zip(AI_ENV_KEYS, env_sig))
    protocol = values["LLM_PROTOCOL"].lower() or "openai"
    if protocol not in {"openai", "anthropic"}:
        protocol = "openai"
    base_url_openai = values["LLM_BASE_URL_OPENAI"] or values["LLM_BASE_URL"] or "https://coding.dashscope.aliyuncs.com/v1"
    base_url_anthropic = values["LLM_BASE_URL_ANTHROPIC"] or "https://coding.dashscope.aliyuncs.com/apps/anthropic"
    api_key_openai = values["LLM_API_KEY_OPENAI"] or values["LLM_API_KEY"]
    api_key_anthropic = values["LLM_API_KEY_ANTHROPIC"] or values["LLM_API_KEY"]
    model_openai = values["LLM_MODEL_OPENAI"] or values["LLM_MODEL"] or "qwen3.5-plus"
    model_anthropic = values["LLM_MODEL_ANTHROPIC"] or values["LLM_MODEL"] or "qwen3.5-plus"
    deep_thinking = (values["LLM_DEEP_THINKING"] or "false").lower() in {"1", "true", "yes", "on"}
    reasoning_effort = (values["LLM_REASONING_EFFORT"] or "medium").lower()
    if reasoning_effort not in {"low", "medium", "high"}:
        reasoning_effort = "medium"
    return {
        "provider": values["LLM_PROVIDER"] or "dashscope",
        "protocol": protocol,
        "base_url_openai": base_url_openai,
        "base_url_anthropic": base_url_anthropic,
        "api_key_openai": api_key_openai,
        "api_key_anthropic": api_key_anthropic,
        "model_openai": model_openai,
        "model_anthropic": model_anthropic,
        "deep_thinking": "true" if deep_thinking else "false",
        "reasoning_effort": reasoning_effort,
        "thinking_budget_tokens": values["LLM_THINKING_BUDGET_TOKENS"] or "1024",
        "max_tokens": values["LLM_MAX_TOKENS"] or "1024",
        "anthropic_version": values["LLM_ANTHROPIC_VERSION"] or "2023-06-01",
        "timeout_sec": values["LLM_TIMEOUT_SEC"] or "120",
    }


def _seed_from_text(text: str) -> int:
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def _rng(*parts: str) -> random.Random:
    key = "|".join(parts)
    return random.Random(_seed_from_text(key))


def _secure_rng() -> random.Random:
    # 使用系统级熵源，避免可预测种子导致的推算风险
    sys_rand = random.SystemRandom()
    _ = secrets.token_bytes(8)  # force entropy read path
    return sys_rand


def _element_scores(name: str, birthday: str, birth_time: str) -> Dict[str, int]:
    rnd = _rng(name, birthday, birth_time, "five-elements")
    raw = [rnd.randint(30, 95) for _ in range(5)]
    total = sum(raw)
    scores = [round(v * 100 / total) for v in raw]
    diff = 100 - sum(scores)
    scores[0] += diff
    return {k: v for k, v in zip(FIVE_ELEMENTS, scores)}


def _pick_strength(scores: Dict[str, int]) -> Tuple[str, str]:
    strongest = max(scores, key=scores.get)
    weakest = min(scores, key=scores.get)
    return strongest, weakest


def _equation_of_time_minutes(date_obj: dt.date) -> float:
    day_of_year = date_obj.timetuple().tm_yday
    b = 2 * math.pi * (day_of_year - 81) / 364
    return 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)


MIN_TIMEZONE_OFFSET = -12
MAX_TIMEZONE_OFFSET = 14


def _parse_birth_datetime(birthday: str, birth_time: str) -> dt.datetime:
    formats = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S")
    for fmt in formats:
        try:
            return dt.datetime.strptime(f"{birthday} {birth_time}", fmt)
        except ValueError:
            continue
    raise ValueError("出生日期或时间格式非法，需为 birthday=YYYY-MM-DD, birth_time=HH:MM 或 HH:MM:SS")


def _true_solar_datetime(raw_dt: dt.datetime, timezone_offset: int, longitude: float) -> dt.datetime:
    if not (MIN_TIMEZONE_OFFSET <= timezone_offset <= MAX_TIMEZONE_OFFSET):
        raise ValueError(f"timezone_offset 超出范围，应在 [{MIN_TIMEZONE_OFFSET}, {MAX_TIMEZONE_OFFSET}] 内")
    if not (-180.0 <= longitude <= 180.0):
        raise ValueError("longitude 超出范围，应在 [-180, 180] 内")
    dst_shift = _china_dst_shift_hours(raw_dt, timezone_offset, longitude)
    effective_offset = timezone_offset + dst_shift
    standard_meridian = effective_offset * 15
    longitude_correction = (longitude - standard_meridian) * 4
    eot = _equation_of_time_minutes(raw_dt.date())
    return raw_dt + dt.timedelta(minutes=longitude_correction + eot)


def _china_dst_shift_hours(raw_dt: dt.datetime, timezone_offset: int, longitude: float) -> int:
    # 中国历史夏令时（1986-1991），仅对 UTC+8 且中国经度范围生效
    if timezone_offset != 8 or not (73.0 <= longitude <= 135.0):
        return 0
    windows = {
        1986: (dt.datetime(1986, 5, 4, 2, 0), dt.datetime(1986, 9, 14, 2, 0)),
        1987: (dt.datetime(1987, 4, 12, 2, 0), dt.datetime(1987, 9, 13, 2, 0)),
        1988: (dt.datetime(1988, 4, 17, 2, 0), dt.datetime(1988, 9, 11, 2, 0)),
        1989: (dt.datetime(1989, 4, 16, 2, 0), dt.datetime(1989, 9, 17, 2, 0)),
        1990: (dt.datetime(1990, 4, 15, 2, 0), dt.datetime(1990, 9, 16, 2, 0)),
        1991: (dt.datetime(1991, 4, 14, 2, 0), dt.datetime(1991, 9, 15, 2, 0)),
    }
    period = windows.get(raw_dt.year)
    if not period:
        return 0
    start, end = period
    return 1 if start <= raw_dt < end else 0


def _inverse_map(mapping: Dict[str, str]) -> Dict[str, str]:
    return {v: k for k, v in mapping.items()}


WUXING_SHENG_INV = _inverse_map(WUXING_SHENG)
WUXING_KE_INV = _inverse_map(WUXING_KE)


def _is_generating(e1: str, e2: str) -> bool:
    gen_map = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
    return gen_map.get(e1) == e2

def _is_overcoming(e1: str, e2: str) -> bool:
    ovr_map = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
    return ovr_map.get(e1) == e2


def _cycle_moving_line(value: int) -> int:
    """梅花动爻循环规则：6→7, 7→8, 8→9, 9→6。"""
    cycle_change = {6: 7, 7: 8, 8: 9, 9: 6}
    return cycle_change.get(value, value)


def _safe_lunar_month_features(lunar: Any) -> Tuple[int, bool, int]:
    raw_month = int(lunar.getMonth())
    lunar_month = abs(raw_month)
    is_leap_month = raw_month < 0
    month_size = 30 if lunar_month % 2 else 29
    get_days = getattr(lunar, "getDayCountOfMonth", None)
    if callable(get_days):
        try:
            month_size = int(get_days(raw_month))
        except Exception:
            pass
    return lunar_month, is_leap_month, month_size


def _resolve_four_transformations(ec: Any, scope: str = "year") -> Dict[str, Any]:
    year_gan = ec.getYearGan()
    result = {"year_gan": year_gan, **FOUR_TRANSFORMATIONS.get(year_gan, FOUR_TRANSFORMATIONS["甲"])}
    if scope == "full":
        month_gan = ec.getMonthGan()
        day_gan = ec.getDayGan()
        result["month_gan"] = month_gan
        result["day_gan"] = day_gan
        result["month_transformations"] = FOUR_TRANSFORMATIONS.get(month_gan, FOUR_TRANSFORMATIONS["甲"])
        result["day_transformations"] = FOUR_TRANSFORMATIONS.get(day_gan, FOUR_TRANSFORMATIONS["甲"])
    return result

def _compute_bazi_strength(ec: Any) -> Tuple[Dict[str, int], str, str, str]:
    stems = [ec.getYearGan(), ec.getMonthGan(), ec.getDayGan(), ec.getTimeGan()]
    branches = [ec.getYearZhi(), ec.getMonthZhi(), ec.getDayZhi(), ec.getTimeZhi()]
    scores = {e: 0 for e in FIVE_ELEMENTS}
    for g in stems:
        scores[GAN_WUXING.get(g, "土")] += 2
    for z in branches:
        scores[ZHI_WUXING.get(z, "土")] += 1

    day_master_element = GAN_WUXING.get(ec.getDayGan(), "土")
    generate_day_master = WUXING_SHENG_INV[day_master_element]
    control_day_master = WUXING_KE_INV[day_master_element]
    leak_day_master = WUXING_SHENG[day_master_element]
    consumed_by_day_master = WUXING_KE[day_master_element]

    support_score = scores[day_master_element] + scores[generate_day_master]
    drain_score = scores[control_day_master] + scores[leak_day_master] + scores[consumed_by_day_master]
    strength = "身强" if support_score >= drain_score else "身弱"
    if strength == "身强":
        yong_shen = leak_day_master if scores[leak_day_master] <= scores[control_day_master] else control_day_master
        ji_shen = day_master_element
    else:
        yong_shen = generate_day_master if scores[generate_day_master] >= scores[day_master_element] else day_master_element
        ji_shen = control_day_master
    return scores, strength, yong_shen, ji_shen


def bazi_analysis(
    name: str,
    birthday: str,
    birth_time: str,
    gender: str,
    timezone_offset: int = 8,
    longitude: float = 120.0,
) -> Dict:
    logger.info("bazi_analysis start name=%s birthday=%s", name, birthday)
    raw_dt = _parse_birth_datetime(birthday, birth_time)
    true_dt = _true_solar_datetime(raw_dt, timezone_offset, longitude)
    solar = Solar.fromYmdHms(true_dt.year, true_dt.month, true_dt.day, true_dt.hour, true_dt.minute, true_dt.second)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    prev_jie = lunar.getPrevJieQi(True)
    next_jie = lunar.getNextJieQi(True)

    scores, strength, yong_shen, ji_shen = _compute_bazi_strength(ec)
    strongest, weakest = _pick_strength(scores)

    pillars = {
        "year": {"gan_zhi": ec.getYear(), "na_yin": ec.getYearNaYin(), "shi_shen_gan": ec.getYearShiShenGan(), "shi_shen_zhi": ec.getYearShiShenZhi()},
        "month": {"gan_zhi": ec.getMonth(), "na_yin": ec.getMonthNaYin(), "shi_shen_gan": ec.getMonthShiShenGan(), "shi_shen_zhi": ec.getMonthShiShenZhi()},
        "day": {"gan_zhi": ec.getDay(), "na_yin": ec.getDayNaYin(), "shi_shen_gan": ec.getDayShiShenGan(), "shi_shen_zhi": ec.getDayShiShenZhi()},
        "time": {"gan_zhi": ec.getTime(), "na_yin": ec.getTimeNaYin(), "shi_shen_gan": ec.getTimeShiShenGan(), "shi_shen_zhi": ec.getTimeShiShenZhi()},
    }

    return {
        "module": "八字分析命盘解析",
        "input": {
            "name": name,
            "gender": gender,
            "calendar": "solar",
            "birthday": birthday,
            "birth_time": birth_time,
            "timezone_offset": timezone_offset,
            "longitude": longitude,
        },
        "time_correction": {
            "raw_local_time": raw_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "true_solar_time": true_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "equation_of_time_minutes": round(_equation_of_time_minutes(raw_dt.date()), 2),
            "china_dst_applied": _china_dst_shift_hours(raw_dt, timezone_offset, longitude) == 1,
        },
        "solar_lunar": {
            "solar": solar.toYmdHms(),
            "lunar": f"{lunar.getYearInChinese()}年{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}",
            "prev_jieqi": {"name": prev_jie.getName(), "time": prev_jie.getSolar().toYmdHms()},
            "next_jieqi": {"name": next_jie.getName(), "time": next_jie.getSolar().toYmdHms()},
        },
        "pillars": pillars,
        "ten_gods": {
            "year_gan": ec.getYearShiShenGan(),
            "month_gan": ec.getMonthShiShenGan(),
            "day_gan": ec.getDayShiShenGan(),
            "time_gan": ec.getTimeShiShenGan(),
        },
        "na_yin": {
            "year": ec.getYearNaYin(),
            "month": ec.getMonthNaYin(),
            "day": ec.getDayNaYin(),
            "time": ec.getTimeNaYin(),
        },
        "wu_xing_distribution": scores,
        "structure": {
            "day_master": ec.getDayGan(),
            "day_master_element": GAN_WUXING.get(ec.getDayGan(), "土"),
            "strength": strength,
            "strongest_element": strongest,
            "weakest_element": weakest,
            "yong_shen": yong_shen,
            "ji_shen": ji_shen,
        },
    }


def daily_fortune(name: str, gender: str, birthday: str, birth_time: str, date: str) -> Dict:
    logger.info("daily_fortune start name=%s date=%s", name, date)
    raw_dt = _parse_birth_datetime(birthday, birth_time)
    solar = Solar.fromYmdHms(raw_dt.year, raw_dt.month, raw_dt.day, raw_dt.hour, raw_dt.minute, raw_dt.second)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()

    scores, strength, yong_shen, ji_shen = _compute_bazi_strength(ec)

    target_dt = dt.datetime.strptime(date, "%Y-%m-%d")
    target_solar = Solar.fromYmdHms(target_dt.year, target_dt.month, target_dt.day, 12, 0, 0)
    target_lunar = target_solar.getLunar()
    target_ec = target_lunar.getEightChar()

    liu_nian = target_ec.getYear()
    liu_yue = target_ec.getMonth()
    liu_ri = target_ec.getDay()

    gender_code = 1 if gender == "男" else 0
    da_yuns = ec.getYun(gender_code).getDaYun()
    current_dy = next((dy for dy in reversed(da_yuns) if dy.getStartYear() <= target_dt.year), da_yuns[0])
    da_yun = current_dy.getGanZhi()

    elements_in_period = []
    for gz in [da_yun, liu_nian, liu_yue, liu_ri]:
        if len(gz) == 2:
            elements_in_period.append(GAN_WUXING.get(gz[0], ""))
            elements_in_period.append(ZHI_WUXING.get(gz[1], ""))

    yong_count = sum(1 for e in elements_in_period if e in yong_shen)
    ji_count = sum(1 for e in elements_in_period if e in ji_shen)

    base_score = 70
    net_score = base_score + (yong_count - ji_count) * 8
    net_score = max(40, min(99, net_score))

    def pseudo_random(seed_str: str, min_v: int, max_v: int) -> int:
        h = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)
        return min_v + (h % (max_v - min_v + 1))

    overall = net_score
    love = max(40, min(99, overall + pseudo_random(f"{name}{date}love", -10, 10)))
    wealth = max(40, min(99, overall + pseudo_random(f"{name}{date}wealth", -10, 10)))
    work = max(40, min(99, overall + pseudo_random(f"{name}{date}work", -10, 10)))
    health = max(40, min(99, overall + pseudo_random(f"{name}{date}health", -10, 10)))

    best_hour_start = pseudo_random(f"{name}{date}hour1", 7, 11)
    best_hour_end = pseudo_random(f"{name}{date}hour2", 13, 21)
    best_hour = f"{best_hour_start}:00-{best_hour_end}:00"

    LUCKY_COLORS = {"木": "青色/绿色", "火": "红色/紫色", "土": "黄色/棕色", "金": "白色/金色", "水": "黑色/蓝色"}
    LUCKY_NUMBERS = {"木": "3, 8", "火": "2, 7", "土": "5, 0", "金": "4, 9", "水": "1, 6"}

    lucky_colors = list(set([LUCKY_COLORS.get(e, "") for e in yong_shen if e in LUCKY_COLORS]))
    lucky_numbers = list(set([LUCKY_NUMBERS.get(e, "") for e in yong_shen if e in LUCKY_NUMBERS]))

    if yong_count > ji_count:
        tips = ["今日五行有利，宜积极推进重要事务。", "把握贵人运，可多沟通协作。"]
    else:
        tips = ["今日五行有所克制，宜求稳守成。", "注意情绪管理，避免冲动决策。"]

    return {
        "module": "每日运势",
        "date": date,
        "four_pillars": {
            "da_yun": da_yun,
            "liu_nian": liu_nian,
            "liu_yue": liu_yue,
            "liu_ri": liu_ri,
        },
        "bazi_basis": {
            "strength": strength,
            "yong_shen": yong_shen,
            "ji_shen": ji_shen,
        },
        "scores": {
            "overall": overall,
            "love": love,
            "wealth": wealth,
            "work": work,
            "health": health,
        },
        "lucky_elements": {
            "colors": lucky_colors,
            "numbers": lucky_numbers,
        },
        "best_hour": best_hour,
        "tips": tips,
    }


def compatibility(left: Dict[str, str], right: Dict[str, str], scene: str) -> Dict:
    score_cfg = REL_SCORE_CONFIG.get(scene, REL_SCORE_CONFIG["default"])
    weights = score_cfg["weights"]
    base = score_cfg["base"]
    bonus = score_cfg["bonus"]
    clamp_min = int(score_cfg["clamp"]["min"])
    clamp_max = int(score_cfg["clamp"]["max"])

    def _get_bazi_info(p: Dict[str, str]):
        raw_dt = _parse_birth_datetime(p["birthday"], p["birth_time"])
        tz = int(p.get("timezone_offset", 8) or 8)
        lon = float(p.get("longitude", 120.0) or 120.0)
        true_dt = _true_solar_datetime(raw_dt, tz, lon)
        solar = Solar.fromYmdHms(true_dt.year, true_dt.month, true_dt.day, true_dt.hour, true_dt.minute, true_dt.second)
        lunar = solar.getLunar()
        ec = lunar.getEightChar()
        scores, strength, yong_shen, ji_shen = _compute_bazi_strength(ec)
        
        # Determine Da Yun direction
        gender_code = 1 if p.get("gender", "男") == "男" else 0
        da_yuns = ec.getYun(gender_code).getDaYun()
        
        return {
            "ec": ec,
            "scores": scores,
            "strength": strength,
            "yong_shen": yong_shen,
            "ji_shen": ji_shen,
            "da_yuns": da_yuns,
            "day_gan": ec.getDayGan(),
            "day_zhi": ec.getDayZhi(),
            "time_zhi": ec.getTimeZhi()
        }

    l_info = _get_bazi_info(left)
    r_info = _get_bazi_info(right)

    # 1. 五行互补度
    # How much of left's abundant elements match right's Yong Shen, and vice versa
    l_strongest = max(l_info["scores"], key=l_info["scores"].get)
    r_strongest = max(r_info["scores"], key=r_info["scores"].get)
    
    comp_score = int(base["complementarity"])
    if l_strongest in r_info["yong_shen"]:
        comp_score += int(bonus["left_strong_match"])
    if r_strongest in l_info["yong_shen"]:
        comp_score += int(bonus["right_strong_match"])
    comp_score = max(0, min(int(weights["complementarity"]), comp_score))
    
    # 2. 日主强弱
    # Usually, strong matches weak, or both balanced.
    dm_score = int(base["day_master"])
    if l_info["strength"] != r_info["strength"]:
        dm_score += int(bonus["strength_complement"])  # strong + weak
    elif l_info["strength"] == "中和":
        dm_score += int(bonus["strength_balanced"])  # both balanced
    dm_score = max(0, min(int(weights["day_master"]), dm_score))
    
    # 3. 配偶宫合冲
    # Spouse palace is Day Zhi (日支)
    he_relations = [("子", "丑"), ("寅", "亥"), ("卯", "戌"), ("辰", "酉"), ("巳", "申"), ("午", "未")]
    chong_relations = [("子", "午"), ("丑", "未"), ("寅", "申"), ("卯", "酉"), ("辰", "戌"), ("巳", "亥")]
    
    l_dz = l_info["day_zhi"]
    r_dz = r_info["day_zhi"]
    
    sp_score = int(base["spouse_palace"])
    if (l_dz, r_dz) in he_relations or (r_dz, l_dz) in he_relations:
        sp_score += int(bonus["spouse_he"])
    elif (l_dz, r_dz) in chong_relations or (r_dz, l_dz) in chong_relations:
        sp_score += int(bonus["spouse_chong"])
    elif l_dz == r_dz:
        sp_score += int(bonus["spouse_tong"])
    sp_score = max(0, min(int(weights["spouse_palace"]), sp_score))
        
    # 4. 子女星同步性
    # Time Zhi (时支) represents children palace
    l_tz = l_info["time_zhi"]
    r_tz = r_info["time_zhi"]
    child_score = int(base["children_sync"])
    if (l_tz, r_tz) in he_relations or (r_tz, l_tz) in he_relations:
        child_score += int(bonus["children_he"])
    elif l_tz == r_tz:
        child_score += int(bonus["children_tong"])
    child_score = max(0, min(int(weights["children_sync"]), child_score))
        
    # 5. 大运同步性
    # Compare the element of the next few Da Yuns
    l_dy = l_info["da_yuns"]
    r_dy = r_info["da_yuns"]
    
    dy_sync_score = int(base["dayun_sync"])
    # Simplified sync check: check if the sequence of branches have similar elements
    l_dy_branches = [dy.getGanZhi()[1] for dy in l_dy[1:4] if len(dy.getGanZhi()) == 2]
    r_dy_branches = [dy.getGanZhi()[1] for dy in r_dy[1:4] if len(dy.getGanZhi()) == 2]
    
    match_count = sum(1 for i in range(min(len(l_dy_branches), len(r_dy_branches))) 
                      if ZHI_WUXING.get(l_dy_branches[i]) == ZHI_WUXING.get(r_dy_branches[i]))
    dy_sync_score += match_count * int(bonus["dayun_element_match"])
    dy_sync_score = max(0, min(int(weights["dayun_sync"]), dy_sync_score))

    total_score = comp_score + dm_score + sp_score + child_score + dy_sync_score
    total_score = max(clamp_min, min(clamp_max, total_score))

    strengths = []
    risks = []
    
    if comp_score > 20:
        strengths.append(f"五行互补度极高，{left['name']}的旺势能极大地补足{right['name']}的需用。")
    if dm_score > 15:
        strengths.append("日主强弱搭配合理，一方主导时另一方能提供稳定支持。")
    if sp_score > 15:
        strengths.append("配偶宫相合，两人在深层价值观与家庭观念上高度一致。")
    elif sp_score < 10:
        risks.append("配偶宫存在相冲，日常相处中容易因生活琐事产生摩擦。")
        
    if child_score > 10:
        strengths.append("子女宫信息同步，在生育观念及晚年规划上步调一致。")
    if dy_sync_score > 10:
        strengths.append("未来大运走向趋同，能共同面对人生起伏，互相扶持。")
    elif dy_sync_score < 8:
        risks.append("未来大运节奏存在差异，一方顺利时另一方可能面临挑战，需更多包容。")
        
    if not risks:
        risks.append("在亲密关系中仍需保持独立空间，避免过度依赖。")

    return {
        "module": scene,
        "left": left,
        "right": right,
        "score": total_score,
        "rating": "天作之合" if total_score >= 85 else ("中等契合" if total_score >= 65 else "需要磨合"),
        "dimensions": {
            "complementarity": comp_score,
            "day_master": dm_score,
            "spouse_palace": sp_score,
            "children_sync": child_score,
            "dayun_sync": dy_sync_score
        },
        "scoring_meta": {
            "weights": weights,
            "clamp": {"min": clamp_min, "max": clamp_max},
            "explanation": "分值会按边界裁剪，避免极端样本造成误导性过高/过低结果。",
        },
        "strengths": strengths,
        "risks": risks,
        "suggestion": "建议在日常沟通中，多从对方的角度理解问题。保持长期的包容与支持，是关系长久的基石。",
    }


def _ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        # Windows may not fully support chmod bits; ignore while keeping directory usable.
        logger.debug("Skip chmod for path: %s", path)


def _safe_remove(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        logger.debug("Failed to remove temp file: %s", path)


def _safe_filename(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in value)
    return safe[:64] or "report"


def _run_pdf_subprocess(cmd: List[str], cwd: Path, env: Dict[str, str]) -> None:
    quoted_command = " ".join(shlex.quote(str(part)) for part in cmd)
    try:
        subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError as exc:
        logger.error(
            "PDF export command failed returncode=%s stderr=%s command=%s",
            exc.returncode,
            (exc.stderr or "").strip(),
            quoted_command,
        )
        raise PdfExportError(f"PDF 导出失败: {quoted_command}") from exc
    except OSError as exc:
        logger.error("PDF export command OS error command=%s error=%s", quoted_command, exc)
        raise PdfExportError(f"PDF 导出执行异常: {quoted_command}") from exc


def export_marriage_pdf(raw_data: Dict[str, Any], output_dir: str | None = None) -> str:
    skill_dir_env = _env("MINIMAX_PDF_SKILL_DIR", "")
    skill_dir = Path(skill_dir_env) if skill_dir_env else (Path(tempfile.gettempdir()) / "minimax-pdf")
    try:
        _ensure_private_dir(skill_dir)
    except OSError as exc:
        raise PdfExportError(f"无法初始化 PDF 技能目录: {skill_dir}") from exc

    scripts_dir = skill_dir / "scripts"
    required_scripts = ["palette.py", "cover.py", "render_cover.js", "render_body.py", "merge.py"]
    missing_scripts = [name for name in required_scripts if not (scripts_dir / name).exists()]
    if missing_scripts:
        raise PdfExportError(f"PDF 技能目录缺少脚本: {', '.join(missing_scripts)}")

    final_output_dir = Path(output_dir).expanduser() if output_dir else (Path(tempfile.gettempdir()) / "fatemaster_exports")
    try:
        _ensure_private_dir(final_output_dir)
    except OSError as exc:
        raise PdfExportError(f"无法初始化 PDF 输出目录: {final_output_dir}") from exc

    left_name = str(raw_data.get("left", {}).get("name", "甲方"))
    right_name = str(raw_data.get("right", {}).get("name", "乙方"))
    dims = raw_data.get("dimensions", {})

    content = [
        {"type": "h1", "text": "八字合婚分析报告"},
        {"type": "body", "text": f"**甲方**：{left_name} | **乙方**：{right_name}"},
        {"type": "divider"},
        {"type": "h2", "text": "综合匹配度"},
        {"type": "callout", "text": f"契合度评分：{raw_data.get('score', 0)} / 100 ({raw_data.get('rating', '未评定')})"},
        {"type": "h3", "text": "各维度得分"},
        {"type": "bullet", "text": f"五行互补度：{dims.get('complementarity', 0)} / 30"},
        {"type": "bullet", "text": f"日主强弱：{dims.get('day_master', 0)} / 20"},
        {"type": "bullet", "text": f"配偶宫合冲：{dims.get('spouse_palace', 0)} / 20"},
        {"type": "bullet", "text": f"子女星同步：{dims.get('children_sync', 0)} / 15"},
        {"type": "bullet", "text": f"大运同步性：{dims.get('dayun_sync', 0)} / 15"},
        {"type": "h2", "text": "核心优势"},
        *[{"type": "bullet", "text": s} for s in raw_data.get("strengths", [])],
        {"type": "h2", "text": "潜在挑战"},
        *[{"type": "bullet", "text": r} for r in raw_data.get("risks", [])],
        {"type": "h2", "text": "命理建议"},
        {"type": "body", "text": str(raw_data.get("suggestion", ""))},
    ]

    temp_paths: List[Path] = []
    work_dir = Path(tempfile.mkdtemp(prefix="fatemaster_pdf_"))
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PAGER"] = "cat"
    tmp_output_pdf: Path | None = None

    try:
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8", dir=str(work_dir)) as fp:
            json.dump(content, fp, ensure_ascii=False)
            content_path = Path(fp.name)
            temp_paths.append(content_path)

        with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".pdf", dir=str(work_dir)) as fp:
            tmp_output_pdf = Path(fp.name)
            temp_paths.append(tmp_output_pdf)

        _run_pdf_subprocess(
            [
                sys.executable,
                str(scripts_dir / "palette.py"),
                "--title",
                f"{left_name} & {right_name} 合婚报告",
                "--type",
                "report",
                "--accent",
                "#8A3A2A",
            ],
            cwd=work_dir,
            env=env,
        )
        _run_pdf_subprocess([sys.executable, str(scripts_dir / "cover.py")], cwd=work_dir, env=env)
        _run_pdf_subprocess(
            ["node", str(scripts_dir / "render_cover.js"), "--input", "cover.html", "--out", "cover.pdf"],
            cwd=work_dir,
            env=env,
        )
        _run_pdf_subprocess(
            [sys.executable, str(scripts_dir / "render_body.py"), "--content", content_path.name],
            cwd=work_dir,
            env=env,
        )
        _run_pdf_subprocess(
            [
                sys.executable,
                str(scripts_dir / "merge.py"),
                "--cover",
                "cover.pdf",
                "--body",
                "body.pdf",
                "--out",
                tmp_output_pdf.name,
            ],
            cwd=work_dir,
            env=env,
        )

        final_name = f"合婚报告_{_safe_filename(left_name)}_{_safe_filename(right_name)}_{uuid.uuid4().hex[:8]}.pdf"
        final_path = final_output_dir / final_name
        shutil.move(str(tmp_output_pdf), str(final_path))
        temp_paths = [p for p in temp_paths if p != tmp_output_pdf]
        return str(final_path)
    finally:
        for path in temp_paths:
            _safe_remove(path)
        for filename in ("cover.html", "cover.pdf", "body.pdf", "tokens.json"):
            _safe_remove(work_dir / filename)
        try:
            work_dir.rmdir()
        except OSError:
            pass

def relationship_graph(center_name: str, relations: List[Dict[str, str]]) -> Dict:
    nodes = [{"id": center_name, "type": "self"}]
    edges = []
    for rel in relations:
        rnd = _rng(center_name, rel["name"], rel["relation_type"], "graph")
        score = rnd.randint(55, 95)
        nodes.append({"id": rel["name"], "type": rel["relation_type"]})
        edges.append(
            {
                "from": center_name,
                "to": rel["name"],
                "relation_type": rel["relation_type"],
                "score": score,
                "label": "稳健" if score >= 80 else ("可提升" if score >= 65 else "需经营"),
            }
        )
    return {
        "module": "八字关系图谱",
        "center": center_name,
        "nodes": nodes,
        "edges": edges,
    }


def meihua_decision(question: str, date: str) -> Dict:
    rnd = _secure_rng()
    
    # 梅花易数：上卦、下卦、动爻
    upper_num = rnd.randint(1, 8)
    lower_num = rnd.randint(1, 8)
    moving_idx = rnd.randint(0, 5) # 0 to 5 for line 1 to 6
    
    # 乾1 兑2 离3 震4 巽5 坎6 艮7 坤8
    # 转换为底层阴阳爻：初爻到三爻为下卦，四爻到六爻为上卦
    trigram_map = {
        1: [7, 7, 7], 2: [7, 7, 8], 3: [7, 8, 7], 4: [7, 8, 8],
        5: [8, 7, 7], 6: [8, 7, 8], 7: [8, 8, 7], 8: [8, 8, 8]
    }
    
    base_lines = trigram_map[lower_num] + trigram_map[upper_num]
    primary_coin_sums = list(base_lines)
    changed_coin_sums = list(base_lines)
    changed_coin_sums[moving_idx] = _cycle_moving_line(changed_coin_sums[moving_idx])

    primary_num = _hex_number_from_lines(primary_coin_sums)
    changed_num = _hex_number_from_lines(changed_coin_sums)
    
    # 互卦：由本卦的2,3,4爻为下卦，3,4,5爻为上卦组成 (索引 1,2,3 和 2,3,4)
    hu_lines = [
        7 if primary_coin_sums[1] in (7, 9) else 8,
        7 if primary_coin_sums[2] in (7, 9) else 8,
        7 if primary_coin_sums[3] in (7, 9) else 8,
        7 if primary_coin_sums[2] in (7, 9) else 8,
        7 if primary_coin_sums[3] in (7, 9) else 8,
        7 if primary_coin_sums[4] in (7, 9) else 8,
    ]
    hu_num = _hex_number_from_lines(hu_lines)
    
    # 错卦：本卦的六爻阴阳全变
    cuo_lines = [8 if c in (7, 9) else 7 for c in primary_coin_sums]
    cuo_num = _hex_number_from_lines(cuo_lines)
    
    # 综卦：本卦的六爻颠倒
    zong_lines = [7 if c in (7, 9) else 8 for c in reversed(primary_coin_sums)]
    zong_num = _hex_number_from_lines(zong_lines)
    
    classics = _load_iching_64()
    
    def get_hex_info(num: int) -> Dict:
        c = classics.get(str(num), {})
        texts = c.get("texts", {})
        orig = texts.get("原文", {})
        return {
            "number": num,
            "name": c.get("name", ""),
            "guaci": orig.get("卦辞", ""),
            "texts": texts
        }
    
    primary_info = get_hex_info(primary_num)
    changed_info = get_hex_info(changed_num)
    hu_info = get_hex_info(hu_num)
    cuo_info = get_hex_info(cuo_num)
    zong_info = get_hex_info(zong_num)
    
    # 提取动爻爻辞
    moving_line_text = ""
    orig_yaoci = primary_info["texts"].get("原文", {}).get("爻辞", {})
    if isinstance(orig_yaoci, dict):
        items = list(orig_yaoci.items())
        if 0 <= moving_idx < len(items):
            moving_line_text = f"{items[moving_idx][0]}：{items[moving_idx][1]}"
            
    # 体用分析
    # 动爻所在的卦为用卦，另一个为体卦
    upper_name = TRIGRAMS[upper_num - 1]
    lower_name = TRIGRAMS[lower_num - 1]
    if moving_idx >= 3:
        yong_gua = upper_name
        ti_gua = lower_name
    else:
        yong_gua = lower_name
        ti_gua = upper_name
        
    ti_wx = TRIGRAM_WUXING.get(ti_gua, "")
    yong_wx = TRIGRAM_WUXING.get(yong_gua, "")
    
    # 生克关系
    relation = ""
    if ti_wx and yong_wx:
        if ti_wx == yong_wx:
            relation = f"体用比和（{ti_wx}），吉"
        elif _is_generating(ti_wx, yong_wx): # 体生用
            relation = f"体生用（{ti_wx}生{yong_wx}），泄气、主耗损"
        elif _is_generating(yong_wx, ti_wx): # 用生体
            relation = f"用生体（{yong_wx}生{ti_wx}），进益、大吉"
        elif _is_overcoming(ti_wx, yong_wx): # 体克用
            relation = f"体克用（{ti_wx}克{yong_wx}），可控、费力得财"
        elif _is_overcoming(yong_wx, ti_wx): # 用克体
            relation = f"用克体（{yong_wx}克{ti_wx}），凶、主阻碍"

    # 应期 (简化版，根据用卦决定时间)
    TIMING_MAP = {"乾": "戌亥日/秋季", "兑": "酉日/秋季", "离": "午日/夏季", "震": "卯日/春季", "巽": "辰巳日/春季", "坎": "子日/冬季", "艮": "丑寅日/冬春", "坤": "未申日/夏秋"}
    timing = TIMING_MAP.get(yong_gua, "近期")

    return {
        "module": "梅花易数",
        "question": question,
        "date": date,
        "hexagrams": {
            "primary": primary_info,
            "hu": hu_info,
            "cuo": cuo_info,
            "zong": zong_info,
            "changed": changed_info,
        },
        "moving_line": {
            "index": moving_idx + 1,
            "text": moving_line_text,
        },
        "ti_yong": {
            "ti_gua": ti_gua,
            "ti_wuxing": ti_wx,
            "yong_gua": yong_gua,
            "yong_wuxing": yong_wx,
            "relation": relation,
        },
        "timing": timing,
        "conclusion": f"本卦{primary_info['name']}定起始，变卦{changed_info['name']}看结局。{relation}。应期多在{timing}。",
    }


def liuyao_divine(question: str, date: str) -> Dict:
    if not ICHINGPY_AVAILABLE:
        raise RuntimeError(f"六爻模块依赖 ichingpy 不可用: {ICHINGPY_IMPORT_ERROR}")
    rnd = _secure_rng()
    coin_sums = [rnd.choice([6, 7, 8, 9]) for _ in range(6)]  # 自下而上
    status_map = {
        6: LineStatus.CHANGING_YIN,
        7: LineStatus.STATIC_YANG,
        8: LineStatus.STATIC_YIN,
        9: LineStatus.CHANGING_YANG,
    }
    line_objs = [Line(status=status_map[s]) for s in coin_sums]
    hexagram = Hexagram(inner=Trigram(lines=line_objs[:3]), outer=Trigram(lines=line_objs[3:]))
    SixLinesDivinationEngine().execute(hexagram)
    transformed = hexagram.transformed
    SixLinesDivinationEngine().execute(transformed)

    moving_lines = [idx + 1 for idx, s in enumerate(coin_sums) if s in (6, 9)]

    def _line_desc(v: int) -> str:
        if v == 6:
            return "老阴（动）"
        if v == 7:
            return "少阳（静）"
        if v == 8:
            return "少阴（静）"
        return "老阳（动）"

    lines_detail = []
    for i, line in enumerate(hexagram.interpretation.lines, start=1):
        lines_detail.append(
            {
                "line_no": i,
                "coin_sum": coin_sums[i - 1],
                "line_type": _line_desc(coin_sums[i - 1]),
                "six_relative": line.relative.name if line.relative else None,
                "role": line.role.name if line.role else None,
            }
        )

    primary_num = _hex_number_from_lines(coin_sums)
    changed_num = _hex_number_from_lines(_changed_coin_sums(coin_sums))
    classics = _load_iching_64()
    primary_classic = classics.get(str(primary_num), {})
    changed_classic = classics.get(str(changed_num), {})

    primary_name = f"{hexagram.outer.name}上{hexagram.inner.name}下"
    changed_name = f"{transformed.outer.name}上{transformed.inner.name}下"
    primary_texts = primary_classic.get("texts", {})
    primary_original = primary_texts.get("原文", {})
    changed_texts = changed_classic.get("texts", {})
    changed_original = changed_texts.get("原文", {})

    guaci = str(primary_original.get("卦辞") or primary_classic.get("judgment") or f"{TRIGRAM_GUACI.get(hexagram.inner.name, '')} {TRIGRAM_GUACI.get(hexagram.outer.name, '')}".strip())
    xiang_ci = str(primary_classic.get("image") or "")
    moving_line_texts = []
    primary_lines_map = primary_original.get("爻辞") or primary_classic.get("lines", {})
    if isinstance(primary_lines_map, dict):
        primary_line_items = list(primary_lines_map.items())
    else:
        primary_line_items = []
    for ln in moving_lines:
        text = None
        line_title = None
        if primary_line_items and 1 <= ln <= len(primary_line_items):
            line_title, text = primary_line_items[ln - 1]
        elif isinstance(primary_lines_map, dict):
            text = primary_lines_map.get(str(ln))
        if text:
            moving_line_texts.append({"line_no": ln, "title": line_title, "text": text})

    return {
        "module": "六爻占卜",
        "method": "铜钱法",
        "question": question,
        "date": date,
        "primary_hexagram": {
            "number": primary_num,
            "name": primary_name,
            "classic_name": primary_classic.get("name") or primary_classic.get("chinese_name", ""),
            "inner_trigram": hexagram.inner.name,
            "outer_trigram": hexagram.outer.name,
            "guaci": guaci,
            "xiang_ci": xiang_ci,
            "texts": primary_texts,
        },
        "changed_hexagram": {
            "number": changed_num,
            "name": changed_name,
            "classic_name": changed_classic.get("name") or changed_classic.get("chinese_name", ""),
            "inner_trigram": transformed.inner.name,
            "outer_trigram": transformed.outer.name,
            "guaci": changed_original.get("卦辞") or changed_classic.get("judgment", ""),
            "xiang_ci": changed_classic.get("image", ""),
            "texts": changed_texts,
        },
        "moving_lines": moving_lines,
        "moving_line_texts": moving_line_texts,
        "lines": lines_detail,
        "interpretation": {
            "core": "先看本卦定主势，再以动爻判转机，最后参考之卦看结果落点。",
            "decision_template": [
                "若动爻集中于下三爻，先处理内部变量再外推。",
                "若动爻集中于上三爻，外部环境变化更快，宜保留弹性。",
                "若世爻受克，先稳心态与资源；若应爻得生，可主动沟通推进。",
            ],
        },
    }


def _normalize_tarot_name(name: str) -> str:
    raw = str(name).split("(", 1)[0].strip()
    aliases = {"隐士": "隐者"}
    return aliases.get(raw, raw)


def _load_tarot_cards() -> List[Dict]:
    p = Path("data/classics/tarot_major.json")
    if not p.exists():
        return []
    try:
        raw_cards = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    by_name: Dict[str, Dict[str, Any]] = {}
    for item in raw_cards:
        cname = _normalize_tarot_name(item.get("name", ""))
        if cname:
            by_name[cname] = item
    if set(by_name.keys()) != set(TAROT_CARDS):
        logger.warning("tarot_major.json 与标准22张大牌不一致，fallback 到常量牌库")
        return []
    ordered_cards = []
    for idx, cname in enumerate(TAROT_CARDS):
        card = dict(by_name[cname])
        card["id"] = idx
        card["name_cn"] = cname
        ordered_cards.append(card)
    return ordered_cards

def tarot_divine(question: str, date: str) -> Dict:
    rnd = _secure_rng()
    cards_db = _load_tarot_cards()
    if not cards_db:
        # Fallback if DB missing
        selected_names = rnd.sample(TAROT_CARDS, 3)
        selected = [{"name": n, "upright": {}, "reversed": {}} for n in selected_names]
    else:
        selected = rnd.sample(cards_db, 3)

    positions = ["过去", "现在", "未来"]
    cards = []
    for pos, card_data in zip(positions, selected):
        is_reversed = rnd.choice([True, False])
        state = "reversed" if is_reversed else "upright"
        meaning_data = card_data.get(state, {})
        
        cards.append(
            {
                "position": pos,
                "card": card_data.get("name_cn") or _normalize_tarot_name(card_data.get("name", "")),
                "is_reversed": is_reversed,
                "state_name": "逆位" if is_reversed else "正位",
                "keywords": meaning_data.get("keywords", ""),
                "meaning": meaning_data.get("meaning", ""),
                "love": meaning_data.get("love", ""),
                "career": meaning_data.get("career", ""),
                "wealth": meaning_data.get("wealth", ""),
                "health": meaning_data.get("health", ""),
            }
        )
        
    return {
        "module": "塔罗占卜",
        "question": question,
        "date": date,
        "cards": cards,
        "summary": "结合三张牌的指引，审视过去的影响，把握当下的行动，迎接未来的变化。",
    }


def ziwei_chart(
    name: str,
    birthday: str,
    birth_time: str,
    school: str = "sanhe",
    transform_scope: str = "year",
    timezone_offset: int = 8,
    longitude: float = 120.0,
) -> Dict:
    solar_dt = _parse_birth_datetime(birthday, birth_time)
    true_dt = _true_solar_datetime(solar_dt, timezone_offset, longitude)
    solar = Solar.fromYmdHms(true_dt.year, true_dt.month, true_dt.day, true_dt.hour, true_dt.minute, true_dt.second)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()

    school_key = school if school in ZIWEI_SCHOOL_OFFSETS else "sanhe"
    scope_key = transform_scope if transform_scope in {"year", "full"} else "year"

    lunar_month, is_leap_month, month_size = _safe_lunar_month_features(lunar)
    lunar_day = lunar.getDay()
    hour_zhi = ec.getTimeZhi()
    hour_index = "子丑寅卯辰巳午未申酉戌亥".index(hour_zhi)
    ming_idx = (lunar_month + hour_index - 2) % 12
    shen_idx = (lunar_month + hour_index) % 12

    main_stars_order = ["紫微", "天机", "太阳", "武曲", "天同", "廉贞", "天府", "太阴", "贪狼", "巨门", "天相", "天梁", "七杀", "破军"]
    leap_adjust = 1 if is_leap_month else 0
    month_size_adjust = 1 if month_size == 30 else 0
    ziwei_base = (lunar_day + 11 + leap_adjust + month_size_adjust) % 12
    star_offsets = ZIWEI_SCHOOL_OFFSETS[school_key]

    star_library = _load_ziwei_stars()
    palace_stars: Dict[str, List[Dict[str, str]]] = {p: [] for p in ZIWEI_PALACES}
    for star in main_stars_order:
        idx = (ziwei_base + star_offsets[star]) % 12
        palace = ZIWEI_PALACES[idx]
        palace_stars[palace].append({"name": star, **star_library.get(star, ZIWEI_STAR_LIBRARY.get(star, {}))})

    four_hua = _resolve_four_transformations(ec, scope_key)
    transformed_star_names = {
        four_hua.get("禄"),
        four_hua.get("权"),
        four_hua.get("科"),
        four_hua.get("忌"),
    }
    if scope_key == "full":
        transformed_star_names |= {
            four_hua.get("month_transformations", {}).get("禄"),
            four_hua.get("month_transformations", {}).get("权"),
            four_hua.get("month_transformations", {}).get("科"),
            four_hua.get("month_transformations", {}).get("忌"),
            four_hua.get("day_transformations", {}).get("禄"),
            four_hua.get("day_transformations", {}).get("权"),
            four_hua.get("day_transformations", {}).get("科"),
            four_hua.get("day_transformations", {}).get("忌"),
        }
    transformed_star_details = {
        name: star_library.get(name, ZIWEI_STAR_LIBRARY.get(name, {}))
        for name in transformed_star_names
        if name
    }

    svg_parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="840" height="520" viewBox="0 0 840 520">',
        '<rect x="0" y="0" width="840" height="520" fill="#0f1522" />',
    ]
    box_w = 260
    box_h = 120
    for i, palace in enumerate(ZIWEI_PALACES):
        row, col = divmod(i, 4)
        x = 20 + col * (box_w + 10)
        y = 20 + row * (box_h + 10)
        svg_parts.append(f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" fill="#131c2d" stroke="#32507a" />')
        stars_text = "、".join([s["name"] for s in palace_stars[palace]]) or "无主星"
        svg_parts.append(f'<text x="{x+8}" y="{y+22}" fill="#89b4ff" font-size="14">{palace}</text>')
        svg_parts.append(f'<text x="{x+8}" y="{y+48}" fill="#d7e5ff" font-size="13">{stars_text}</text>')
    svg_parts.append("</svg>")

    return {
        "module": "紫微斗数排盘",
        "name": name,
        "solar_birthday": birthday,
        "birth_time": birth_time,
        "timezone_offset": timezone_offset,
        "longitude": longitude,
        "lunar_birthday": f"{lunar.getYearInChinese()}年{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}",
        "ziwei_config": {
            "school": school_key,
            "transform_scope": scope_key,
            "is_leap_month": is_leap_month,
            "lunar_month_size": month_size,
            "algorithm_version": "v2.1",
        },
        "ming_gong": ZIWEI_PALACES[ming_idx],
        "shen_gong": ZIWEI_PALACES[shen_idx],
        "four_transformations": four_hua,
        "transformation_star_details": transformed_star_details,
        "palace_stars": palace_stars,
        "star_library_size": len(star_library),
        "chart_svg": "".join(svg_parts),
        "insight": "建议优先查看命宫、事业宫、财帛宫，并结合大限阶段做阶段性决策。",
    }


def hhuangli(date: str, activity: str) -> Dict:
    day = dt.datetime.strptime(date, "%Y-%m-%d").date()
    rule = ACTIVITY_MAP.get(activity, (["平日可行"], ["注意时机"]))
    suitable, avoid = rule
    parity = "偶数日" if day.day % 2 == 0 else "奇数日"
    yi = suitable + [parity]
    ji = avoid + (["冲日"] if day.day % 5 == 0 else ["无明显冲煞"])
    return {
        "module": "黄历查询",
        "date": date,
        "activity": activity,
        "yi": yi,
        "ji": ji,
        "note": "仅作传统文化参考，请结合现实条件与法律规范。",
    }


def _time_context(reference_date: str | None = None) -> Dict[str, str]:
    now = dt.datetime.now()
    ref = now
    if reference_date:
        try:
            ref = dt.datetime.strptime(reference_date, "%Y-%m-%d")
        except ValueError:
            ref = now
    hour = now.hour
    period = "清晨" if 5 <= hour < 8 else "白天" if 8 <= hour < 18 else "夜间"
    season = (
        "春季"
        if ref.month in (3, 4, 5)
        else "夏季"
        if ref.month in (6, 7, 8)
        else "秋季"
        if ref.month in (9, 10, 11)
        else "冬季"
    )
    return {
        "current_datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "weekday": WEEKDAY_CN[now.weekday()],
        "time_period": period,
        "reference_date": ref.strftime("%Y-%m-%d"),
        "season": season,
    }


def _result_highlights(result: Dict[str, Any]) -> List[str]:
    points: List[str] = []
    if "strongest_element" in result and "weakest_element" in result:
        points.append(f"五行重心：{result['strongest_element']}强，{result['weakest_element']}弱。")
    if "score" in result and "rating" in result:
        points.append(f"关系评分：{result['score']}（{result['rating']}）。")
    if "scores" in result and isinstance(result["scores"], dict):
        overall = result["scores"].get("overall")
        if overall is not None:
            points.append(f"综合运势分：{overall}。")
    if "hexagram" in result and "trend" in result:
        points.append(f"卦象：{result['hexagram']}，建议：{result['trend']}。")
    if "cards" in result:
        cards = [c["card"] for c in result["cards"]]
        points.append(f"抽取牌面：{'、'.join(cards)}。")
    if "yi" in result and "ji" in result:
        points.append(f"黄历宜：{'、'.join(result['yi'][:2])}；忌：{'、'.join(result['ji'][:2])}。")
    if "insight" in result:
        points.append(str(result["insight"]))
    return points[:3]


def _build_ai_prompt(module: str, user_input: Dict[str, Any], result: Dict[str, Any], reference_date: str | None) -> str:
    knowledge = AI_KNOWLEDGE.get(module, ["理性表达，避免绝对化。", "输出可执行建议。"])
    time_ctx = _time_context(reference_date)
    highlights = _result_highlights(result)
    
    if module == "每日运势分析":
        output_format = "请输出：1) 今日关键洞察 2) 风险提醒 3) 今日可执行行动（3条）。"
    elif module in ["八字分析命盘解析", "紫微斗数排盘"]:
        output_format = "请输出：\n1) 命盘综合分析\n2) 事业运势分析\n3) 财富运势分析\n4) 桃花/感情运势分析\n5) 健康运势分析\n6) 总结与建议。"
    elif module in ["事业合作分析", "婆媳关系分析", "知己分析", "紫微合婚"]:
        output_format = "请输出：\n1) 关系综合评分与定调\n2) 双方命理特质交叉分析\n3) 核心优势与契合点\n4) 潜在冲突与风险点\n5) 改善关系的具体建议。"
    else:
        output_format = "请输出：\n1) 综合现状分析\n2) 关键节点与变量\n3) 应对策略与建议。"

    return "\n".join(
        [
            "你是理性、克制、可执行导向的命理分析助手。",
            "目标：基于输入与计算结果，给出详尽、中立、具体、可落地的多维度分析与建议。",
            "规则：不神化、不恐吓、不做决定替代，避免绝对化语言。",
            f"模块：{module}",
            f"时间上下文：{time_ctx}",
            f"领域知识：{knowledge}",
            f"用户输入：{user_input}",
            f"核心结果：{highlights}",
            output_format,
        ]
    )


def _to_int(value: str, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _extract_openai_content(data: Dict[str, Any]) -> str | None:
    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        merged = "\n".join([p for p in parts if p.strip()]).strip()
        return merged or None
    return None


def _extract_anthropic_content(data: Dict[str, Any]) -> str | None:
    content = data.get("content", [])
    if not isinstance(content, list):
        return None
    parts: List[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
    merged = "\n".join([p for p in parts if p.strip()]).strip()
    return merged or None


def _call_openai_protocol(system_prompt: str, user_prompt: str, cfg: Dict[str, str]) -> str | None:
    api_key = cfg["api_key_openai"]
    if not api_key:
        return None
    url = f"{cfg['base_url_openai'].rstrip('/')}/chat/completions"
    timeout_sec = _to_int(cfg["timeout_sec"], 120)
    deep_thinking = cfg["deep_thinking"] == "true"
    payload_base: Dict[str, Any] = {
        "model": cfg["model_openai"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.5,
    }
    payload_with_reasoning = dict(payload_base)
    if deep_thinking:
        payload_with_reasoning["reasoning_effort"] = cfg["reasoning_effort"]
        payload_with_reasoning["thinking"] = {
            "type": "enabled",
            "budget_tokens": _to_int(cfg["thinking_budget_tokens"], 1024),
        }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(url, headers=headers, json=payload_with_reasoning, timeout=timeout_sec)
        if deep_thinking and resp.status_code >= 400:
            resp = requests.post(url, headers=headers, json=payload_base, timeout=timeout_sec)
        resp.raise_for_status()
        return _extract_openai_content(resp.json())
    except Exception as exc:
        logger.warning("openai protocol call failed: %s", exc)
        return None


def _call_anthropic_protocol(system_prompt: str, user_prompt: str, cfg: Dict[str, str]) -> str | None:
    api_key = cfg["api_key_anthropic"]
    if not api_key:
        return None
    url = f"{cfg['base_url_anthropic'].rstrip('/')}/messages"
    timeout_sec = _to_int(cfg["timeout_sec"], 120)
    deep_thinking = cfg["deep_thinking"] == "true"
    payload_base: Dict[str, Any] = {
        "model": cfg["model_anthropic"],
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
        "max_tokens": _to_int(cfg["max_tokens"], 1024),
    }
    payload_with_reasoning = dict(payload_base)
    if deep_thinking:
        payload_with_reasoning["thinking"] = {
            "type": "enabled",
            "budget_tokens": _to_int(cfg["thinking_budget_tokens"], 1024),
        }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": cfg["anthropic_version"],
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(url, headers=headers, json=payload_with_reasoning, timeout=timeout_sec)
        if deep_thinking and resp.status_code >= 400:
            resp = requests.post(url, headers=headers, json=payload_base, timeout=timeout_sec)
        resp.raise_for_status()
        return _extract_anthropic_content(resp.json())
    except Exception as exc:
        logger.warning("anthropic protocol call failed: %s", exc)
        return None


def _call_external_llm(system_prompt: str, user_prompt: str) -> str | None:
    cfg = _ai_settings()
    if cfg["protocol"] == "anthropic":
        return _call_anthropic_protocol(system_prompt, user_prompt, cfg)
    return _call_openai_protocol(system_prompt, user_prompt, cfg)


def _sanitize_response_payload(data: Any) -> Any:
    if isinstance(data, dict):
        cleaned: Dict[str, Any] = {}
        for key, value in data.items():
            lowered = str(key).lower()
            if any(keyword in lowered for keyword in SENSITIVE_KEYWORDS):
                continue
            cleaned[key] = _sanitize_response_payload(value)
        return cleaned
    if isinstance(data, list):
        return [_sanitize_response_payload(item) for item in data]
    return data


def _normalize_ai_analysis_lines(lines: List[str]) -> List[str]:
    normalized: List[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("```"):
            continue
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"\*([^*]+)\*", r"\1", line)
        line = re.sub(r"^\s*[-*+]\s+", "• ", line)
        normalized.append(line)
    return normalized


def attach_ai_layer(module: str, user_input: Dict[str, Any], result: Dict[str, Any], reference_date: str | None = None) -> Dict[str, Any]:
    prompt = _build_ai_prompt(module, user_input, result, reference_date)
    time_ctx = _time_context(reference_date)
    highlights = _result_highlights(result)
    knowledge = AI_KNOWLEDGE.get(module, ["理性表达，避免绝对化。", "输出可执行建议。"])
    ai_text_fallback = [
        f"结合{time_ctx['weekday']}（{time_ctx['time_period']}）与当前节律，建议先聚焦最关键的一件事。",
        "从本次结果看，优先处理“可控变量”，再处理“情绪变量”，会更稳健。",
        "本周行动建议：1) 明确目标与边界 2) 固定复盘节奏 3) 关键沟通提前约定规则。",
    ]
    if highlights:
        ai_text_fallback.insert(0, f"关键洞察：{highlights[0]}")

    system_prompt = (
        "你是理性、克制、可执行导向的命理分析助手。"
        "请使用中文。不要神化、不要绝对化、不要恐吓用户，"
        "输出聚焦可执行建议。"
    )
    try:
        llm_text = _call_external_llm(system_prompt, prompt)
    except Exception as exc:
        logger.exception("attach_ai_layer external llm failed module=%s error=%s", module, exc)
        llm_text = None
    final_analysis_raw = [line for line in (llm_text or "").split("\n") if line.strip()] if llm_text else ai_text_fallback
    final_analysis = _normalize_ai_analysis_lines(final_analysis_raw)
    analysis_markdown = (llm_text or "\n".join(ai_text_fallback)).strip()

    merged = dict(result)
    cfg = _ai_settings()
    protocol = cfg["protocol"]
    active_model = cfg["model_anthropic"] if protocol == "anthropic" else cfg["model_openai"]
    llm_enabled_public = _env("LLM_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    merged["ai"] = {
        "prompt_version": "v2.2",
        "provider": cfg["provider"],
        "protocol": protocol,
        "model": active_model,
        "deep_thinking_enabled": cfg["deep_thinking"] == "true",
        "reasoning_effort": cfg["reasoning_effort"],
        "llm_enabled": llm_enabled_public,
        "llm_response_mode": "external" if llm_text else "fallback",
        "time_context": time_ctx,
        "knowledge_points": knowledge,
        "optimized_prompt": prompt,
        "analysis_markdown": analysis_markdown,
        "analysis": final_analysis,
    }
    return _sanitize_response_payload(merged)
