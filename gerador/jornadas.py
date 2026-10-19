"""Máquina de estados da jornada na landing DadosPro.

Uma sessão percorre a página na ordem das seções: hero → vídeo → módulos →
tabela de planos → e-book → FAQ → rodapé. Cada passo é uma chance; canal e
dispositivo mudam as chances. Um visitante tem de uma a quatro sessões em
dias diferentes; quem virou lead volta com mais intenção de compra, e quem
comprou volta para a área de membros.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlparse

from gerador import catalogo as cat
from gerador.eventos import Contexto, criar_evento, hex8, item, ler_iso

P_RECARGA = 0.25          # chance de um page_view ser recarga completa (novo session_hint)
P_REEMBOLSO = 0.12         # base; o fator_reembolso do canal ajusta. ~8% observado (compras da última semana perdem o reembolso fora da janela)


@dataclass
class Sessao:
    rng: random.Random
    ctx: Contexto
    agora: datetime
    eventos: list[dict] = field(default_factory=list)

    def chance(self, p: float) -> bool:
        return self.rng.random() < min(p, 0.98)

    def emitir(self, nome: str, params: dict | None = None, items: list | None = None,
               segundos: float | None = None) -> dict:
        self.agora += timedelta(seconds=segundos if segundos is not None else self.rng.uniform(2, 40))
        evento = criar_evento(self.rng, nome, self.agora, self.ctx, params, items)
        self.eventos.append(evento)
        return evento

    def abrir(self, pagina: str, recarga: bool = False) -> dict:
        if recarga and self.ctx.pagina is not None:
            self.ctx.referrer = cat.PAGINAS[self.ctx.pagina]
            self.ctx.session_hint = "s-" + hex8(self.rng)
        elif self.ctx.pagina is None:
            self.ctx.referrer = self.ctx.canal["referrer"]
        else:
            self.ctx.referrer = cat.PAGINAS[self.ctx.pagina]
            if self.chance(P_RECARGA):
                self.ctx.session_hint = "s-" + hex8(self.rng)
        self.ctx.pagina = pagina
        return self.emitir("page_view", {"page_title": f"{cat.TITULO} · {pagina}"})


@dataclass
class ResultadoSessao:
    eventos: list[dict]
    compra: dict | None
    fez_lead: bool


def _valor(carrinho: list[dict]) -> float:
    return round(sum(i["price"] * i["quantity"] for i in carrinho), 2)


def _monetario(carrinho: list[dict], **extra) -> dict:
    return {"currency": cat.MOEDA, "value": _valor(carrinho), **extra}


def _video(s: Sessao) -> None:
    base = dict(cat.VIDEO)
    duracao = base["video_duration"]
    s.emitir("video_start", {**base, "video_current_time": 0, "video_percent": 0})
    anterior = 0
    for marco, p in cat.RETENCAO_VIDEO:
        if not s.chance(p):
            return
        s.emitir("video_progress", {**base, "video_current_time": duracao * marco // 100, "video_percent": marco},
                 segundos=duracao * (marco - anterior) / 100)
        anterior = marco
    if s.chance(cat.P_VIDEO_COMPLETO):
        s.emitir("video_complete", {**base, "video_current_time": duracao, "video_percent": 100},
                 segundos=duracao * (100 - anterior) / 100)


def _funil_compra(s: Sessao, fator: float) -> tuple[dict | None, bool]:
    """Da tabela de planos até a compra. Devolve (purchase ou None, saiu_da_landing)."""
    rng = s.rng
    if not s.chance(0.35 * fator):
        return None, False
    idx = rng.choices(range(len(cat.PLANOS)), weights=cat.PESOS_PLANO)[0]
    plano = cat.PLANOS[idx]
    s.emitir("select_item", dict(cat.LISTA), [item(plano, index=idx, **cat.LISTA)])
    if s.chance(0.60):
        s.emitir("view_item", {"currency": cat.MOEDA, "value": plano["price"]}, [item(plano)])
    if not s.chance(0.75):
        return None, False

    s.emitir("add_to_cart", {"currency": cat.MOEDA, "value": plano["price"]}, [item(plano)])
    if s.chance(0.10):
        outro = rng.choice([p for p in cat.PLANOS if p is not plano])
        s.emitir("remove_from_cart", {"currency": cat.MOEDA, "value": plano["price"]}, [item(plano)])
        s.emitir("add_to_cart", {"currency": cat.MOEDA, "value": outro["price"]}, [item(outro)])
        plano = outro
    carrinho = [item(plano)]

    s.abrir("checkout")
    s.emitir("view_cart", _monetario(carrinho), list(carrinho))
    if s.chance(0.25):
        carrinho.append(item(cat.BUMP))
        s.emitir("add_to_cart", {"currency": cat.MOEDA, "value": cat.BUMP["price"]}, [item(cat.BUMP)])
        if s.chance(0.30):
            carrinho.pop()
            s.emitir("remove_from_cart", {"currency": cat.MOEDA, "value": cat.BUMP["price"]}, [item(cat.BUMP)])
    if not s.chance(0.70):
        return None, True
    s.emitir("begin_checkout", _monetario(carrinho), list(carrinho))

    frete = 0.0
    if plano["item_id"] == cat.PREMIUM:
        if not s.chance(0.90):
            return None, True
        tier = rng.choices(tuple(cat.FRETE), weights=cat.PESOS_FRETE)[0]
        frete = cat.FRETE[tier]
        s.emitir("add_shipping_info", _monetario(carrinho, shipping_tier=tier, shipping=frete), list(carrinho))

    if not s.chance(0.75 * fator ** 0.5):
        return None, True
    tipo = rng.choices(cat.PAGAMENTOS, weights=cat.PESOS_PAGAMENTO)[0]
    s.emitir("add_payment_info", _monetario(carrinho, payment_type=tipo), list(carrinho))
    if not s.chance(0.85):
        return None, True

    bruto = _valor(carrinho)
    valor = round(bruto - round(bruto * cat.DESCONTO_PIX, 2), 2) if tipo == "pix" else bruto
    compra = s.emitir("purchase", {
        "transaction_id": "T-" + hex8(rng).upper(),
        "value": valor,
        "tax": round(valor * cat.ALIQUOTA_ISS, 2),
        "shipping": frete,
        "currency": cat.MOEDA,
        "payment_type": tipo,
        "coupon": "PIX5" if tipo == "pix" else None,
    }, list(carrinho))
    s.abrir("obrigado")
    if s.chance(0.60):
        s.abrir("membros")
        s.ctx.user_id = "u-" + hex8(rng)
        s.emitir("sign_up", {"method": "email"})
    return compra, True


def simular_sessao(rng: random.Random, ctx: Contexto, inicio: datetime,
                   intencao: float = 1.0, ja_e_lead: bool = False) -> ResultadoSessao:
    s = Sessao(rng, ctx, inicio)
    fs = ctx.dispositivo["fator_scroll"]
    fator = ctx.canal["fator_compra"] * ctx.dispositivo["fator_compra"] * intencao

    s.abrir("landing")
    if s.chance(P_RECARGA):
        s.abrir("landing", recarga=True)
    if s.chance(0.30):
        s.emitir("click", {"link_url": cat.BASE_URL + "/#planos", "link_text": "Ver planos",
                           "link_id": "hero_ver_planos", "outbound": False})
    alcance = 0
    if s.chance(0.85 * fs):
        s.emitir("scroll", {"percent_scrolled": 25})
        alcance = 25
    if alcance >= 25 and s.chance(0.40):
        _video(s)
    if alcance >= 25 and s.chance(0.75 * fs):
        s.emitir("scroll", {"percent_scrolled": 50})
        alcance = 50
    if alcance >= 50 and s.chance(0.06):
        s.emitir("file_download", dict(cat.EMENTA))
    if alcance >= 50 and s.chance(0.70 * fs):
        s.emitir("scroll", {"percent_scrolled": 75})
        alcance = 75

    compra, saiu = None, False
    if alcance >= 50 and s.chance(0.90):
        s.emitir("view_item_list", dict(cat.LISTA),
                 [item(p, index=i, **cat.LISTA) for i, p in enumerate(cat.PLANOS)])
        compra, saiu = _funil_compra(s, fator)

    fez_lead = False
    if not saiu:
        if alcance >= 50 and not ja_e_lead and s.chance(0.12):
            s.emitir("generate_lead", {"lead_source": cat.LEAD_SOURCE, "currency": cat.MOEDA, "value": 0})
            fez_lead = True
        if alcance >= 75 and s.chance(0.65 * fs):
            s.emitir("scroll", {"percent_scrolled": 90})
            alcance = 90
        if alcance >= 75 and s.chance(0.10):
            termo, resultados = rng.choice(cat.BUSCAS_FAQ)
            s.emitir("site_search", {"search_term": termo, "search_results": resultados, "search_area": "faq"})
        if s.chance(0.05):
            texto, url = rng.choice(cat.SAIDAS)
            s.emitir("click", {"link_url": url, "link_domain": urlparse(url).hostname,
                               "link_text": texto, "outbound": True})
    return ResultadoSessao(s.eventos, compra, fez_lead)


def sessao_membros(rng: random.Random, ctx: Contexto, inicio: datetime, evento: str,
                   novo_user_id: str | None = None) -> list[dict]:
    """Área de membros. No sign_up, o user_id só passa a valer depois do page_view."""
    s = Sessao(rng, ctx, inicio)
    s.abrir("membros")
    if novo_user_id is not None:
        ctx.user_id = novo_user_id
    s.emitir(evento, {"method": "email"})
    return s.eventos


def sessao_reembolso(rng: random.Random, ctx: Contexto, inicio: datetime, compra: dict) -> list[dict]:
    s = Sessao(rng, ctx, inicio)
    s.abrir("obrigado")
    p = compra["params"]
    s.emitir("refund", {
        "transaction_id": p["transaction_id"], "value": p["value"], "tax": p["tax"],
        "shipping": p["shipping"], "currency": p["currency"], "reason": "garantia_7_dias",
    }, compra["items"])
    return s.eventos


def _sortear(rng: random.Random, opcoes: tuple[dict, ...]) -> dict:
    return rng.choices(opcoes, weights=[o["peso"] for o in opcoes])[0]


def _inicio(rng: random.Random, data_inicial: datetime, dia: int) -> datetime:
    hora = rng.choices(range(24), weights=cat.PESOS_HORA)[0]
    return data_inicial + timedelta(days=dia, hours=hora, seconds=rng.uniform(0, 3599))


def simular_visitante(rng: random.Random, data_inicial: datetime, dias: int) -> tuple[list[dict], int]:
    """Devolve (eventos do visitante, número de sessões simuladas)."""
    pseudo = "anon-" + hex8(rng)
    dispositivo = _sortear(rng, cat.DISPOSITIVOS)
    canal = _sortear(rng, cat.CANAIS)
    n = rng.choices((1, 2, 3, 4), weights=(65, 25, 7, 3))[0]
    dias_sessao = sorted(rng.sample(range(dias), k=min(n, dias)))
    fim = data_inicial + timedelta(days=dias)

    eventos: list[dict] = []
    sessoes = 0
    user_id = None
    e_lead = False
    compra = None
    for k, dia in enumerate(dias_sessao):
        if k > 0:
            canal = cat.NEWSLETTER if e_lead and rng.random() < 0.6 else _sortear(rng, cat.CANAIS)
        ctx = Contexto(pseudo, canal, dispositivo, "s-" + hex8(rng), user_id)
        inicio = _inicio(rng, data_inicial, dia)
        sessoes += 1

        if compra is not None:
            if user_id:
                eventos += sessao_membros(rng, ctx, inicio, "login")
            else:
                eventos += sessao_membros(rng, ctx, inicio, "sign_up", novo_user_id="u-" + hex8(rng))
            user_id = ctx.user_id
            continue

        resultado = simular_sessao(rng, ctx, inicio, intencao=1.6 if e_lead else 1.0, ja_e_lead=e_lead)
        eventos += resultado.eventos
        user_id = ctx.user_id
        e_lead = e_lead or resultado.fez_lead
        if resultado.compra is not None:
            compra = resultado.compra
            if rng.random() < P_REEMBOLSO * canal["fator_reembolso"]:
                quando = ler_iso(compra["event_ts"]) + timedelta(days=rng.uniform(1, 6.9))
                if quando < fim:
                    ctx_r = Contexto(pseudo, canal, dispositivo, "s-" + hex8(rng), user_id)
                    eventos += sessao_reembolso(rng, ctx_r, quando, compra)
                    sessoes += 1
    return eventos, sessoes


def simular(seed: int, dias: int, visitantes: int, data_inicial: datetime
            ) -> tuple[list[dict], int, random.Random]:
    """Simula todos os visitantes. Devolve (eventos, sessões, rng) — o rng segue para a sujeira e os lotes."""
    rng = random.Random(seed)
    eventos: list[dict] = []
    sessoes = 0
    for _ in range(visitantes):
        evs, n = simular_visitante(rng, data_inicial, dias)
        eventos += evs
        sessoes += n
    return eventos, sessoes, rng
