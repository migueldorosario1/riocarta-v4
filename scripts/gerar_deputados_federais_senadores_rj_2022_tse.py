#!/usr/bin/env python3
"""Gera CSVs com deputados federais e senadores eleitos do RJ em 2022.

Fonte oficial:
https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2022.zip

Saidas padrao:
src/data/deputados_federais_eleitos_rj_2022.csv
src/data/senadores_eleitos_rj_2022.csv
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
OUTPUT_DEPUTADOS_FEDERAIS = PROJECT_ROOT / "src" / "data" / "deputados_federais_eleitos_rj_2022.csv"
OUTPUT_SENADORES = PROJECT_ROOT / "src" / "data" / "senadores_eleitos_rj_2022.csv"
JSON_DEPUTADOS_FEDERAIS = PROJECT_ROOT / "src" / "data" / "deputados_federais_eleitos_rj_2022.json"
JSON_SENADORES = PROJECT_ROOT / "src" / "data" / "senadores_eleitos_rj_2022.json"

SITUACOES_ELEITO = {"ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA", "ELEITO POR MEDIA"}


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


def processar_cargo(
    csv_text: str,
    *,
    cargo: str,
    coluna_pessoa: str,
) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=";")
    candidatos: dict[str, dict[str, Any]] = {}
    votos_por_candidato: defaultdict[str, int] = defaultdict(int)
    total_votos_estado = 0

    for row in reader:
        if row.get("SG_UF") != "RJ":
            continue
        if row.get("DS_CARGO", "").upper() != cargo.upper():
            continue

        votos = parse_int(row.get("QT_VOTOS_NOMINAIS"))
        total_votos_estado += votos

        candidato_id = row.get("SQ_CANDIDATO") or row["NR_CANDIDATO"]
        votos_por_candidato[candidato_id] += votos

        if candidato_id not in candidatos:
            candidatos[candidato_id] = {
                coluna_pessoa: row.get("NM_CANDIDATO", ""),
                "nome_urna": row.get("NM_URNA_CANDIDATO", ""),
                "partido": row.get("SG_PARTIDO", ""),
                "numero": row.get("NR_CANDIDATO", ""),
                "situacao": row.get("DS_SIT_TOT_TURNO", ""),
            }

    eleitos = []
    for candidato_id, candidato in candidatos.items():
        situacao = candidato["situacao"].upper()
        if situacao not in SITUACOES_ELEITO:
            continue

        votos = votos_por_candidato[candidato_id]
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

    return sorted(eleitos, key=lambda item: (-item["votos"], item[coluna_pessoa]))


def escrever_csv(linhas: list[dict[str, Any]], output_path: Path, coluna_pessoa: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        coluna_pessoa,
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


def escrever_json(
    linhas: list[dict[str, Any]],
    output_path: Path,
    *,
    coluna_pessoa: str,
    lista_key: str,
    criterio: str,
) -> None:
    pessoas = []
    for linha in linhas:
        nome = title_pt_br(linha["nome_urna"] or linha[coluna_pessoa])
        pessoas.append(
            {
                "nome": nome,
                "slug": slugify(nome),
                coluna_pessoa: title_pt_br(linha[coluna_pessoa]),
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
        "criterio": criterio,
        "total": len(pessoas),
        lista_key: pessoas,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, help="Zip local do TSE; se omitido, baixa da fonte oficial.")
    parser.add_argument("--out-deputados", type=Path, default=OUTPUT_DEPUTADOS_FEDERAIS)
    parser.add_argument("--out-senadores", type=Path, default=OUTPUT_SENADORES)
    parser.add_argument("--json-deputados", type=Path, default=JSON_DEPUTADOS_FEDERAIS)
    parser.add_argument("--json-senadores", type=Path, default=JSON_SENADORES)
    args = parser.parse_args()

    csv_text = load_csv_text(args.zip)

    deputados = processar_cargo(
        csv_text,
        cargo="DEPUTADO FEDERAL",
        coluna_pessoa="deputado_federal",
    )
    senadores = processar_cargo(
        csv_text,
        cargo="SENADOR",
        coluna_pessoa="senador",
    )

    escrever_csv(deputados, args.out_deputados, "deputado_federal")
    escrever_csv(senadores, args.out_senadores, "senador")
    escrever_json(
        deputados,
        args.json_deputados,
        coluna_pessoa="deputado_federal",
        lista_key="deputadosFederais",
        criterio="Deputados federais eleitos em 2022; percentual sobre total de votos nominais para deputado federal no RJ.",
    )
    escrever_json(
        senadores,
        args.json_senadores,
        coluna_pessoa="senador",
        lista_key="senadores",
        criterio="Senadores eleitos em 2022; percentual sobre total de votos nominais para senador no RJ.",
    )

    total_deputados = deputados[0]["total_votos_estado"] if deputados else 0
    total_senadores = senadores[0]["total_votos_estado"] if senadores else 0

    print(f"CSV gerado: {args.out_deputados}")
    print(f"JSON gerado: {args.json_deputados}")
    print(f"Deputados federais eleitos: {len(deputados)}")
    print(f"Total de votos nominais para deputado federal no RJ: {total_deputados}")
    print()
    print(f"CSV gerado: {args.out_senadores}")
    print(f"JSON gerado: {args.json_senadores}")
    print(f"Senadores eleitos: {len(senadores)}")
    print(f"Total de votos nominais para senador no RJ: {total_senadores}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
