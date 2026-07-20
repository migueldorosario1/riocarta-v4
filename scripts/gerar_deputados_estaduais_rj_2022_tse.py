#!/usr/bin/env python3
"""Gera CSV com deputados estaduais eleitos do RJ em 2022 a partir do TSE.

Fonte:
https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2022.zip

Saida padrao:
src/data/deputados_estaduais_eleitos_rj_2022.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import unicodedata
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any


TSE_ZIP_URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2022.zip"
CSV_NAME = "votacao_candidato_munzona_2022_RJ.csv"
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_PATH = PROJECT_ROOT / "src" / "data" / "deputados_estaduais_eleitos_rj_2022.csv"
JSON_OUTPUT_PATH = PROJECT_ROOT / "src" / "data" / "deputados_estaduais_eleitos_rj_2022.json"


def slugify(text: str) -> str:
    clean = unicodedata.normalize("NFKD", text)
    clean = clean.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", clean.lower()).strip("-")


def title_pt_br(text: str) -> str:
    small_words = {"da", "das", "de", "do", "dos", "e", "em", "na", "nas", "no", "nos", "a", "o"}
    words = []
    for idx, word in enumerate((text or "").strip().split()):
        lower = word.lower()
        if idx > 0 and lower in small_words:
            words.append(lower)
        else:
            words.append(lower[:1].upper() + lower[1:])
    return " ".join(words)


def load_csv_text(zip_path: Path | None) -> str:
    if zip_path is None:
        with urllib.request.urlopen(TSE_ZIP_URL, timeout=120) as response:
            raw_zip = response.read()
    else:
        raw_zip = zip_path.read_bytes()

    with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
        return archive.read(CSV_NAME).decode("latin-1")


def parse_int(value: str | None) -> int:
    return int(value or 0)


def gerar_linhas(csv_text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=";")
    candidatos: dict[str, dict[str, Any]] = {}
    votos_por_candidato: defaultdict[str, int] = defaultdict(int)
    total_votos_estado = 0

    for row in reader:
        if row.get("SG_UF") != "RJ":
            continue
        if row.get("DS_CARGO", "").upper() != "DEPUTADO ESTADUAL":
            continue

        votos = parse_int(row.get("QT_VOTOS_NOMINAIS"))
        total_votos_estado += votos

        sq = row.get("SQ_CANDIDATO") or row["NR_CANDIDATO"]
        votos_por_candidato[sq] += votos

        if sq not in candidatos:
            candidatos[sq] = {
                "deputado": row.get("NM_CANDIDATO", ""),
                "nome_urna": row.get("NM_URNA_CANDIDATO", ""),
                "partido": row.get("SG_PARTIDO", ""),
                "numero": row.get("NR_CANDIDATO", ""),
                "situacao": row.get("DS_SIT_TOT_TURNO", ""),
            }

    eleitos = []
    situacoes_eleito = {"ELEITO POR QP", "ELEITO POR MÉDIA", "ELEITO POR MEDIA"}
    for sq, candidato in candidatos.items():
        situacao = candidato["situacao"]
        if situacao.upper() not in situacoes_eleito:
            continue

        votos = votos_por_candidato[sq]
        eleitos.append(
            {
                **candidato,
                "votos": votos,
                "total_votos_estado": total_votos_estado,
                "percentual_estado": round((votos / total_votos_estado) * 100, 4)
                if total_votos_estado
                else 0,
            }
        )

    return sorted(eleitos, key=lambda item: (-item["votos"], item["deputado"]))


def escrever_csv(linhas: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "deputado",
        "nome_urna",
        "partido",
        "numero",
        "votos",
        "total_votos_estado",
        "percentual_estado",
        "situacao",
    ]

    with output_path.open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(linhas)


def escrever_json(linhas: list[dict[str, Any]], output_path: Path) -> None:
    deputados = []
    for linha in linhas:
        nome = title_pt_br(linha["nome_urna"] or linha["deputado"])
        deputados.append(
            {
                "nome": nome,
                "slug": slugify(nome),
                "deputado": title_pt_br(linha["deputado"]),
                "partido": linha["partido"],
                "numero": linha["numero"],
                "votos": linha["votos"],
                "totalVotosEstado": linha["total_votos_estado"],
                "percentualEstado": linha["percentual_estado"],
                "situacao": linha["situacao"],
            }
        )

    payload = {
        "schemaVersion": "v1",
        "source": "TSE votacao_candidato_munzona_2022_RJ.csv",
        "criterio": "Deputados estaduais eleitos em 2022; percentual sobre total de votos válidos nominais para deputado estadual no RJ.",
        "total": len(deputados),
        "deputados": deputados,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, help="Zip local do TSE; se omitido, baixa da fonte oficial.")
    parser.add_argument("--out", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--json-out", type=Path, default=JSON_OUTPUT_PATH)
    args = parser.parse_args()

    linhas = gerar_linhas(load_csv_text(args.zip))
    escrever_csv(linhas, args.out)
    escrever_json(linhas, args.json_out)

    total_votos = linhas[0]["total_votos_estado"] if linhas else 0
    print(f"CSV gerado: {args.out}")
    print(f"JSON gerado: {args.json_out}")
    print(f"Deputados eleitos: {len(linhas)}")
    print(f"Total de votos nominais no estado: {total_votos}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
