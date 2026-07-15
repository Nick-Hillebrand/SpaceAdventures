"""Embeddable widgets (Architecture/23-seo-widgets-and-growth.md L3).

GET /embed/next-launch?provider=&lang= returns a self-contained HTML page
(inline CSS + JS, no external assets) showing a live countdown to the next
upcoming launch.  Consumers embed it via <iframe src="…/embed/next-launch">.

Security notes:
- CSP frame-ancestors * overrides the main-app 'self' restriction so the
  widget can be framed by any third-party site.
- No cookies, no auth, no personal data on this route.
- LL2 fields (mission_name, agency_name, rocket_name, status_name) flow into
  the HTML response: they are JSON-encoded with < → \\u003c and embedded in a
  <script> data variable (never via innerHTML / dangerouslySetInnerHTML); the
  output context is therefore JS string / JSON, not raw HTML.  This is
  documented in tests/security/test_injection.py.
"""
from __future__ import annotations

import html
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.launches import Launch
from app.services import launches_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["embed"])

_SUPPORTED_LANGS = frozenset({"en", "de", "es", "fr", "ja", "ru"})

# Widget UI strings — kept inline so the embed response is truly self-contained
# (no locale-file fetch, no CDN).
_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Next Launch",
        "cd_label": "Countdown",
        "no_launch": "No upcoming launches",
        "powered_by": "Powered by Space Adventures",
        "loading": "Loading…",
    },
    "de": {
        "title": "Nächster Start",
        "cd_label": "Countdown",
        "no_launch": "Keine bevorstehenden Starts",
        "powered_by": "Bereitgestellt von Space Adventures",
        "loading": "Laden…",
    },
    "es": {
        "title": "Próximo lanzamiento",
        "cd_label": "Cuenta regresiva",
        "no_launch": "Sin lanzamientos próximos",
        "powered_by": "Con tecnología de Space Adventures",
        "loading": "Cargando…",
    },
    "fr": {
        "title": "Prochain lancement",
        "cd_label": "Compte à rebours",
        "no_launch": "Aucun lancement à venir",
        "powered_by": "Propulsé par Space Adventures",
        "loading": "Chargement…",
    },
    "ja": {
        "title": "次回打ち上げ",
        "cd_label": "カウントダウン",
        "no_launch": "予定されている打ち上げはありません",
        "powered_by": "Space Adventures による",
        "loading": "読み込み中…",
    },
    "ru": {
        "title": "Следующий пуск",
        "cd_label": "Обратный отсчёт",
        "no_launch": "Нет предстоящих запусков",
        "powered_by": "На базе Space Adventures",
        "loading": "Загрузка…",
    },
}

# Use __PLACEHOLDER__ markers so substitution never conflicts with CSS braces
# or JS syntax.  Values are either HTML-escaped strings (for HTML attributes)
# or JSON blobs with < → \\u003c (for <script> data variables).
_EMBED_TEMPLATE = """\
<!DOCTYPE html>
<html lang="__LANG__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE_ESC__</title>
<style>
:root{color-scheme:light dark;font-family:system-ui,sans-serif;--bg:#0f172a;--fg:#f1f5f9;--mu:#94a3b8;--ac:#38bdf8;--ca:#1e293b;--bd:#334155}
@media(prefers-color-scheme:light){:root{--bg:#f8fafc;--fg:#0f172a;--mu:#64748b;--ac:#0284c7;--ca:#fff;--bd:#e2e8f0}}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%}
body{background:var(--bg);color:var(--fg);display:flex;flex-direction:column;padding:.75rem;gap:.5rem}
.w{background:var(--ca);border:1px solid var(--bd);border-radius:.625rem;padding:1rem;flex:1;display:flex;flex-direction:column;gap:.5rem;min-height:0}
.badge{font-size:.6rem;text-transform:uppercase;letter-spacing:.1em;color:var(--ac);font-weight:700}
.mission{font-size:1rem;font-weight:600;line-height:1.4;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.meta{font-size:.75rem;color:var(--mu);display:flex;gap:.5rem;flex-wrap:wrap}
.status{font-size:.6rem;font-weight:600;padding:.15em .5em;border-radius:.25rem;background:var(--ac);color:#fff;align-self:flex-start}
.cd-l{font-size:.6rem;text-transform:uppercase;letter-spacing:.05em;color:var(--mu);margin-top:auto;padding-top:.5rem}
.cd{font-size:1.4rem;font-weight:700;font-variant-numeric:tabular-nums;font-family:ui-monospace,monospace}
.attr{font-size:.6rem;color:var(--mu);text-align:right}
.attr a{color:var(--mu);text-decoration:none}
.attr a:hover{color:var(--ac)}
</style>
</head>
<body>
<div class="w">
<p class="badge" id="badge"></p>
<p id="msg"></p>
<div id="info" hidden>
<p class="mission" id="mission"></p>
<div class="meta"><span id="agency"></span><span id="net-dt"></span></div>
<p class="status" id="status-text"></p>
<p class="cd-l" id="cd-label"></p>
<p class="cd" id="cd">--d --h --m --s</p>
</div>
</div>
<p class="attr"><a href="__ORIGIN_ESC__" target="_blank" rel="noopener noreferrer" id="attr-link"></a></p>
<script>
(function(){
var S=__LABELS_JSON__;
var L=__LAUNCH_JSON__;
var lang="__LANG__";
document.getElementById("badge").textContent=S.title;
document.getElementById("attr-link").textContent=S.powered_by;
if(!L){document.getElementById("msg").textContent=S.no_launch;return;}
document.getElementById("msg").textContent=S.loading;
var n=new Date(L.net).getTime();
document.getElementById("mission").textContent=L.mission_name||L.name;
document.getElementById("agency").textContent=L.agency_name||"";
try{document.getElementById("net-dt").textContent=new Intl.DateTimeFormat(lang,{dateStyle:"medium",timeStyle:"short"}).format(new Date(L.net));}
catch(e){document.getElementById("net-dt").textContent=L.net;}
document.getElementById("status-text").textContent=L.status_name||"";
document.getElementById("cd-label").textContent=S.cd_label;
document.getElementById("msg").hidden=true;
document.getElementById("info").removeAttribute("hidden");
function pad(x){return x<10?"0"+x:x;}
function tick(){
var d=n-Date.now();
if(d<=0){document.getElementById("cd").textContent="T+0";clearInterval(iv);return;}
var dy=Math.floor(d/864e5),h=Math.floor(d%864e5/36e5),m=Math.floor(d%36e5/6e4),s=Math.floor(d%6e4/1e3);
document.getElementById("cd").textContent=dy+"d "+pad(h)+"h "+pad(m)+"m "+pad(s)+"s";
}
tick();var iv=setInterval(tick,1000);
})();
</script>
</body>
</html>
"""


def _json_safe(data: object) -> str:
    """JSON-encode + escape chars unsafe inside <script>…</script>.

    U+2028 (line separator) and U+2029 (paragraph separator) are ECMAScript
    line terminators; left literal they break string literals inside <script>.
    """
    return (
        json.dumps(data, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def _launch_json(launch: Launch | None) -> str:
    if launch is None:
        return "null"
    net = launch.net
    if net.tzinfo is None:
        net = net.replace(tzinfo=timezone.utc)
    return _json_safe(
        {
            "name": launch.name,
            "mission_name": launch.mission_name,
            "net": net.isoformat(),
            "agency_name": launch.agency_name,
            "rocket_name": launch.rocket_name,
            "status_name": launch.status_name,
        }
    )


def _render(launch: Launch | None, lang: str, origin: str) -> str:
    labels = _LABELS.get(lang, _LABELS["en"])
    return (
        _EMBED_TEMPLATE
        .replace("__LANG__", lang)
        .replace("__TITLE_ESC__", html.escape(labels["title"]))
        .replace("__ORIGIN_ESC__", html.escape(origin, quote=True))
        .replace("__LABELS_JSON__", _json_safe(labels))
        .replace("__LAUNCH_JSON__", _launch_json(launch))
    )


_EMBED_CSP = (
    "default-src 'self'; "
    "script-src 'unsafe-inline'; "
    "style-src 'unsafe-inline'; "
    "img-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors *"
)


@router.get("/embed/next-launch")
async def embed_next_launch(
    request: Request,
    provider: str | None = Query(default=None, max_length=200),
    lang: str = Query(default="en", max_length=5),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Self-contained next-launch countdown widget for third-party embedding.

    Returns a minimal HTML page (≤ 30 KB) with inline CSS + JS — no external
    assets, no cookies, no auth.  Consumers embed via:
      <iframe src="https://{domain}/embed/next-launch"></iframe>
    """
    safe_lang = lang if lang in _SUPPORTED_LANGS else "en"
    settings = request.app.state.settings
    origin = str(settings.frontend_origin).rstrip("/")

    launch = await launches_service.get_next_launch(session, provider or None)
    body = _render(launch, safe_lang, origin)

    return Response(
        content=body,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=60",
            "Content-Security-Policy": _EMBED_CSP,
        },
    )
