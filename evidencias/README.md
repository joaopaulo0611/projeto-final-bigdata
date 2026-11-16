# evidencias/

Prints tirados no explorador (`http://localhost:8501`) mostrando cada camada gravada no S3, catalogada, executada com sucesso e consultada no Athena. O código dos jobs está em pipeline/ e o relatório em RELATORIO.md, na raiz.

## bronze/

| Arquivo | O que mostra |
| --- | --- |
| 1_bucket.png | S3: s3://datalake-tracking/bronze/ |
| 2_catalogo_schema.png | Data Catalog: schema de bronze.eventos |
| 3_execucao.png | Jobs ETL: bronze com status Sucesso |
| 4_athena.png | consulta executada no Athena |
| resultado.csv | CSV gerado pela consulta do Athena |

## silver/

| Arquivo | O que mostra |
| --- | --- |
| 1_bucket.png | S3: s3://datalake-tracking/silver/ |
| 2_catalogo_banco.png | Data Catalog: tabelas do banco silver |
| 2_catalogo_schema.png | Data Catalog: schema de silver.eventos |
| 3_execucao_1.png | Jobs ETL: silver com status Sucesso |
| 3_execucao_2.png | continuação do log: rejeições, sessões e itens |
| 4_athena.png | consulta executada no Athena |
| resultado.csv | CSV gerado pela consulta do Athena |

O log da Silver nesses prints mostra 128.744 eventos na Bronze, o dobro das 64.372 linhas da landing, porque a Bronze (append-only) tinha rodado duas vezes. A deduplicação da Silver descartou as cópias e o resultado final é o mesmo: 61.813 eventos válidos.

## gold/

| Arquivo | O que mostra |
| --- | --- |
| 1_bucket_raiz.png | S3: as camadas do bucket datalake-tracking |
| 1_bucket_gold.png | S3: as tabelas em s3://datalake-tracking/gold/ |
| 2_catalogo_schema.png | Data Catalog: schema de gold.funil_compra |
| 3_execucao_gold_funil.png | Jobs ETL: gold_funil com status Sucesso |
| 3_execucao_gold_engajamento.png | Jobs ETL: gold_engajamento com status Sucesso |
| 3_execucao_gold_receita.png | Jobs ETL: gold_receita com status Sucesso |
| 3_execucao_gold_mapa_calor.png | Jobs ETL: gold_mapa_calor com status Sucesso |
| 4_athena.png | consulta executada no Athena |
| 5_mapa_calor_site.png | o site com o mapa de calor aceso (R11) |
| resultado.csv | CSV gerado pela consulta do Athena |
