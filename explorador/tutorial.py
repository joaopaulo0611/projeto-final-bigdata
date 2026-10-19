"""Tutorial do console: um tour em modal por tela, que destaca cada elemento e explica para que serve.

Cada roteiro é uma lista de passos (seletor CSS do elemento, título e texto). Os seletores usam as
classes `st-key-<chave>` que o Streamlit põe nos elementos com `key`. Sem Streamlit aqui: só dados.
O "não mostrar mais" é gravado pelo módulo `preferencias`.
"""

from __future__ import annotations

from dataclasses import dataclass

TELA_S3 = "S3 · Buckets"
TELA_CATALOGO = "Glue · Data Catalog"
TELA_JOBS = "Glue · Jobs ETL"
TELA_WORKFLOWS = "Glue · Workflows"
TELA_ATHENA = "Athena · Editor de consultas"

MENU = '[data-testid="stSidebar"] [role="radiogroup"]'
ABAS = '[data-testid="stTabs"] [role="tablist"]'


@dataclass(frozen=True)
class Passo:
    seletor: str | None      # None: balão no centro da tela, sem destaque
    titulo: str
    texto: str


def _k(chave: str) -> str:
    return f'[class*="st-key-{chave}"]'


ROTEIROS: dict[str, list[Passo]] = {
    "s3-buckets": [
        Passo(None, "Bem-vindo ao console do datalake",
              "Este console imita o da AWS para você treinar o fluxo do mercado, mas tudo roda no seu computador: "
              "o floci faz o papel do S3, o Spark do contêiner o do Glue e o DuckDB o do Athena. "
              "Este tour mostra para que serve cada parte da tela. Use Próximo e Anterior, ou feche quando quiser."),
        Passo(".barra-console", "Barra do console",
              "Mostra o bucket, o endereço do S3 local e a região. Também lembra a regra de ouro: o Athena só lê; "
              "só as telas de Jobs ETL e Workflows executam código."),
        Passo(MENU, "Serviços",
              "O menu lateral leva às cinco telas: Buckets (os arquivos), Data Catalog (as tabelas), "
              "Jobs ETL (rodar um job), Workflows (rodar vários jobs em ordem) e Editor de consultas (SQL). "
              "Cada tela tem o seu próprio tour."),
        Passo(_k("painel-buckets"), "Lista de buckets",
              "Um bucket é um \"disco\" do S3. Aqui aparecem todos os buckets do floci, só para leitura. O do projeto é "
              "o datalake-tracking, o único que alimenta o Data Catalog e o Athena. Clique no nome dele para ver "
              "as pastas landing/, bronze/, silver/ e gold/."),
        Passo(_k("recarregar"), "Recarregar",
              "Depois de rodar um job, clique aqui para o console ler o bucket de novo e enxergar as pastas e colunas novas."),
        Passo(_k("dock"), "Ajuda e acessibilidade",
              "Esta barra fica sempre no canto inferior direito. 🎓 abre o tour da tela em que você estiver; "
              "a chave \"Mostrar tutorial\" desliga os tours automáticos; ♿ abre as opções de acessibilidade "
              "(tamanho do texto, alto contraste, links sublinhados, espaçamento e menos movimento); "
              "⬆ volta ao topo da página."),
    ],
    "s3-bucket": [
        Passo(_k("trilha-s3"), "Caminho (breadcrumb)",
              "Mostra onde você está: Buckets › datalake-tracking › pasta › subpasta. Clique em qualquer parte para voltar."),
        Passo(ABAS, "Abas do bucket",
              "Objetos lista pastas e arquivos; Partições resume os dados por evento e por dia; Propriedades mostra a "
              "visão geral do bucket."),
        Passo(_k("painel-objetos"), "Objetos",
              "Pastas (📁) e arquivos (📄) da pasta atual, com tipo, data e tamanho. As pastas event_name=…, year=…, "
              "month=… e day=… são as partições. Clique numa pasta para entrar."),
        Passo(_k("painel-objetos"), "Prévia de um arquivo",
              "Clique num arquivo .jsonl ou .parquet: as primeiras 100 linhas aparecem logo abaixo, em formato de tabela. "
              "É a forma mais rápida de conferir o que o seu job gravou."),
    ],
    "catalogo-bancos": [
        Passo(_k("painel-bancos"), "Bancos de dados",
              "O Data Catalog é a lista do que existe no lake. Aqui há um banco por camada do medalhão: landing, bronze, "
              "silver e gold, no bucket do datalake, e um banco para cada outro bucket do floci, com o nome dele. "
              "Clique num banco para ver as tabelas dele."),
        Passo(_k("trilha-catalogo"), "Caminho",
              "Glue › Data Catalog › banco › tabela. Clique em Data Catalog para voltar à lista de bancos."),
    ],
    "catalogo-tabelas": [
        Passo(_k("painel-tabelas"), "Tabelas do banco",
              "Cada pasta com dados vira uma tabela: nome, formato (Parquet ou JSON), localização no S3, quantas partições "
              "e quantas colunas. Clique no nome para ver o esquema."),
    ],
    "catalogo-tabela": [
        Passo(_k("painel-tabela-visao"), "Visão geral da tabela",
              "Onde os arquivos ficam, o formato, as chaves de partição e o nome para usar no Athena (banco.tabela)."),
        Passo(ABAS, "Esquema e partições",
              "Esquema: as colunas e os tipos (as chaves de partição vêm marcadas). Partições: uma linha por partição, "
              "com arquivos e tamanho."),
        Passo(_k("consultar_athena"), "Consultar no Athena",
              "Abre uma consulta nova no editor, já com SELECT * FROM banco.tabela LIMIT 10."),
    ],
    "jobs-lista": [
        Passo(_k("sincronizar-jobs"), "Sincronizar",
              "Os jobs e workflows rodam a partir do floci, do bucket glue-assets, como no Glue, onde os scripts ficam no S3. "
              "Depois de criar ou editar arquivos em pipeline/, clique em Sincronizar: ele envia o que é novo ou mudou "
              "e tira do floci o que você apagou. Passe o mouse no botão para ver o que está esperando."),
        Passo(_k("painel-jobs"), "Seus jobs",
              "Cada script .py que está no floci (menos o comum.py) é um job. A tabela mostra o status e o início da "
              "última execução. Clique no nome para abrir o job. Com mais de 8 jobs, aparece a caixa Localizar "
              "para filtrar a lista pelo nome."),
        Passo(_k("trilha-jobs"), "Caminho",
              "Glue › Jobs ETL › job. Clique em Jobs ETL para voltar à lista depois de abrir um job."),
    ],
    "jobs-detalhe": [
        Passo(_k("executar_job"), "Executar",
              "Baixa o script do floci e roda no Spark do contêiner, como docker compose run --rm app python pipeline/<job>.py. "
              "Enquanto ele roda, o botão fica desligado: um job por vez."),
        Passo(_k("painel-execucoes"), "Execuções",
              "Cada execução com status (Em execução, Sucesso ou Falhou), início, duração e código de saída. "
              "Enquanto o job roda, esta tabela se atualiza sozinha."),
        Passo(_k("painel-log"), "Log",
              "Tudo o que o job imprimiu. Se a execução falhar, o motivo quase sempre está nas últimas linhas."),
        Passo(ABAS, "Script",
              "A aba Script mostra o código que está no floci (só leitura). Para mudar o job, edite o arquivo em "
              "pipeline/ no seu editor e clique em Sincronizar."),
    ],
    "workflows-lista": [
        Passo(_k("sincronizar-workflows"), "Sincronizar",
              "Os jobs e workflows rodam a partir do floci, do bucket glue-assets, como no Glue, onde os scripts ficam no S3. "
              "Depois de criar ou editar arquivos em pipeline/, clique em Sincronizar: ele envia o que é novo ou mudou "
              "e tira do floci o que você apagou. Passe o mouse no botão para ver o que está esperando."),
        Passo(None, "Workflows",
              "Um workflow junta vários jobs num grafo: cada job diz de quais outros depende. Ao executar, o console "
              "roda cada job assim que as dependências dele terminam com sucesso, como se você rodasse um depois do outro, "
              "mas jobs independentes podem rodar ao mesmo tempo."),
        Passo(_k("criar_workflow"), "Criar workflow",
              "Abre o formulário: você dá um nome, escolhe os jobs e diz de quem cada um depende. O workflow vai para "
              "o floci e ganha uma cópia em pipeline/workflows/, para não se perder quando o floci reiniciar."),
        Passo(_k("painel-workflows"), "Seus workflows",
              "Cada linha é um workflow, com quantos jobs tem e o status da última execução. Clique no nome para abrir."),
    ],
    "workflows-detalhe": [
        Passo(_k("executar_workflow"), "Executar",
              "Começa uma execução nova do workflow inteiro. Enquanto ela roda, o botão fica desligado e aparece o "
              "botão Parar: ele não começa jobs novos, e os que já rodam terminam."),
        Passo(_k("painel-grafo"), "Grafo",
              "Cada caixa é um job e cada seta diz \"este roda depois daquele\". As cores mostram o status na "
              "execução escolhida: azul rodando, verde sucesso, vermelho falhou, tracejado não executado."),
        Passo(_k("painel-etapas"), "Etapas",
              "A mesma informação do grafo em tabela: dependências, status, início e duração de cada job. "
              "Escolha uma etapa logo abaixo para ver o log dela."),
        Passo(ABAS, "Histórico e definição",
              "Histórico lista todas as execuções do workflow. Definição mostra o arquivo .json e onde ele fica."),
    ],
    "workflows-form": [
        Passo(_k("wf_form_nome"), "Nome",
              "Letras minúsculas, números, _ ou -. Vira o nome do arquivo: workflows/<nome>.json."),
        Passo(_k("wf_form_jobs"), "Jobs do workflow",
              "Escolha os jobs da pasta que fazem parte do workflow, na ordem em que você pensa neles."),
        Passo(_k("painel-dependencias"), "Dependências",
              "Para cada job, marque de quais outros ele depende. Um job sem dependências começa logo. "
              "Ciclos (A espera B e B espera A) não são aceitos."),
        Passo(_k("wf_form_paralelo"), "Jobs ao mesmo tempo",
              "Quantos jobs independentes podem rodar juntos. Cada um abre um Spark: mais de 2 pode faltar memória."),
        Passo(_k("painel-previa"), "Prévia",
              "O grafo vai se desenhando enquanto você preenche. Se algo estiver errado, o aviso aparece aqui."),
    ],
    "athena": [
        Passo(_k("painel-athena-dados"), "Dados",
              "Escolha o banco de dados e veja as tabelas dele. Abra uma tabela para ver as colunas; Inserir no editor "
              "escreve banco.tabela na sua consulta."),
        Passo(_k("athena_banco"), "Banco de dados",
              "Os mesmos bancos do Data Catalog: landing, bronze, silver e gold, e um para cada outro bucket. "
              "Uma consulta pode juntar tabelas de buckets diferentes."),
        Passo(_k("painel-athena-editor"), "Editor de consultas",
              "Escreva a SQL aqui. As abas Consulta 1, Consulta 2… guardam consultas diferentes; ＋ abre uma nova e ✕ "
              "fecha a atual. Só são aceitas consultas de leitura."),
        Passo(_k("executar"), "Executar e limite",
              "Executar roda a consulta. O limite diz quantas linhas trazer (padrão 1 000, máximo 50 000)."),
        Passo(_k("painel-athena-resultados"), "Resultados e consultas recentes",
              "Depois de executar: status, tempo, linhas e dados lidos (estimado). Filtrar por event_name diminui os dados "
              "lidos, como no Athena de verdade. A aba Consultas recentes guarda o histórico desta sessão."),
    ],
}


def roteiro(contexto: str) -> list[Passo]:
    return ROTEIROS.get(contexto, [])
