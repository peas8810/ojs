# scripts/update_scilit.py
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests


SCILIT_URL = "https://www.scilit.com/sources/96056"
OUT_JSON = Path("remunom-scilit.json")


def fetch_html(url: str) -> str:
    headers = {
        # UA “normal” ajuda a reduzir bloqueios
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Referer": "https://www.scilit.com/",
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def parse_number_near_label(html: str, label_regex: str) -> float | int | None:
    """
    Heurística: acha um rótulo (ex: h5-index) e captura o número próximo.
    """
    # Pega um “trecho” ao redor do label pra procurar número
    m = re.search(label_regex, html, flags=re.IGNORECASE)
    if not m:
        return None
    start = max(m.start() - 200, 0)
    end = min(m.end() + 400, len(html))
    chunk = html[start:end]

    # números: 12, 12.3, 1,276 etc.
    num = re.search(r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)", chunk)
    if not num:
        return None

    s = num.group(1).replace(".", "").replace(",", ".")
    try:
        x = float(s)
        return int(x) if x.is_integer() else x
    except Exception:
        return None


def parse_series(html: str) -> list[dict]:
    """
    Tenta extrair dados do gráfico.
    Como o Scilit pode mudar o front-end, usamos heurísticas:
      - procura por meses no formato YYYY-MM
      - procura por arrays numéricos próximos a 'Monthly Citation Metric'
    Retorna: [{"month":"YYYY-MM","value":0.42}, ...]
    """
    # 1) tenta achar meses YYYY-MM no HTML
    months = re.findall(r"(20\d{2}-\d{2})", html)
    # remove duplicados mantendo ordem
    seen = set()
    months = [m for m in months if not (m in seen or seen.add(m))]

    # 2) tenta achar um array de números perto da expressão "Monthly Citation Metric"
    idx = re.search(r"Monthly\s+Citation\s+Metric", html, flags=re.IGNORECASE)
    if not idx:
        return []

    window = html[idx.start(): idx.start() + 50000]  # janela grande
    # tenta pegar um array JS tipo: [0.1, 0.2, ...]
    arr = re.search(r"\[(?:\s*\d+(?:\.\d+)?\s*,?)+\s*\]", window)
    if not arr:
        return []

    raw = arr.group(0)
    values = re.findall(r"\d+(?:\.\d+)?", raw)
    values = [float(v) for v in values]

    # Se a lista de meses for menor/maior, tentamos “alinhar” pelo menor tamanho
    n = min(len(months), len(values))
    if n == 0:
        return []

    series = [{"month": months[i], "value": round(values[i], 4)} for i in range(n)]
    return series


def main() -> None:
    # carrega JSON antigo (fallback)
    old = {}
    if OUT_JSON.exists():
        try:
            old = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        except Exception:
            old = {}

    try:
        html = fetch_html(SCILIT_URL)

        h5_index = parse_number_near_label(html, r"\bh5[-\s]?index\b")
        mcm = parse_number_near_label(html, r"Monthly\s+Citation\s+Metric")

        series = parse_series(html)

        # Se não conseguiu ler série, mantém a antiga
        if not series and isinstance(old.get("series"), list):
            series = old["series"]

        payload = {
            "source": SCILIT_URL,
            "updated_at": datetime.now(timezone.utc).date().isoformat(),
            "h5_index": h5_index if h5_index is not None else old.get("h5_index"),
            "mcm": mcm if mcm is not None else old.get("mcm"),
            "series": series,
        }

        OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print("OK: JSON atualizado.")
    except Exception as e:
        # Não quebra seu painel: mantém o arquivo como está
        print("ERRO ao atualizar (mantendo JSON anterior):", repr(e))


if __name__ == "__main__":
    main()
