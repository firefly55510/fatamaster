from __future__ import annotations

import logging
import os
import re
import uuid
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request

from engine import (
    attach_ai_layer,
    bazi_analysis,
    compatibility,
    daily_fortune,
    hhuangli,
    liuyao_divine,
    meihua_decision,
    relationship_graph,
    tarot_divine,
    ziwei_chart,
    export_marriage_pdf,
    PdfExportError,
    _ai_settings,
)

app = FastAPI(title="FateMaster 模拟版", version="0.2.0", openapi_version="3.0.3")
load_dotenv()
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _cors_settings() -> Dict[str, Any]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000").strip()
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    if not origins:
        origins = ["http://127.0.0.1:8000"]
    wildcard = "*" in origins
    return {
        "allow_origins": origins,
        "allow_credentials": False if wildcard else True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


_cors = _cors_settings()


def _is_development_env() -> bool:
    # 优先使用 APP_ENV；兼容历史 FLASK_ENV
    env = os.getenv("APP_ENV", "").strip().lower() or os.getenv("FLASK_ENV", "").strip().lower()
    return env == "development"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors["allow_origins"],
    allow_credentials=_cors["allow_credentials"],
    allow_methods=_cors["allow_methods"],
    allow_headers=_cors["allow_headers"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.middleware("http")
async def internal_error_middleware(request: Request, call_next):
    trace_id = uuid.uuid4().hex
    try:
        return await call_next(request)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled server error trace_id=%s path=%s", trace_id, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error", "trace_id": trace_id})


class PersonProfile(BaseModel):
    name: str = Field(..., description="姓名")
    birthday: str = Field(..., description="生日 YYYY-MM-DD", pattern=r"^\d{4}-\d{2}-\d{2}$")
    birth_time: Optional[str] = Field(None, description="出生时辰 HH:MM 或 HH:MM:SS", pattern=r"^\d{2}:\d{2}(:\d{2})?$")
    gender: Optional[str] = Field("未知", description="性别")
    birth_place: Optional[str] = Field("", description="出生地（城市/国家），用于自动推断时区")
    timezone_offset: Optional[int] = Field(None, description="时区偏移，例如北京时间为 8", ge=-12, le=14)
    longitude: Optional[float] = Field(None, description="出生地经度，用于真太阳时校正", ge=-180.0, le=180.0)
    ziwei_school: Optional[str] = Field("sanhe", description="紫微流派：sanhe / feixing")
    ziwei_transform_scope: Optional[str] = Field("year", description="四化范围：year / full")


class SingleProfileRequest(BaseModel):
    profile: PersonProfile


class DailyRequest(BaseModel):
    name: str
    gender: str = "男"
    birthday: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    birth_time: str = Field("12:00", pattern=r"^\d{2}:\d{2}$")
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")


class PairRequest(BaseModel):
    left: PersonProfile
    right: PersonProfile


class GraphRelation(BaseModel):
    name: str
    relation_type: str = Field(..., description="婚姻/亲子/事业/朋友等")


class GraphRequest(BaseModel):
    center_name: str
    relations: List[GraphRelation]


class QuestionRequest(BaseModel):
    question: str
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")


class HuangliRequest(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    activity: str


class PdfDebugRequest(BaseModel):
    output_dir: str


class AIResponse(BaseModel):
    prompt_version: str
    provider: str
    protocol: str
    model: str
    deep_thinking_enabled: bool
    reasoning_effort: str
    llm_enabled: bool
    llm_response_mode: str
    time_context: Dict[str, Any]
    knowledge_points: List[str]
    optimized_prompt: str
    analysis_markdown: Optional[str] = None
    analysis: List[str]


class GenericModuleResponse(BaseModel):
    model_config = ConfigDict(extra="allow")


class HealthResponse(BaseModel):
    ok: bool
    service: str


class PublicConfigResponse(BaseModel):
    provider: str
    protocol: str
    model: str
    deep_thinking_enabled: bool
    reasoning_effort: str


PLACE_TIMEZONE_MAP = {
    "中国": 8, "北京": 8, "上海": 8, "广州": 8, "深圳": 8, "香港": 8, "澳门": 8, "台北": 8,
    "东京": 9, "首尔": 9, "新加坡": 8, "曼谷": 7,
    "伦敦": 0, "巴黎": 1, "柏林": 1, "莫斯科": 3,
    "迪拜": 4, "新德里": 5, "孟买": 5,
    "悉尼": 10, "墨尔本": 10,
    "纽约": -5, "华盛顿": -5, "芝加哥": -6, "丹佛": -7, "洛杉矶": -8, "温哥华": -8,
}

PLACE_LONGITUDE_MAP = {
    "北京": 116.4, "上海": 121.5, "广州": 113.3, "深圳": 114.1, "台北": 121.5,
    "东京": 139.7, "纽约": -74.0, "伦敦": -0.1, "巴黎": 2.35, "洛杉矶": -118.2,
}


def _guess_timezone_from_longitude(longitude: float) -> int:
    return max(-12, min(14, int(round(longitude / 15.0))))


def _resolve_profile_geo(profile: PersonProfile) -> Dict[str, Any]:
    place = (profile.birth_place or "").strip()
    longitude = profile.longitude
    timezone_offset = profile.timezone_offset
    tz_source = "explicit"
    lon_source = "explicit" if longitude is not None else "default"

    if longitude is None and place:
        for key, lon in PLACE_LONGITUDE_MAP.items():
            if key in place:
                longitude = lon
                lon_source = "place_inferred"
                break
    if longitude is None:
        longitude = 120.0

    if timezone_offset is None and place:
        for key, tz in PLACE_TIMEZONE_MAP.items():
            if key in place:
                timezone_offset = tz
                tz_source = "place_inferred"
                break
    if timezone_offset is None and longitude is not None:
        timezone_offset = _guess_timezone_from_longitude(longitude)
        tz_source = "longitude_inferred"
    if timezone_offset is None:
        timezone_offset = 8
        tz_source = "default_fallback"

    return {
        "birth_place": place,
        "resolved_timezone_offset": timezone_offset,
        "timezone_source": tz_source,
        "resolved_longitude": longitude,
        "longitude_source": lon_source,
    }


def _normalize_birth_time(value: Optional[str]) -> str | None:
    if value is None:
        return None
    v = value.strip()
    return v or None


class BaziResponse(BaseModel):
    module: str
    input: Dict[str, Any]
    time_correction: Dict[str, Any]
    solar_lunar: Dict[str, Any]
    pillars: Dict[str, Dict[str, Any]]
    ten_gods: Dict[str, Any]
    na_yin: Dict[str, str]
    wu_xing_distribution: Dict[str, int]
    structure: Dict[str, Any]
    ai: AIResponse


class LiuyaoResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    module: str
    method: str
    question: str
    date: str
    primary_hexagram: Dict[str, Any]
    changed_hexagram: Dict[str, Any]
    moving_lines: List[int]
    moving_line_texts: List[Dict[str, Any]]
    lines: List[Dict[str, Any]]
    interpretation: Dict[str, Any]
    ai: AIResponse


class ZiweiResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    module: str
    name: str
    solar_birthday: str
    birth_time: str
    lunar_birthday: str
    ming_gong: str
    shen_gong: str
    four_transformations: Dict[str, Any]
    palace_stars: Dict[str, List[Dict[str, Any]]]
    star_library_size: int
    chart_svg: str
    insight: str
    ai: AIResponse


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return RedirectResponse(url="/service/bazi", status_code=302)


@app.get("/service/{module_id}", response_class=HTMLResponse)
def service_page(request: Request, module_id: str):
    return templates.TemplateResponse("index.html", {"request": request, "module_id": module_id})


def _execute_and_attach(
    module_name: str,
    req_payload: Dict[str, Any],
    executor: Callable[[], Dict[str, Any]],
    reference_date: str | None = None,
) -> Dict[str, Any]:
    try:
        raw = executor()
    except ValueError as exc:
        logger.warning("Validation failed module=%s error=%s", module_name, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("Runtime failed module=%s error=%s", module_name, exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PdfExportError:
        raise
    except Exception as exc:
        logger.exception("Unhandled module failure module=%s error=%s", module_name, exc)
        raise HTTPException(status_code=500, detail="模块执行失败") from exc
    return attach_ai_layer(module_name, req_payload, raw, reference_date)


@app.get("/health", response_model=HealthResponse)
def health():
    return {"ok": True, "service": "fatemaster-sim"}


@app.get("/config", response_model=PublicConfigResponse)
def get_public_config():
    cfg = _ai_settings()
    protocol = cfg["protocol"]
    model = cfg["model_anthropic"] if protocol == "anthropic" else cfg["model_openai"]
    return {
        "provider": cfg["provider"],
        "protocol": protocol,
        "model": model,
        "deep_thinking_enabled": cfg["deep_thinking"] == "true",
        "reasoning_effort": cfg["reasoning_effort"],
    }


@app.post("/api/bazi/analyze", response_model=BaziResponse, tags=["核心模块"])
def api_bazi(req: SingleProfileRequest):
    p = req.profile
    geo_ctx = _resolve_profile_geo(p)
    birth_time = _normalize_birth_time(p.birth_time) or "12:00"
    birth_time_status = "explicit" if _normalize_birth_time(p.birth_time) else "assumed_noon_due_to_unknown_hour"
    raw = bazi_analysis(
        p.name,
        p.birthday,
        birth_time,
        p.gender or "未知",
        geo_ctx["resolved_timezone_offset"],
        geo_ctx["resolved_longitude"],
    )
    req_payload = req.model_dump()
    req_payload["profile"]["geo_context"] = geo_ctx
    req_payload["profile"]["birth_time_status"] = birth_time_status
    return attach_ai_layer("八字分析命盘解析", req_payload, raw)


@app.post("/api/fortune/daily", response_model=GenericModuleResponse)
def api_daily(req: DailyRequest):
    return _execute_and_attach(
        "每日运势",
        req.model_dump(),
        lambda: daily_fortune(req.name, req.gender, req.birthday, req.birth_time, req.date),
        req.date,
    )


def _prepare_pair_payload(req: PairRequest) -> Dict[str, Any]:
    req_payload = req.model_dump()
    for p in ["left", "right"]:
        geo_ctx = _resolve_profile_geo(getattr(req, p))
        birth_time = _normalize_birth_time(getattr(req, p).birth_time) or "12:00"
        birth_time_status = "explicit" if _normalize_birth_time(getattr(req, p).birth_time) else "assumed_noon_due_to_unknown_hour"
        
        req_payload[p]["birth_time"] = birth_time
        req_payload[p]["timezone_offset"] = geo_ctx["resolved_timezone_offset"]
        req_payload[p]["longitude"] = geo_ctx["resolved_longitude"]
        req_payload[p]["geo_context"] = geo_ctx
        req_payload[p]["birth_time_status"] = birth_time_status
    return req_payload

@app.post("/api/marriage/analyze", response_model=GenericModuleResponse)
def api_marriage(req: PairRequest):
    req_payload = _prepare_pair_payload(req)
    return _execute_and_attach(
        "合婚分析",
        req_payload,
        lambda: compatibility(req_payload["left"], req_payload["right"], "合婚分析"),
    )

@app.post("/api/marriage/pdf")
def api_marriage_pdf(req: PairRequest):
    req_payload = _prepare_pair_payload(req)
    try:
        raw = compatibility(req_payload["left"], req_payload["right"], "合婚分析")
        pdf_path = export_marriage_pdf(raw, output_dir=None)
    except PdfExportError as exc:
        logger.error("PDF export failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"PDF 导出失败: {exc}") from exc
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"合婚报告_{req.left.name}_{req.right.name}.pdf",
    )

if _is_development_env():
    @app.post("/debug/pdf/export")
    def debug_pdf_export(req: PdfDebugRequest):
        debug_payload = {
            "left": {"name": "调试甲方"},
            "right": {"name": "调试乙方"},
            "score": 80,
            "rating": "中等契合",
            "dimensions": {
                "complementarity": 20,
                "day_master": 15,
                "spouse_palace": 16,
                "children_sync": 12,
                "dayun_sync": 11,
            },
            "strengths": ["调试模式：验证导出链路"],
            "risks": ["调试模式：验证异常捕获"],
            "suggestion": "仅开发环境调试，不可用于生产。",
        }
        try:
            path = export_marriage_pdf(debug_payload, output_dir=req.output_dir)
            return {"ok": True, "path": path}
        except PdfExportError as exc:
            raise HTTPException(status_code=500, detail=f"PDF 导出失败: {exc}") from exc

@app.post("/api/cooperation/analyze", response_model=GenericModuleResponse)
def api_cooperation(req: PairRequest):
    req_payload = _prepare_pair_payload(req)
    return _execute_and_attach(
        "事业合作分析",
        req_payload,
        lambda: compatibility(req_payload["left"], req_payload["right"], "事业合作分析"),
    )

@app.post("/api/mother-in-law/analyze", response_model=GenericModuleResponse)
def api_mother_in_law(req: PairRequest):
    req_payload = _prepare_pair_payload(req)
    return _execute_and_attach(
        "婆媳关系分析",
        req_payload,
        lambda: compatibility(req_payload["left"], req_payload["right"], "婆媳关系分析"),
    )

@app.post("/api/friend/analyze", response_model=GenericModuleResponse)
def api_friend(req: PairRequest):
    req_payload = _prepare_pair_payload(req)
    return _execute_and_attach(
        "知己分析",
        req_payload,
        lambda: compatibility(req_payload["left"], req_payload["right"], "知己分析"),
    )


@app.post("/api/relationship/graph", response_model=GenericModuleResponse)
def api_graph(req: GraphRequest):
    return _execute_and_attach(
        "八字关系图谱",
        req.model_dump(),
        lambda: relationship_graph(req.center_name, [r.model_dump() for r in req.relations]),
    )


@app.post("/api/meihua/daily-decision", response_model=GenericModuleResponse)
def api_meihua(req: QuestionRequest):
    return _execute_and_attach(
        "梅花易数每日决策",
        req.model_dump(),
        lambda: meihua_decision(req.question, req.date),
        req.date,
    )


@app.post("/api/liuyao/divine", response_model=LiuyaoResponse, tags=["核心模块"])
def api_liuyao(req: QuestionRequest):
    raw = liuyao_divine(req.question, req.date)
    return attach_ai_layer("六爻占卜", req.model_dump(), raw, req.date)


@app.post("/api/tarot/divine", response_model=GenericModuleResponse)
def api_tarot(req: QuestionRequest):
    return _execute_and_attach(
        "塔罗占卜",
        req.model_dump(),
        lambda: tarot_divine(req.question, req.date),
        req.date,
    )


@app.post("/api/ziwei/chart", response_model=ZiweiResponse, tags=["核心模块"])
def api_ziwei_chart(req: SingleProfileRequest):
    p = req.profile
    birth_time = _normalize_birth_time(p.birth_time)
    if not birth_time:
        raise HTTPException(status_code=422, detail="紫微斗数排盘需要精确出生时辰（HH:MM 或 HH:MM:SS）。")
    geo_ctx = _resolve_profile_geo(p)
    req_payload = req.model_dump()
    req_payload["profile"]["geo_context"] = geo_ctx
    return _execute_and_attach(
        "紫微斗数排盘",
        req_payload,
        lambda: ziwei_chart(
            p.name,
            p.birthday,
            birth_time,
            p.ziwei_school or "sanhe",
            p.ziwei_transform_scope or "year",
            geo_ctx["resolved_timezone_offset"],
            geo_ctx["resolved_longitude"],
        ),
    )


@app.post("/api/ziwei/marriage", response_model=GenericModuleResponse)
def api_ziwei_marriage(req: PairRequest):
    return _execute_and_attach(
        "紫微合婚",
        req.model_dump(),
        lambda: compatibility(req.left.model_dump(), req.right.model_dump(), "紫微合婚"),
    )


@app.post("/api/huangli", response_model=GenericModuleResponse)
def api_huangli(req: HuangliRequest):
    return _execute_and_attach(
        "黄历查询",
        req.model_dump(),
        lambda: hhuangli(req.date, req.activity),
        req.date,
    )


"""
设计说明：
1. 本项目为“功能模拟版”，核心目标是提供相同模块入口与交互流程。
2. 结果为可复现的算法生成内容，不代表任何确定性预测结论。
3. 按用户需求移除了登录验证、订阅校验、权限控制。
"""
