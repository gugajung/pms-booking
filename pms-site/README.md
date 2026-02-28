# GeoSlope Lab (MVP)

Aplicação web para análise preliminar de estabilidade de taludes, inspirada no fluxo de trabalho do Slide2.

## Entregas do MVP

- Interface web para entrada de geometria e parâmetros geotécnicos
- Busca de superfície circular crítica
- Cálculo de fator de segurança por Bishop simplificado
- Visualização da superfície crítica em canvas
- Geração de laudo em HTML (pronto para imprimir/salvar em PDF)

## Como executar

```bash
cd /Users/gustavojung/Documents/teste\ codex
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 pms-site/app.py
```

Abra: `http://127.0.0.1:5000`

## Observação técnica

Este projeto é um MVP para estudo e prototipação. Não substitui validação de engenharia, revisão técnica independente ou uso de software comercial certificado para decisões de projeto.
