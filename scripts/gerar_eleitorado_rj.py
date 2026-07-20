#!/usr/bin/env python3
import csv
import io
import json
import urllib.request
import zipfile
import re
import unicodedata
from pathlib import Path

TSE_ZIP_URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2024.zip"
CSV_NAME = "detalhe_votacao_munzona_2024_RJ.csv"
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_PATH = PROJECT_ROOT / "src" / "data" / "eleitores_rj_2024.json"

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

def main():
    print(f"Baixando {TSE_ZIP_URL}...")
    req = urllib.request.Request(
        TSE_ZIP_URL,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        raw_zip = response.read()
    
    print("Descompactando ZIP...")
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
        csv_text = archive.read(CSV_NAME).decode("latin-1")
    
    print("Processando CSV...")
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=";")
    
    # Vamos ver as colunas disponíveis para ter certeza
    fieldnames = reader.fieldnames
    print(f"Colunas do arquivo: {fieldnames}")
    
    # Agrupar por município
    # Como as linhas são por município, zona e cargo (e talvez turno), 
    # precisamos filtrar por um único cargo (e.g. PREFEITO ou CD_CARGO = 11) e turno (e.g. 1) 
    # para evitar duplicar QT_APTOS de uma mesma zona.
    eleitores_por_municipio = {}
    
    for row in reader:
        # Procurando identificar cargo de prefeito e primeiro turno
        cargo_cod = row.get("CD_CARGO")
        turno = row.get("NR_TURNO")
        
        # Filtros para pegar apenas uma ocorrência por zona de cada município
        if cargo_cod != "11":  # 11 é Prefeito
            continue
        if turno != "1":       # Primeiro turno
            continue
            
        mun = title_pt_br(row.get("NM_MUNICIPIO", ""))
        mun_slug = slugify(mun)
        aptos = int(row.get("QT_APTOS", 0))
        comparecimento = int(row.get("QT_COMPARECIMENTO", 0))
        abstencoes = int(row.get("QT_ABSTENCOES", 0))
        
        if mun_slug not in eleitores_por_municipio:
            eleitores_por_municipio[mun_slug] = {
                "municipio": mun,
                "municipioSlug": mun_slug,
                "eleitores": 0,
                "comparecimento": 0,
                "abstencoes": 0
            }
        
        eleitores_por_municipio[mun_slug]["eleitores"] += aptos
        eleitores_por_municipio[mun_slug]["comparecimento"] += comparecimento
        eleitores_por_municipio[mun_slug]["abstencoes"] += abstencoes

    # Escrever no JSON de saída
    output_data = {
        "fonte": TSE_ZIP_URL,
        "criterio": "Soma de QT_APTOS de detalhe_votacao_munzona_2024_RJ.csv filtrando por CD_CARGO=11 e NR_TURNO=1",
        "eleitorado": eleitores_por_municipio
    }
    
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
        
    print(f"JSON gerado em {OUTPUT_PATH}")
    
    # Mostrar os dados de Maricá para validar
    if "marica" in eleitores_por_municipio:
        print(f"Validação de Maricá: {eleitores_por_municipio['marica']}")
    else:
        print("Maricá não encontrado!")

if __name__ == "__main__":
    main()
