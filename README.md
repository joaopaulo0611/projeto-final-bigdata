# DadosPro: datalake de tracking

Projeto final de engenharia de dados. Uma empresa vende um curso online por uma landing page, e cada interação do visitante (abrir a página, rolar, dar play no vídeo, comprar) vira um evento de tracking gravado num bucket S3 em arquivos JSON Lines.

O projeto constrói um datalake em arquitetura medalhão que transforma esses eventos em respostas de negócio:

- Bronze: cópia fiel do que chegou na landing, com a origem de cada linha.
- Silver: dado limpo, sem duplicatas, validado, com sessões e identidades resolvidas.
- Gold: tabelas agregadas que respondem às perguntas da empresa sobre funil, engajamento e receita.

Todas as camadas ficam no bucket datalake-tracking, em Parquet, gravadas pelo Spark com caminhos s3a://.

## Onde está cada coisa

| Arquivo ou pasta | O que é |
| --- | --- |
| RELATORIO.md | o relatório final: respostas às perguntas, com os números da Gold, e a seção de qualidade do dado |
| pipeline/ | o código PySpark: um job por camada e o script que roda todos em sequência |
| pipeline/README.md | como rodar o pipeline e o que cada job lê e grava |
| evidencias/ | prints de cada camada no S3, no catálogo, na execução dos jobs e no Athena, e o mapa de calor aceso no site |
| site/ | a landing page de exemplo; o botão Mapa de calor mostra a Gold de cliques e de rolagem |
| gerador/ | simula o coletor e popula a landing com 14 dias de eventos |
| docs/ | enunciado e contrato do evento |
| explorador/ | console local para ver o bucket, rodar os jobs e fazer consultas SQL |

## Os jobs

| Job | Lê | Grava |
| --- | --- | --- |
| bronze.py | landing/ | bronze/, append-only, com arquivo_origem e ingestao_ts |
| silver.py | bronze/ | silver/ (eventos válidos), silver/itens e silver/eventos_rejeitados |
| gold_funil.py | silver/ | gold/funil_compra e gold/funil_lead |
| gold_engajamento.py | silver/ | gold/sessoes, gold/retencao_video, gold/buscas_faq e gold/saidas_downloads |
| gold_receita.py | silver/ | gold/receita_diaria, gold/taxa_reembolso, gold/adesao_order_bump e gold/lead_para_compra |
| gold_mapa_calor.py | silver/ | gold/mapa_calor_cliques e gold/mapa_calor_rolagem |
| exportar_mapa_calor.py | gold/mapa_calor_* | site/mapa_calor.js |

O job Gold de ML (pergunta 4) foi dispensado pelo professor em sala. Por isso o pipeline tem sete jobs.

## Como rodar

Tudo roda nos contêineres Docker do projeto. Não é preciso instalar nada além do Docker. Na raiz do repositório:

```bash
docker compose up -d floci
docker compose run --rm app python gerador/gerar_eventos.py
docker compose run --rm app python pipeline/rodar_pipeline.py
```

O primeiro comando sobe o S3 local, o segundo popula a landing e o terceiro roda os sete jobs em ordem. Depois, abra site/index.html no navegador e clique em Mapa de calor, no painel lateral.

Para rodar um job sozinho:

```bash
docker compose run --rm app python pipeline/silver.py
```

Cada job confere se a camada anterior existe e, se não existir, para e diz qual job rodar antes.

A preparação do ambiente está explicada no SETUP.md.
