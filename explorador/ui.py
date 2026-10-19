"""Peças visuais do console (CSS e componentes), no estilo de um console de nuvem (sem marcas).

O Streamlit põe a classe `st-key-<chave>` em todo contêiner com `key`; o CSS abaixo usa isso para
desenhar tabelas, painéis e faixas iguais aos do console, sem depender de componentes externos.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import streamlit as st

from explorador import tipos

# Paleta: barra superior #232f3e, laranja #ff9900, azul de link #006ce0, textos #0f141a/#424650/#656871.
CSS = """
<style>
  html, body, .stApp, .stMarkdown, button, input, textarea, select {
    font-family: "Helvetica Neue", Roboto, Arial, sans-serif; }
  .stApp { background: #ffffff; color: #0f141a; }

  /* cabeçalho do Streamlit: transparente, logo abaixo da barra; ficam só os botões do menu lateral */
  [data-testid="stHeader"] { background: transparent !important; top: 44px !important; height: 2.5rem !important; }
  [data-testid="stToolbarActions"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"],
  [data-testid="stDecoration"], [data-testid="stHeaderActionElements"], #MainMenu, footer { display: none !important; }
  .block-container { padding-top: 4.2rem !important; padding-bottom: 3rem !important; max-width: 1320px; }

  /* barra superior */
  .barra-console { position: fixed; top: 0; left: 0; right: 0; z-index: 1000002; height: 44px;
    background: #232f3e; color: #fff; display: flex; align-items: center; gap: 18px; padding: 0 20px;
    font-size: .875rem; border-bottom: 1px solid #414d5c; }
  .barra-console .marca { color: #ff9900; font-weight: 800; font-size: 1rem; letter-spacing: .01em; }
  .barra-console .servicos { color: #fff; font-weight: 700; border-left: 1px solid #414d5c; padding-left: 18px; }
  .barra-console .detalhe { margin-left: auto; color: #d1d5db; font-size: .8125rem; }
  .barra-console .regiao { color: #fff; font-weight: 700; border-left: 1px solid #414d5c; padding-left: 18px; }
  .barra-console span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  @media (max-width: 760px) { .barra-console span:not(.marca) { display: none; } }

  /* menu lateral (navegação de serviços) */
  [data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #c6c6cd;
    top: 44px !important; height: calc(100vh - 44px) !important; }
  [data-testid="stSidebarHeader"] { height: 2.2rem; padding: 0 8px; }
  .menu-titulo { font-size: 1.125rem; font-weight: 700; color: #0f141a; padding: 0 0 6px 2px; }
  [data-testid="stSidebar"] [role="radiogroup"] { gap: 0; }
  [data-testid="stSidebar"] [role="radiogroup"] > div { display: block; width: 100%; }
  [data-testid="stSidebar"] [data-testid="stRadioOption"] { width: 100%; margin: 0; padding: 7px 12px 7px 14px;
    border-left: 3px solid transparent; cursor: pointer; }
  [data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:first-child { display: none; }
  [data-testid="stSidebar"] [data-testid="stRadioOption"] p { font-size: .875rem; color: #424650; }
  [data-testid="stSidebar"] [data-testid="stRadioOption"]:hover p { color: #006ce0; }
  [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] { border-left-color: #006ce0; background: #f0f7ff; }
  [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p { color: #006ce0; font-weight: 700; }
  [data-testid="stSidebar"] [role="radiogroup"] > div::before { display: block; font-size: .75rem; font-weight: 700;
    color: #656871; text-transform: uppercase; letter-spacing: .04em; padding: 12px 0 4px 2px; }
  [data-testid="stSidebar"] [role="radiogroup"] > div:nth-child(1)::before { content: "S3"; padding-top: 2px; }
  [data-testid="stSidebar"] [role="radiogroup"] > div:nth-child(2)::before { content: "Glue"; }
  [data-testid="stSidebar"] [role="radiogroup"] > div:nth-child(5)::before { content: "Athena"; }

  /* títulos de página, breadcrumb, textos de apoio */
  .pag-titulo { font-size: 1.5rem; font-weight: 700; color: #0f141a; line-height: 1.3; margin: 2px 0 2px; }
  .pag-titulo .contador { color: #656871; font-weight: 400; }
  .pag-desc { color: #656871; font-size: .875rem; margin-bottom: 8px; }
  .trilha-sep { color: #656871; font-size: .875rem; }
  .trilha-atual { color: #656871; font-size: .875rem; }
  [class*="st-key-trilha"] button p { font-size: .875rem !important; }

  /* botões: primário laranja, normal com contorno azul, link azul */
  .stButton button, .stDownloadButton button { border-radius: 20px; font-weight: 700; }
  .stButton button[kind="primary"], .stDownloadButton button[kind="primary"] {
    background: #ff9900; border: 2px solid #ff9900; color: #0f141a; }
  .stButton button[kind="primary"]:hover { background: #fa6f00; border-color: #fa6f00; color: #0f141a; }
  .stButton button[kind="primary"]:disabled { background: #ebebf0; border-color: #ebebf0; color: #9ba7b6; }
  .stButton button[kind="secondary"], .stDownloadButton button[kind="secondary"] {
    background: #fff; border: 2px solid #006ce0; color: #006ce0; }
  .stButton button[kind="secondary"]:hover { background: #f0fbff; border-color: #002b66; color: #002b66; }
  .stButton button[kind="tertiary"] { color: #006ce0; font-weight: 400; padding: 0; min-height: 0;
    justify-content: flex-start; text-align: left; border-radius: 0; }
  .stButton button[kind="tertiary"]:hover { color: #002b66; text-decoration: underline; }
  .stButton button[kind="tertiary"] p { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  /* painéis (contêineres do console) */
  [class*="st-key-painel-"] { border: none !important; border-radius: 16px !important; background: #fff;
    box-shadow: 0 1px 1px 1px #e9ebed, 0 6px 36px rgba(0, 7, 22, .10); padding: 14px 20px 16px !important; }
  .painel-titulo { font-size: 1.125rem; font-weight: 700; color: #0f141a; }
  .painel-titulo .contador { color: #656871; font-weight: 400; }
  .painel-desc { color: #656871; font-size: .875rem; margin-top: -4px; }

  /* tabelas do console */
  [class*="st-key-tabcab-"] { border-bottom: 1px solid #c6c6cd; padding: 6px 0 4px; }
  [class*="st-key-tablinha-"] { border-bottom: 1px solid #ebebf0; padding: 3px 0; }
  [class*="st-key-tablinha-"]:hover { background: #f6f6f9; }
  [class*="st-key-tabcab-"] [data-testid="stMarkdownContainer"] p,
  [class*="st-key-tablinha-"] [data-testid="stMarkdownContainer"] p { margin: 0; }
  /* o título quebra linha quando não cabe na coluna (em vez de invadir a vizinha) */
  .tab-titulo { font-weight: 700; color: #424650; font-size: .875rem; display: block; line-height: 1.25;
                white-space: normal; overflow-wrap: break-word; }
  .tab-texto { font-size: .875rem; color: #0f141a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; }
  [class*="st-key-tablinha-"] [data-testid="stMarkdown"], [class*="st-key-tabcab-"] [data-testid="stMarkdown"],
  [class*="st-key-tablinha-"] [data-testid="stMarkdownContainer"], [class*="st-key-tabcab-"] [data-testid="stMarkdownContainer"] {
    margin: 0 !important; min-height: 1.3rem; }
  [class*="st-key-tablinha-"] .stButton button { min-height: 0; height: auto; line-height: 1.5; }
  [class*="st-key-tablinha-"] .stButton button p { font-size: .875rem; line-height: 1.5; margin: 0; }
  [class*="st-key-tablinha-"] .tab-texto, [class*="st-key-tablinha-"] .selo { line-height: 1.5; }
  .tab-vazio { text-align: center; color: #656871; padding: 18px 0; font-size: .875rem; }

  /* selos de status */
  .selo { font-size: .875rem; white-space: nowrap; }
  .selo-ok { color: #00802f; } .selo-erro { color: #db0000; } .selo-run { color: #006ce0; } .selo-neutro { color: #656871; }

  /* pares rótulo/valor (visão geral) */
  .kv { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 14px 24px; margin-top: 6px; }
  .kv-rotulo { color: #656871; font-size: .8125rem; font-weight: 700; }
  .kv-valor { color: #0f141a; font-size: .875rem; word-break: break-all; }

  /* abas */
  [data-testid="stTabs"] [role="tablist"] { border-bottom: 1px solid #c6c6cd; }
  [data-testid="stTab"] p { font-weight: 700; color: #424650; font-size: .9375rem; }
  [data-testid="stTab"][aria-selected="true"] p { color: #006ce0; }

  /* tipo struct: palavra curta em azul que abre a tipagem interna num overlay */
  [class*="st-key-struct-"] button { color: #006ce0 !important; padding: 0 !important; min-height: 0 !important;
    font-weight: 400 !important; font-size: .875rem; }
  [class*="st-key-struct-"] button:hover { color: #002b66 !important; text-decoration: underline; }
  [data-testid="stPopoverBody"]:has(.tipagem-titulo) { max-width: 360px; }
  .tipagem-titulo { font-weight: 700; font-size: .9375rem; color: #0f141a; }
  .tipagem-resumo { color: #656871; font-weight: 400; }
  [data-testid="stPopoverBody"]:has(.tipagem-titulo) li { margin: 0; font-size: .875rem; }
  [class*="st-key-arvcol-"] { gap: 6px !important; }
  [class*="st-key-arvcol-"] .tab-texto { color: #656871; }
  [class*="st-key-arvcol-"] [data-testid="stMarkdownContainer"] p { margin: 0; }

  /* árvore de dados do Athena */
  [data-testid="stExpander"] details { border-radius: 8px; border-color: #e9ebed; }
  [data-testid="stExpander"] summary p { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: .875rem; }

  /* editor SQL: fonte de código e calha à esquerda, como o editor do Athena */
  .stTextArea textarea { font-family: Monaco, Menlo, Consolas, "Courier New", monospace; font-size: .875rem;
    line-height: 1.55; padding-left: 52px !important; border-radius: 8px;
    background: linear-gradient(to right, #f6f6f9 0, #f6f6f9 40px, #e9ebed 40px, #e9ebed 41px, #fff 41px) local; }

  /* tutorial: o botão que grava "não mostrar mais" fica escondido; os scripts (tour e acessibilidade) não ocupam espaço */
  [class*="st-key-tour-desligar"], [class*="st-key-script-"] { display: none !important; }

  /* botões flutuantes no canto inferior direito: topo, tutorial e o menu ♿ (tutorial e acessibilidade) */
  .st-key-dock { position: fixed; right: 20px; bottom: 20px; z-index: 1000005; width: 44px !important;
    gap: 10px; align-items: center; background: transparent; }
  .st-key-dock [data-testid="stPopover"], .st-key-dock [data-testid="stPopover"] div,
  .st-key-dock [data-testid="stPopover"] span, .st-key-dock .stButton { width: 44px !important; }
  .st-key-dock button { width: 44px !important; height: 44px; min-height: 44px; padding: 0 !important;
    border-radius: 50% !important; border: 1px solid #e9ebed !important; background: #fff !important;
    color: #0f141a !important; box-shadow: 0 2px 10px rgba(0, 7, 22, .14); justify-content: center; }
  .st-key-dock button p { font-size: 1.15rem !important; margin: 0; }
  .st-key-dock button:hover { border-color: #006ce0 !important; box-shadow: 0 2px 14px rgba(0, 108, 224, .25); }
  .st-key-dock [data-testid="stPopoverButton"] [data-testid="stIconMaterial"] { display: none; }   /* sem a setinha */
  .st-key-topo { transition: opacity .2s ease; }
  html.topo-escondido .st-key-topo { opacity: 0; pointer-events: none; }
  [data-testid="stPopoverBody"] { min-width: 300px; }

  /* "Pular para o conteúdo": o primeiro Tab da página; invisível até o teclado chegar nele */
  #pular-conteudo { position: fixed; left: 12px; top: -60px; background: #fff; color: #0f141a !important;
    padding: 8px 14px; border-radius: 8px; font-weight: 700; z-index: 1000020; text-decoration: underline; }
  #pular-conteudo:focus { top: 6px; }

  /* foco do teclado sempre visível */
  .stApp :focus-visible, #tour-raiz :focus-visible { outline: 3px solid #006ce0 !important; outline-offset: 2px; }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important;
      transition: none !important; scroll-behavior: auto !important; } }

  /* faixa de aviso (flashbar) */
  [class*="st-key-flash"] { background: #006ce0; border-radius: 12px; padding: 10px 16px !important; margin-bottom: 8px; }
  [class*="st-key-flash"] p, [class*="st-key-flash"] span { color: #fff !important; }
  [class*="st-key-flash"] .stButton button { background: transparent; border: 2px solid #fff; color: #fff; }
  [class*="st-key-flash"] .stButton button:hover { background: rgba(255,255,255,.15); }
  [class*="st-key-flash"] .stButton button[kind="tertiary"] { border: none; text-decoration: underline; }
</style>
"""


@dataclass
class Link:
    """Célula clicável (nome em azul, como os links das tabelas do console)."""
    rotulo: str
    chave: str
    on_click: Callable | None = None
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)


@dataclass
class Tipo:
    """Célula com o tipo de uma coluna: struct aparece curto e abre a tipagem interna num overlay."""
    coluna: str
    tipo: str
    chave: str


@dataclass
class Html:
    conteudo: str


def _slug(texto: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", texto).strip("-")


def _texto(celula: Any) -> str:
    if isinstance(celula, Link):
        return celula.rotulo
    if isinstance(celula, Tipo):
        return tipos.curto(celula.tipo)
    if isinstance(celula, Html):
        return re.sub(r"<[^>]+>", "", celula.conteudo)
    return str(celula)


def titulo(texto: str, contador: int | None = None, descricao: str | None = None) -> None:
    extra = f' <span class="contador">({contador})</span>' if contador is not None else ""
    st.markdown(f'<div class="pag-titulo" role="heading" aria-level="1">{html.escape(texto)}{extra}</div>',
                unsafe_allow_html=True)
    if descricao:
        st.markdown(f'<div class="pag-desc">{descricao}</div>', unsafe_allow_html=True)


def trilha(itens: list[tuple[str, str | None, Callable | None, dict]], chave: str) -> None:
    """Breadcrumb: (rótulo, chave do botão, on_click, kwargs). O último item, sem chave, é a página atual."""
    linha = st.container(horizontal=True, vertical_alignment="center", gap="small", key=f"trilha-{chave}")
    for i, (rotulo, chave_botao, ao_clicar, kwargs) in enumerate(itens):
        if chave_botao:
            linha.button(rotulo, key=chave_botao, type="tertiary", on_click=ao_clicar, kwargs=kwargs or {})
        else:
            linha.markdown(f'<span class="trilha-atual" aria-current="page">{html.escape(rotulo)}</span>', width="content",
                           unsafe_allow_html=True)
        if i < len(itens) - 1:
            linha.markdown('<span class="trilha-sep" aria-hidden="true">›</span>', width="content", unsafe_allow_html=True)


def painel(chave: str, titulo_painel: str | None = None, contador: int | None = None,
           descricao: str | None = None):
    caixa = st.container(border=True, key=f"painel-{_slug(chave)}")
    if titulo_painel:
        extra = f' <span class="contador">({contador})</span>' if contador is not None else ""
        caixa.markdown(f'<div class="painel-titulo" role="heading" aria-level="2">{html.escape(titulo_painel)}{extra}</div>',
                       unsafe_allow_html=True)
    if descricao:
        caixa.markdown(f'<div class="painel-desc">{descricao}</div>', unsafe_allow_html=True)
    return caixa


def selo(status: str) -> Html:
    classes = {"Sucesso": ("selo-ok", "✔"), "Concluída": ("selo-ok", "✔"), "Falhou": ("selo-erro", "✖"),
               "Em execução": ("selo-run", "⟳")}
    classe, icone = classes.get(status, ("selo-neutro", "–"))
    return Html(f'<span class="selo {classe}"><span aria-hidden="true">{icone}</span> {html.escape(status)}</span>')


def pares(dados: dict[str, str]) -> None:
    """Visão geral: rótulos cinza com o valor embaixo, em grade (como "Detalhes" no console)."""
    itens = "".join(f'<div><div class="kv-rotulo">{html.escape(k)}</div><div class="kv-valor">{html.escape(str(v))}</div></div>'
                    for k, v in dados.items())
    st.markdown(f'<div class="kv">{itens}</div>', unsafe_allow_html=True)


def tipo(alvo, coluna: str, tipo_completo: str, chave: str) -> None:
    """Tipo de uma coluna. Um struct inteiro não cabe na tela: aparece só `struct` (ou `struct[]`, `map(…, struct)`)
    e o clique abre um overlay com a tipagem interna em árvore."""
    resumo = tipos.curto(tipo_completo)
    if not tipos.tem_struct(tipo_completo):
        alvo.markdown(f'<span class="tab-texto">{html.escape(resumo)}</span>', unsafe_allow_html=True)
        return
    with alvo.popover(resumo, type="tertiary", key=f"struct-{_slug(chave)}",
                      help=f"Ver a tipagem interna de {coluna}"):
        st.markdown(f'<div class="tipagem-titulo" role="heading" aria-level="3">Tipagem interna de '
                    f'<code>{html.escape(coluna)}</code> <span class="tipagem-resumo">{html.escape(resumo)}</span></div>',
                    unsafe_allow_html=True)
        if resumo.startswith("struct[]"):
            explica = (f"Uma lista de structs: cada linha guarda vários itens, e cada item tem os campos abaixo. "
                       f"No SQL, abra a lista com unnest({coluna}).")
        elif resumo.startswith("map("):
            explica = "Um mapa de chave para valor; o valor é um struct com os campos abaixo."
        else:
            explica = (f"Um struct é como uma ficha dentro da linha: guarda vários campos, cada um com nome e tipo. "
                       f"No SQL, leia um campo com ponto: {coluna}.campo.")
        st.caption(explica)
        st.markdown(tipos.arvore_markdown(tipo_completo))


def tabela(chave: str, colunas: list[tuple[str, float]], linhas: list[list[Any]],
           localizar: bool = False, vazio: str = "Nenhum item.") -> int:
    """Tabela do console: cabeçalho, linhas com divisória, nomes clicáveis e (opcional) caixa "Localizar".

    Devolve quantas linhas foram mostradas (depois do filtro)."""
    if localizar:
        termo = st.text_input("Localizar", key=f"busca:{chave}", placeholder="Localizar…",
                              label_visibility="collapsed")
        if termo:
            linhas = [l for l in linhas if termo.lower() in " ".join(_texto(c) for c in l).lower()]
    pesos = [peso for _, peso in colunas]
    # "grade-…": o script de acessibilidade marca este bloco como tabela (linhas, cabeçalhos e células)
    with st.container(key=f"grade-{_slug(chave)}"):
        with st.container(key=f"tabcab-{_slug(chave)}"):
            for coluna, (nome, _) in zip(st.columns(pesos, gap="small", vertical_alignment="center"), colunas):
                coluna.markdown(f'<span class="tab-titulo">{html.escape(nome)}</span>', unsafe_allow_html=True)
        if not linhas:
            st.markdown(f'<div class="tab-vazio" role="status">{vazio}</div>', unsafe_allow_html=True)
            return 0
        for i, linha in enumerate(linhas):
            with st.container(key=f"tablinha-{_slug(chave)}-{i}"):
                for coluna, celula in zip(st.columns(pesos, gap="small", vertical_alignment="center"), linha):
                    if isinstance(celula, Link):
                        coluna.button(celula.rotulo, key=celula.chave, type="tertiary", on_click=celula.on_click,
                                      args=celula.args, kwargs=celula.kwargs)
                    elif isinstance(celula, Tipo):
                        tipo(coluna, celula.coluna, celula.tipo, celula.chave)
                    elif isinstance(celula, Html):
                        coluna.markdown(celula.conteudo, unsafe_allow_html=True)
                    else:
                        coluna.markdown(f'<span class="tab-texto">{html.escape(str(celula))}</span>', unsafe_allow_html=True)
    return len(linhas)


# ------------------------------------------------------------------ tour ------------------------------------------------------------------

def _script(chave: str, codigo: str) -> None:
    """Roda um <script> nosso num iframe invisível (mesma origem: ele mexe na página do console pelo window.parent).

    Só código escrito aqui entra: o st.iframe executa o HTML como está."""
    with st.container(key=f"script-{chave}"):
        st.iframe(codigo, height=1)


_TOUR_JS = r"""
<script>
(function () {
  const P = window.parent, D = P.document;
  const cfg = __CONFIG__;
  const store = (() => { try { return P.sessionStorage; } catch (e) { return null; } })();
  const lido = (k) => { try { return store ? store.getItem(k) : null; } catch (e) { return null; } };
  const grava = (k, v) => { try { store && store.setItem(k, v); } catch (e) {} };

  if (!cfg.passos.length) return;
  const chaveVisto = "tour-visto:" + cfg.contexto, chaveForca = "tour-forca";
  const forcado = cfg.forcar && lido(chaveForca) !== String(cfg.forcar);
  if (!forcado && (!cfg.auto || lido(chaveVisto))) return;
  if (cfg.forcar) grava(chaveForca, String(cfg.forcar));
  if (D.getElementById("tour-raiz")) return;           // já aberto

  const css = D.createElement("style");
  css.id = "tour-css";
  css.textContent = `
    #tour-raiz { position: fixed; inset: 0; z-index: 1000010; pointer-events: none; }
    #tour-raiz .fundo { position: fixed; inset: 0; background: rgba(15,20,26,.55); pointer-events: auto; }
    #tour-raiz .foco { position: fixed; border-radius: 10px; box-shadow: 0 0 0 9999px rgba(15,20,26,.55);
      outline: 3px solid #ff9900; transition: all .2s ease; pointer-events: none; }
    #tour-raiz .balao { position: fixed; width: min(380px, calc(100vw - 32px)); background: #fff; color: #0f141a;
      border-radius: 16px; box-shadow: 0 8px 40px rgba(0,7,22,.35); padding: 18px 20px 14px; pointer-events: auto;
      font: .875rem/1.5 "Helvetica Neue",Roboto,Arial,sans-serif; }
    #tour-raiz .contagem { color: #656871; font-size: .75rem; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }
    #tour-raiz h3 { margin: 4px 0 6px; font-size: 1.125rem; font-weight: 700; }
    #tour-raiz p { margin: 0 0 12px; color: #424650; }
    #tour-raiz .acoes { display: flex; gap: 8px; align-items: center; }
    #tour-raiz button { border-radius: 20px; font: 700 .875rem/1 inherit; padding: 8px 16px; cursor: pointer; }
    #tour-raiz .prox { background: #ff9900; border: 2px solid #ff9900; color: #0f141a; margin-left: auto; }
    #tour-raiz .ant { background: #fff; border: 2px solid #006ce0; color: #006ce0; }
    #tour-raiz .fechar { position: absolute; top: 10px; right: 12px; background: none; border: none; font-size: 1.125rem;
      color: #656871; padding: 4px 8px; }
    #tour-raiz .nunca { display: flex; gap: 6px; align-items: center; margin-top: 10px; color: #656871; font-size: .8125rem; }
  `;
  D.head.appendChild(css);
  const raiz = D.createElement("div");
  raiz.id = "tour-raiz";
  raiz.innerHTML = `<div class="fundo"></div><div class="foco"></div>
    <div class="balao" role="dialog" aria-modal="true" tabindex="-1"
         aria-labelledby="tour-titulo" aria-describedby="tour-contagem tour-texto">
      <button class="fechar" title="Fechar o tutorial" aria-label="Fechar o tutorial">✕</button>
      <div aria-live="polite"><div class="contagem" id="tour-contagem"></div><h3 id="tour-titulo"></h3><p id="tour-texto"></p></div>
      <div class="acoes"><button class="ant">Anterior</button><button class="prox">Próximo</button></div>
      <label class="nunca"><input type="checkbox"> Não mostrar mais o tutorial</label>
    </div>`;
  D.body.appendChild(raiz);
  const fundo = raiz.querySelector(".fundo"), foco = raiz.querySelector(".foco"), balao = raiz.querySelector(".balao");
  let i = 0, alvo = null;

  // acessibilidade do modal: o resto da página some para o leitor de tela, o foco fica dentro do balão
  // (Tab e Shift+Tab dão a volta) e, ao fechar, volta para onde estava
  const antes = D.activeElement, app = D.getElementById("root");
  if (app) app.setAttribute("aria-hidden", "true");
  balao.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const itens = [...balao.querySelectorAll("button, input")].filter((b) => b.offsetParent && b.style.visibility !== "hidden");
    const primeiro = itens[0], ultimo = itens[itens.length - 1];
    if (e.shiftKey && (D.activeElement === primeiro || D.activeElement === balao)) { e.preventDefault(); ultimo.focus(); }
    else if (!e.shiftKey && D.activeElement === ultimo) { e.preventDefault(); primeiro.focus(); }
  });

  function posicionar() {
    const vw = P.innerWidth, vh = P.innerHeight, bw = balao.offsetWidth, bh = balao.offsetHeight;
    if (!alvo) {
      foco.style.display = "none"; fundo.style.display = "block";
      balao.style.left = ((vw - bw) / 2) + "px"; balao.style.top = ((vh - bh) / 2) + "px";
      return;
    }
    const r = alvo.getBoundingClientRect(), m = 6;
    foco.style.display = "block"; fundo.style.display = "none";
    foco.style.left = (r.left - m) + "px"; foco.style.top = (r.top - m) + "px";
    foco.style.width = (r.width + 2 * m) + "px"; foco.style.height = (r.height + 2 * m) + "px";
    let top = r.bottom + 14;
    if (top + bh > vh - 8) top = r.top - bh - 14;              // sem espaço embaixo: em cima
    if (top < 52) top = Math.min(vh - bh - 8, Math.max(52, r.top + 14));
    let left = r.left;
    if (r.width < bw) left = r.left + r.width / 2 - bw / 2;
    left = Math.max(12, Math.min(left, vw - bw - 12));
    balao.style.left = left + "px"; balao.style.top = top + "px";
  }

  function mostrar(n) {
    i = n;
    const passo = cfg.passos[i];
    alvo = passo.seletor ? D.querySelector(passo.seletor) : null;
    if (alvo && (alvo.getBoundingClientRect().width === 0)) alvo = null;     // escondido: balão no centro
    if (alvo) alvo.scrollIntoView({ block: "center", behavior: "instant" });
    balao.querySelector(".contagem").textContent = "Passo " + (i + 1) + " de " + cfg.passos.length;
    balao.querySelector("h3").textContent = passo.titulo;
    balao.querySelector("p").textContent = passo.texto;
    balao.querySelector(".ant").style.visibility = i === 0 ? "hidden" : "visible";
    balao.querySelector(".prox").textContent = i === cfg.passos.length - 1 ? "Concluir" : "Próximo";
    requestAnimationFrame(posicionar);
    setTimeout(posicionar, 80);                                 // também sem animação (aba em segundo plano)
    if (n === 0) balao.focus({ preventScroll: true });          // ao abrir, o leitor de tela lê título e texto; depois, a região viva anuncia
  }

  function fechar() {
    grava(chaveVisto, "1");
    P.removeEventListener("resize", posicionar);
    P.removeEventListener("scroll", posicionar, true);
    raiz.remove(); css.remove();
    if (app) app.removeAttribute("aria-hidden");
    if (antes && antes.isConnected && antes.focus) antes.focus({ preventScroll: true });   // o foco volta para onde estava
    if (balao.querySelector(".nunca input").checked) {
      const botao = D.querySelector('[class*="st-key-tour-desligar"] button');
      if (botao) botao.click();                                 // avisa o Python: grava "tutorial": false
    }
  }

  balao.querySelector(".prox").onclick = () => (i < cfg.passos.length - 1 ? mostrar(i + 1) : fechar());
  balao.querySelector(".ant").onclick = () => i > 0 && mostrar(i - 1);
  balao.querySelector(".fechar").onclick = fechar;
  D.addEventListener("keydown", function esc(e) { if (e.key === "Escape" && D.getElementById("tour-raiz")) { fechar(); D.removeEventListener("keydown", esc); } });
  P.addEventListener("resize", posicionar);
  P.addEventListener("scroll", posicionar, true);
  setTimeout(() => mostrar(0), 350);                           // espera a tela terminar de desenhar
})();
</script>
"""


def tour(contexto: str, passos: list, auto: bool, forcar: int = 0) -> None:
    """Tour em modal: escurece a tela, destaca cada elemento e explica para que ele serve.

    `auto`: abre sozinho na primeira visita a esta tela (nesta aba do navegador).
    `forcar`: um número que muda a cada clique em "Abrir tutorial desta tela" (abre mesmo já visto)."""
    config = {"contexto": contexto, "auto": auto, "forcar": forcar,
              "passos": [{"seletor": p.seletor, "titulo": p.titulo, "texto": p.texto} for p in passos]}
    _script("tour", _TOUR_JS.replace("__CONFIG__", json.dumps(config, ensure_ascii=False)))


def css_acessibilidade(escolhas: dict) -> str:
    """CSS das opções de acessibilidade escolhidas na barra flutuante (o texto do Streamlit é em rem)."""
    conteudo = '[data-testid="stMain"] .block-container, [data-testid="stSidebar"], .st-key-dock, [data-testid="stPopoverBody"]'
    regras = [f"html {{ font-size: {int(escolhas.get('texto', 100))}% !important; }}"]
    if escolhas.get("contraste"):
        regras += [
            f":is({conteudo}) :is(p, span, label, li, div.tab-texto, div.kv-valor):not(button *, .barra-console *)"
            " {{ color: #000 !important; }}",
            ".pag-desc, .painel-desc, .kv-rotulo, .trilha-sep, .trilha-atual, .contador, .tab-titulo, .tab-vazio,"
            ' [data-testid="stCaptionContainer"], .selo-neutro { color: #000 !important; }',
            '.stButton button[kind="tertiary"] p, [data-testid="stTab"][aria-selected="true"] p,'
            ' [data-testid="stRadioOption"][data-selected="true"] p { color: #003b8f !important; }',
            '.stButton button[kind="secondary"], .st-key-dock button'
            " { border-color: #003b8f !important; color: #003b8f !important; }",
            ".selo-ok { color: #005c1f !important; } .selo-erro { color: #a30000 !important; }"
            " .selo-run { color: #003b8f !important; }",
            '[class*="st-key-tablinha-"], [class*="st-key-tabcab-"], [data-testid="stTabs"] [role="tablist"]'
            " { border-bottom-color: #000 !important; }",
            '[class*="st-key-painel-"], .st-key-dock button { box-shadow: 0 0 0 2px #000 !important; }',
            'input, textarea, [data-baseweb="select"] > div { border: 2px solid #000 !important; }',
            "#tour-raiz .balao p, #tour-raiz .contagem, #tour-raiz .nunca { color: #000 !important; }",
        ]
    if escolhas.get("sublinhar"):
        regras.append('.stButton button[kind="tertiary"] p, .stApp a, [data-testid="stRadioOption"] p'
                      " { text-decoration: underline !important; text-underline-offset: 3px; }")
    if escolhas.get("espacamento"):
        regras.append(f":is({conteudo}, #tour-raiz) :is(p, span, label, li, div.tab-texto, div.kv-valor, h3)"
                      " { letter-spacing: .12em !important; word-spacing: .16em !important; line-height: 1.6 !important; }")
    if escolhas.get("movimento"):
        regras.append("*, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important;"
                      " transition: none !important; scroll-behavior: auto !important; }")
    return "<style>\n" + "\n".join(regras) + "\n</style>"


_APOIO_JS = r"""
<script>
(function () {
  const P = window.parent, D = P.document, cfg = __CONFIG__;
  const $ = (s, r) => (r || D).querySelector(s), $$ = (s, r) => [...(r || D).querySelectorAll(s)];
  const marca = (el, attrs) => { if (!el) return; for (const [k, v] of Object.entries(attrs)) if (el.getAttribute(k) !== v) el.setAttribute(k, v); };

  // quem rola a página no Streamlit é o contêiner principal, não a janela
  const rolador = () => [$('[data-testid="stMain"]'), $('[data-testid="stAppViewContainer"]')]
    .find((e) => e && e.scrollHeight > e.clientHeight + 4) || D.scrollingElement;

  // botões só com ícone: o leitor de tela lê o nome, não o desenho do emoji
  const NOMES = { ".st-key-topo button": "Voltar ao topo da página",
                  ".st-key-tour-abrir button": "Abrir o tutorial desta tela",
                  '.st-key-dock [data-testid="stPopoverButton"]': "Tutorial e acessibilidade",
                  ".st-key-nova_aba button": "Nova consulta",
                  ".st-key-fechar_aba button": "Fechar esta consulta",
                  '[data-testid="stSidebarCollapseButton"] button': "Recolher o menu de serviços",
                  '[data-testid="stExpandSidebarButton"]': "Abrir o menu de serviços" };

  // sobe do filho até o pai sem papel definido no meio: as divs do Streamlit viram "none" para o leitor
  // de tela enxergar tabela → linha → célula
  function semPapelEntre(filho, pai) {
    for (let e = filho.parentElement; e && e !== pai; e = e.parentElement) if (!e.getAttribute("role")) e.setAttribute("role", "none");
  }

  function estruturar() {
    D.documentElement.lang = "pt-BR";                                 // leitores de tela leem em português
    if (!D.getElementById("pular-conteudo")) {                        // fora do React: é o primeiro item do Tab
      const pular = D.createElement("a");
      pular.id = "pular-conteudo"; pular.href = "#conteudo"; pular.textContent = "Pular para o conteúdo";
      D.body.insertBefore(pular, D.body.firstChild);
    }
    // regiões da página: topo, menu e conteúdo (com o alvo do "Pular para o conteúdo")
    marca($(".barra-console"), { role: "banner" });
    marca($('[data-testid="stSidebar"]'), { role: "navigation", "aria-label": "Menu de serviços" });
    marca($('[data-testid="stMain"]'), { role: "main", id: "conteudo", tabindex: "-1" });
    marca($(".st-key-dock"), { role: "complementary", "aria-label": "Ajuda e acessibilidade" });
    for (const t of $$('[class*="st-key-trilha-"]')) marca(t, { role: "navigation", "aria-label": "Caminho" });
    for (const [s, nome] of Object.entries(NOMES)) { const b = $(s); if (b) { marca(b, { "aria-label": nome }); if (b.title !== nome) b.title = nome; } }

    // tabelas do console: cabeçalho e linhas viram uma tabela de verdade para o leitor de tela
    for (const grade of $$('[class*="st-key-grade-"]')) {
      const painel = grade.closest('[class*="st-key-painel-"]');
      const nome = painel && $(".painel-titulo", painel) ? $(".painel-titulo", painel).textContent.trim() : "Tabela";
      marca(grade, { role: "table", "aria-label": nome });
      for (const linha of $$('[class*="st-key-tabcab-"], [class*="st-key-tablinha-"]', grade)) {
        const cabecalho = String(linha.className).includes("st-key-tabcab-");
        marca(linha, { role: "row" }); semPapelEntre(linha, grade);
        for (const celula of $$('[data-testid="stColumn"]', linha)) {
          marca(celula, { role: cabecalho ? "columnheader" : "cell" }); semPapelEntre(celula, linha);
        }
      }
    }
    // o que muda sozinho é anunciado sem roubar o foco: execuções do job e resultado da consulta
    for (const s of ['[class*="st-key-painel-execucoes"]', '[class*="st-key-painel-athena-resultados"]'])
      for (const e of $$(s)) marca(e, { "aria-live": "polite" });

    // o botão Topo some no começo da página: some também para o teclado e o leitor de tela
    const longe = rolador().scrollTop > 240;
    D.documentElement.classList.toggle("topo-escondido", !longe);   // no html: o React reescreve a classe do contêiner
    const topo = $(".st-key-topo button");
    if (topo) { topo.tabIndex = longe ? 0 : -1; marca(topo, { "aria-hidden": longe ? "false" : "true" }); }
  }

  function clique(e) {
    const alvo = e.target.closest ? e.target : null;
    if (alvo && alvo.closest("#pular-conteudo")) {                   // "Pular para o conteúdo"
      e.preventDefault(); const m = $("#conteudo"); if (m) m.focus(); return;
    }
    if (!alvo || !alvo.closest(".st-key-topo button")) return;
    e.preventDefault(); e.stopPropagation();                          // só rola: não precisa recarregar a tela
    const suave = !cfg.reduzirMovimento && !P.matchMedia("(prefers-reduced-motion: reduce)").matches;
    rolador().scrollTo({ top: 0, behavior: suave ? "smooth" : "auto" });
    const titulo = $(".pag-titulo");                                   // o foco volta para o começo da página
    if (titulo) { titulo.tabIndex = -1; titulo.focus({ preventScroll: true }); }
  }

  // o Streamlit redesenha a tela a cada clique: refaz as marcações quando a página muda
  let pendente = null;
  const agendar = () => { if (!pendente) pendente = setTimeout(() => { pendente = null; estruturar(); }, 120); };

  // a cada nova versão deste script, troca os ouvintes antigos pelos novos
  const antigo = P.__apoioConsole;
  if (antigo) {
    D.removeEventListener("click", antigo.clique, true); D.removeEventListener("scroll", antigo.estruturar, true);
    antigo.observador.disconnect();
  }
  const observador = new MutationObserver(agendar);
  observador.observe(D.body, { childList: true, subtree: true });
  P.__apoioConsole = { clique, estruturar, observador };
  D.addEventListener("click", clique, true);
  D.addEventListener("scroll", estruturar, true);
  estruturar(); setTimeout(estruturar, 400);
})();
</script>
"""


def apoio_acessibilidade(reduzir_movimento: bool) -> None:
    """Script de acessibilidade na página: idioma pt-BR, regiões (topo, menu, conteúdo), tabelas que o leitor
    de tela entende, nomes nos botões só com ícone, avisos do que muda sozinho e o botão "Topo"."""
    config = {"reduzirMovimento": bool(reduzir_movimento)}
    _script("apoio", _APOIO_JS.replace("__CONFIG__", json.dumps(config)))
