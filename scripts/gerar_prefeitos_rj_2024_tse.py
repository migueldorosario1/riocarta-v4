#!/usr/bin/env python3
"""Gera CSV e JSON com prefeitos eleitos no RJ em 2024.

Fonte oficial:
https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2024.zip

Saidas padrao:
src/data/prefeitos_eleitos_rj_2024.csv
src/data/prefeitos_eleitos_rj_2024.json
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


TSE_ZIP_URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2024.zip"
CSV_NAME = "votacao_candidato_munzona_2024_RJ.csv"
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_CSV = PROJECT_ROOT / "src" / "data" / "prefeitos_eleitos_rj_2024.csv"
OUTPUT_JSON = PROJECT_ROOT / "src" / "data" / "prefeitos_eleitos_rj_2024.json"

SITUACOES_ELEITO = {"ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA", "ELEITO POR MEDIA"}
CASOS_SEM_ELEICAO_VALIDADA = [
    {
        "municipio": "Itaguaí",
        "municipio_slug": "itaguai",
        "turno": None,
        "prefeito": "Haroldo Rodrigues Jesus Neto",
        "nome_urna": "Haroldo Jesus",
        "partido": "PDT",
        "numero": "",
        "situacao": "PREFEITO INTERINO; eleição municipal sem eleito validado no TSE",
        "votos": 0,
        "total_votos_municipio": 0,
        "percentual_municipio": 0,
    }
]


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


def parse_int(value: str | None) -> int:
    return int(value or 0)


def load_csv_text(zip_path: Path | None) -> str:
    if zip_path is None:
        with urllib.request.urlopen(TSE_ZIP_URL, timeout=120) as response:
            raw_zip = response.read()
    else:
        raw_zip = zip_path.read_bytes()

    with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
        return archive.read(CSV_NAME).decode("latin-1")


def row_votes(row: dict[str, str]) -> int:
    return parse_int(row.get("QT_VOTOS_NOMINAIS_VALIDOS") or row.get("QT_VOTOS_NOMINAIS"))


def gerar_linhas(csv_text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=";")
    candidatos: dict[tuple[str, str, str], dict[str, Any]] = {}
    votos_por_candidato: defaultdict[tuple[str, str, str], int] = defaultdict(int)
    total_por_municipio_turno: defaultdict[tuple[str, str], int] = defaultdict(int)

    for row in reader:
        if row.get("SG_UF") != "RJ":
            continue
        if row.get("DS_CARGO", "").upper() != "PREFEITO":
            continue

        municipio = title_pt_br(row.get("NM_MUNICIPIO", ""))
        turno = row.get("NR_TURNO", "")
        candidato_id = row.get("SQ_CANDIDATO") or row.get("NR_CANDIDATO", "")
        key = (municipio, turno, candidato_id)
        votos = row_votes(row)

        total_por_municipio_turno[(municipio, turno)] += votos
        votos_por_candidato[key] += votos

        if key not in candidatos:
            candidatos[key] = {
                "municipio": municipio,
                "municipio_slug": slugify(municipio),
                "turno": parse_int(turno),
                "prefeito": title_pt_br(row.get("NM_CANDIDATO", "")),
                "nome_urna": title_pt_br(row.get("NM_URNA_CANDIDATO", "")),
                "partido": row.get("SG_PARTIDO", ""),
                "numero": row.get("NR_CANDIDATO", ""),
                "situacao": row.get("DS_SIT_TOT_TURNO", ""),
            }

    eleitos = []
    for key, candidato in candidatos.items():
        situacao = candidato["situacao"].upper()
        if situacao not in SITUACOES_ELEITO:
            continue

        municipio, turno, _ = key
        votos = votos_por_candidato[key]
        total_municipio = total_por_municipio_turno[(municipio, turno)]
        eleitos.append(
            {
                **candidato,
                "votos": votos,
                "total_votos_municipio": total_municipio,
                "percentual_municipio": round((votos / total_municipio) * 100, 4)
                if total_municipio
                else 0,
            }
        )

    municipios_com_eleito = {item["municipio_slug"] for item in eleitos}
    for caso in CASOS_SEM_ELEICAO_VALIDADA:
        if caso["municipio_slug"] not in municipios_com_eleito:
            eleitos.append(caso)

    return sorted(eleitos, key=lambda item: item["municipio"])


def escrever_csv(linhas: list[dict[str, Any]], output_path: Path) -> None:
    fieldnames = [
        "municipio",
        "prefeito",
        "nome_urna",
        "partido",
        "numero",
        "votos",
        "total_votos_municipio",
        "percentual_municipio",
        "situacao",
        "turno",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows([{key: linha[key] for key in fieldnames} for linha in linhas])


def escrever_json(linhas: list[dict[str, Any]], output_path: Path) -> None:
    prefeitos = []
    for linha in linhas:
        nome = linha["nome_urna"] or linha["prefeito"]
        prefeitos.append(
            {
                "municipio": linha["municipio"],
                "municipioSlug": linha["municipio_slug"],
                "nome": nome,
                "slug": slugify(nome),
                "prefeito": linha["prefeito"],
                "nomeUrna": linha["nome_urna"],
                "partido": linha["partido"],
                "numero": linha["numero"],
                "votos": linha["votos"],
                "totalVotosMunicipio": linha["total_votos_municipio"],
                "percentualMunicipio": linha["percentual_municipio"],
                "situacao": linha["situacao"],
                "turno": linha["turno"],
            }
        )

    payload = {
        "schemaVersion": "v1",
        "source": "TSE votacao_candidato_munzona_2024_RJ.csv",
        "criterio": "Prefeitos eleitos em 2024; percentual sobre total de votos nominais validos para prefeito no municipio e no turno em que o candidato foi eleito.",
        "total": len(prefeitos),
        "prefeitos": prefeitos,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, help="Zip local do TSE; se omitido, baixa da fonte oficial.")
    parser.add_argument("--out-csv", type=Path, default=OUTPUT_CSV)
    parser.add_argument("--out-json", type=Path, default=OUTPUT_JSON)
    args = parser.parse_args()

    linhas = gerar_linhas(load_csv_text(args.zip))
    escrever_csv(linhas, args.out_csv)
    escrever_json(linhas, args.out_json)

    print(f"CSV gerado: {args.out_csv}")
    print(f"JSON gerado: {args.out_json}")
    print(f"Prefeitos eleitos: {len(linhas)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
