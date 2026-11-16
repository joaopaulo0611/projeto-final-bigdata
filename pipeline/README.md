# pipeline/

Código PySpark do datalake: um job por camada e um script que roda todos em sequência. Todo acesso ao S3 é feito pelo Spark, com caminhos s3a://datalake-tracking/..., sem boto3.

## Os jobs

| Job | Lê | Grava |
| --- | --- | --- |
| bronze.py | landing/ | bronze/event_name=…/year=…/month=…/day=…, append-only, com arquivo_origem e ingestao_ts |
| silver.py | bronze/ | silver/event_name=…, silver/itens e silver/eventos_rejeitados |
| gold_funil.py | silver/ | gold/funil_compra e gold/funil_lead |
| gold_engajamento.py | silver/ | gold/sessoes, gold/retencao_video, gold/buscas_faq e gold/saidas_downloads |
| gold_receita.py | silver/ | gold/receita_diaria, gold/taxa_reembolso, gold/adesao_order_bump e gold/lead_para_compra |
| gold_mapa_calor.py | silver/ | gold/mapa_calor_cliques e gold/mapa_calor_rolagem |
| exportar_mapa_calor.py | gold/mapa_calor_* | site/mapa_calor.js |
| rodar_pipeline.py | | roda os sete jobs acima, nesta ordem |
| comum.py | | funções compartilhadas: SparkSession, caminhos, leitura e gravação das partições, verificação de camada |

O job Gold de ML foi dispensado pelo professor.

O que cada job faz:

- Bronze: lê a landing com schema explícito, acrescenta a proveniência (arquivo_origem e ingestao_ts) e grava em modo append, particionado por evento e dia de coleta.
- Silver: remove duplicatas por event_id, valida cada evento e manda os inválidos para eventos_rejeitados com o motivo, calcula as sessões pela regra dos 30 minutos (sem usar session_hint), faz o identity stitching do user_id, extrai params para colunas tipadas e explode items na tabela itens.
- Gold funil: funil de compra por plano e canal, com conversão sobre a etapa anterior e sobre o topo, e funil de lead por canal.
- Gold engajamento: uma linha por sessão, retenção do vídeo, buscas no FAQ, saídas e downloads.
- Gold receita: receita bruta, reembolsada e líquida por dia, plano e canal, taxa de reembolso, adesão ao order bump e conversão de lead em compra. O reembolso é atribuído à compra pelo transaction_id.
- Gold mapa de calor: cliques por elemento e alcance da rolagem na landing.
- Exportar mapa de calor: lê as duas tabelas do mapa de calor e grava site/mapa_calor.js para o site desenhar o mapa.

## Como rodar

Na raiz do repositório, com o Docker instalado:

```bash
docker compose up -d floci
docker compose run --rm app python gerador/gerar_eventos.py
docker compose run --rm app python pipeline/rodar_pipeline.py
```

O primeiro comando sobe o S3 local (floci). O segundo popula a landing e só é necessário se ela estiver vazia. O terceiro roda os sete jobs em ordem e para no primeiro que falhar. Ele não gera dados.

Para rodar um job sozinho:

```bash
docker compose run --rm app python pipeline/<job>.py
```

Cada job confere se a camada de que depende existe. Se não existir, ele para com uma mensagem dizendo o que rodar antes. Por exemplo, um job Gold sem a Silver pede para rodar python pipeline/silver.py.

Os jobs também podem ser rodados pelo explorador: suba com docker compose up -d explorador, abra `http://localhost:8501`, vá em Glue, Jobs ETL, clique em Sincronizar e execute os jobs na ordem bronze, silver e depois os gold.

## Observações

- A Bronze é append-only. Rodar o pipeline de novo acrescenta outra cópia da landing à Bronze. A deduplicação da Silver descarta essa cópia, então a Silver e a Gold saem iguais, mas o número de duplicatas removidas que a Silver imprime cresce. Para recomeçar do zero, recrie o contêiner do floci (docker compose up -d --force-recreate floci) e rode o gerador de novo.
- A Silver grava com overwrite dinâmico de partições, para não apagar silver/itens e silver/eventos_rejeitados, que ficam ao lado das pastas event_name=.
- A SparkSession desliga a inferência de tipo das partições, para manter month=09 e day=03 com dois dígitos.
- O Spark 4 usa o modo ANSI. A Silver converte os valores de params com try_cast e as taxas da Gold usam try_divide, para que um valor sujo vire nulo em vez de derrubar o job.
- site/mapa_calor.js é gerado pelo job de exportação e não entra no git.
