# Pipeline

Pipeline do datalake de tracking, em três camadas: **Bronze**, **Silver** e **Gold**.

## Conteúdo da pasta

```
Entrega/
├── README.md         ← este arquivo: como rodar
├── RELATORIO.md      ← respostas às perguntas e qualidade do dado
├── comum.py          ← funções prontas que os jobs importam
├── rodar_pipeline.py ← roda todos os jobs em sequência (R3)
├── bronze/
│   ├── 1_bucket.png            ← S3: s3://datalake-tracking/bronze/
│   ├── 2_catalogo_schema.png   ← Data Catalog: schema de bronze.eventos
│   ├── 3_execucao.png          ← Jobs ETL: bronze com status Sucesso
│   ├── 4_athena.png            ← consulta executada no Athena
│   ├── resultado.csv           ← CSV gerado pelo Athena
│   └── bronze.py               ← o job ETL
├── silver/
│   ├── 1_bucket.png            ← S3: s3://datalake-tracking/silver/
│   ├── 2_catalogo_banco.png    ← Data Catalog: tabelas do banco silver
│   ├── 2_catalogo_schema.png   ← Data Catalog: schema de silver.eventos
│   ├── 3_execucao_1.png        ← Jobs ETL: silver com status Sucesso
│   ├── 3_execucao_2.png        ← continuação do log (rejeições, sessões, itens)
│   ├── 4_athena.png            ← consulta executada no Athena
│   ├── resultado.csv           ← CSV gerado pelo Athena
│   └── silver.py               ← o job ETL
└── gold/
    ├── 1_bucket_raiz.png                 ← S3: as camadas do datalake-tracking
    ├── 1_bucket_gold.png                 ← S3: as tabelas em s3://datalake-tracking/gold/
    ├── 2_catalogo_schema.png             ← Data Catalog: schema de gold.funil_compra
    ├── 3_execucao_gold_funil.png         ← Jobs ETL: gold_funil com status Sucesso
    ├── 3_execucao_gold_engajamento.png   ← Jobs ETL: gold_engajamento com status Sucesso
    ├── 3_execucao_gold_receita.png       ← Jobs ETL: gold_receita com status Sucesso
    ├── 3_execucao_gold_mapa_calor.png    ← Jobs ETL: gold_mapa_calor com status Sucesso
    ├── 4_athena.png                      ← consulta executada no Athena
    ├── 5_mapa_calor_site.png             ← site com o mapa de calor aceso (R11)
    ├── resultado.csv                     ← CSV gerado pelo Athena
    ├── gold_funil.py                     ← os jobs ETL
    ├── gold_engajamento.py
    ├── gold_receita.py
    ├── gold_mapa_calor.py
    └── exportar_mapa_calor.py
```

## Os jobs

| Job | Lê | Grava |
| --- | --- | --- |
| `bronze.py` | `landing/` (JSONL) | `bronze/event_name=…/year=…/month=…/day=…` em Parquet, append-only, com `arquivo_origem` e `ingestao_ts` |
| `silver.py` | `bronze/` | `silver/event_name=…/year=…/month=…/day=…` (eventos válidos), `silver/itens/` e `silver/eventos_rejeitados/` |
| `gold_funil.py` | `silver/` | `gold/funil_compra`, `gold/funil_lead` |
| `gold_engajamento.py` | `silver/` | `gold/sessoes`, `gold/retencao_video`, `gold/buscas_faq`, `gold/saidas_downloads` |
| `gold_receita.py` | `silver/` | `gold/receita_diaria`, `gold/taxa_reembolso`, `gold/adesao_order_bump`, `gold/lead_para_compra` |
| `gold_mapa_calor.py` | `silver/` | `gold/mapa_calor_cliques`, `gold/mapa_calor_rolagem` |
| `exportar_mapa_calor.py` | `gold/mapa_calor_*` | `site/mapa_calor.js` (R11) |

**Bronze:**
- lê a landing com schema explícito;
- acrescenta a proveniência (`arquivo_origem` e `ingestao_ts`);
- grava em modo `append`, particionado por evento e dia.

**Silver:**
- remove duplicatas por `event_id`;
- valida cada evento e manda os inválidos para `eventos_rejeitados`, com o motivo;
- calcula as sessões pela regra dos 30 minutos;
- faz o identity stitching do `user_id`;
- extrai os parâmetros de `params` para colunas;
- explode `items` na tabela `itens`.

**Gold:** uma tabela por pergunta de negócio, todas lidas da Silver.
- `gold_funil`: funil de compra por plano e canal, e funil de lead;
- `gold_engajamento`: uma linha por sessão, retenção do vídeo, buscas no FAQ, saídas e downloads;
- `gold_receita`: receita bruta, reembolsada e líquida por dia, plano e canal, taxa de reembolso, adesão ao order bump e conversão de lead em compra. O reembolso é atribuído à compra pelo `transaction_id`;
- `gold_mapa_calor`: cliques por elemento e alcance da rolagem na landing;
- `exportar_mapa_calor`: grava `site/mapa_calor.js` para o site desenhar o mapa de calor.

O job Gold de ML foi dispensado pelo professor.

## Como rodar

Tudo roda nos contêineres Docker do projeto. Não é preciso instalar nada além do Docker.

```bash
docker compose up -d floci                                      # S3 local
docker compose run --rm app python gerador/gerar_eventos.py     # popula a landing
docker compose run --rm app python pipeline/rodar_pipeline.py
```

O `rodar_pipeline.py` roda os sete jobs na ordem da tabela e para no primeiro que falhar. Cada job também pode ser rodado sozinho:

```bash
docker compose run --rm app python pipeline/<job>.py
```

Os jobs também podem ser rodados pelo explorador:
1. Suba o explorador com `docker compose up -d explorador` e abra `http://localhost:8501`.
2. Vá em **Glue · Jobs ETL** e clique em **⟳ Sincronizar**.
3. Execute os jobs na ordem: `bronze`, `silver` e depois os jobs `gold_*`. Foi assim que os prints de execução foram tirados.

Cada job confere se a camada anterior existe antes de começar (R2). Se a Silver não existir, por exemplo, um job Gold para com a mensagem "Rode antes: python pipeline/silver.py".

**A Bronze é append-only.** Se ela rodar duas vezes, a landing entra duas vezes. Por isso o log da Silver em `silver/3_execucao_1.png` mostra 128.744 eventos na Bronze, o dobro das 64.372 linhas da landing. A deduplicação da Silver descarta essas cópias, então os números finais da Silver não mudam. Para recomeçar do zero, reinicie o floci e rode o gerador de novo.
