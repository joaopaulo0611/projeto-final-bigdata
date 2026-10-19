"""Qual elemento da página foi clicado: o `params.element_id` dos eventos de clique.

O valor é o atributo `data-heat` do elemento em site/index.html. O passo é
determinístico (não usa o rng), então ligar a marcação não muda nenhum outro
campo nem os números do gerador.
"""

from __future__ import annotations

from gerador import catalogo as cat

SOCIAL = {
    "instagram.com": "social-instagram",
    "youtube.com": "social-youtube",
    "wa.me": "social-whatsapp",
    "linkedin.com": "social-linkedin",
}
PLANOS = {"PLANO-BASICO": "plano-basico", "PLANO-PRO": "plano-pro", "PLANO-PREMIUM": "plano-premium"}
CTAS = ("hero_ver_planos", "hero_assistir", "logo")
FIXOS = {
    "video_start": "btn-play",
    "file_download": "dl-ementa",
    "generate_lead": "form-lead",
    "site_search": "faq-busca",
    "begin_checkout": "btn-continuar",
    "purchase": "btn-comprar",
    "refund": "btn-refund",
    "login": "btn-login",
    "sign_up": "btn-signup",
}


def _cta(link_id: str) -> str:
    return "cta-" + link_id.replace("_", "-")


ELEMENTOS = frozenset(
    set(SOCIAL.values()) | set(PLANOS.values()) | {_cta(c) for c in CTAS} | set(FIXOS.values())
    | {"modal-comprar", "bump", "frete-pac", "frete-sedex"}
    | {"pagto-" + p.replace("_", "-") for p in cat.PAGAMENTOS}
)


def _item(evento: dict | None) -> str | None:
    itens = (evento or {}).get("items") or []
    return itens[0].get("item_id") if itens else None


def _plano_no_carrinho(evento: dict, anterior: dict | None, seguinte: dict | None) -> str | None:
    """Botão de compra de um plano, como no site.

    - add_to_cart logo depois de view_item: o detalhe estava aberto → botão do modal;
    - add_to_cart sem detalhe: botão "Quero este plano" do próprio cartão;
    - troca de plano (remove_from_cart seguido de add_to_cart): os dois vêm do cartão do plano novo.
    """
    nome = evento["event_name"]
    if nome == "add_to_cart" and (anterior or {}).get("event_name") == "view_item":
        return "modal-comprar"
    alvo = _item(evento)
    if nome == "remove_from_cart" and (seguinte or {}).get("event_name") == "add_to_cart":
        alvo = _item(seguinte) or alvo
    return PLANOS.get(alvo)          # plano desconhecido: sem element_id


def elemento(evento: dict, anterior: dict | None = None, seguinte: dict | None = None) -> str | None:
    """`anterior`/`seguinte`: eventos vizinhos do mesmo visitante (só importam para o carrinho)."""
    nome = evento["event_name"]
    params = evento.get("params") or {}
    itens = evento.get("items") or []
    if nome == "click":
        if params.get("outbound"):
            return SOCIAL.get(params.get("link_domain") or "")
        return _cta(params["link_id"]) if params.get("link_id") else None
    if nome == "select_item":
        return PLANOS.get(itens[0]["item_id"]) if itens else None
    if nome in ("add_to_cart", "remove_from_cart"):
        if itens and itens[0]["item_id"] == cat.BUMP["item_id"]:
            return "bump"
        return _plano_no_carrinho(evento, anterior, seguinte)
    if nome == "add_shipping_info" and params.get("shipping_tier"):
        return "frete-" + str(params["shipping_tier"]).lower()
    if nome == "add_payment_info" and params.get("payment_type"):
        return "pagto-" + str(params["payment_type"]).replace("_", "-")
    return FIXOS.get(nome)


def marcar_elementos(eventos: list[dict]) -> int:
    """Põe params.element_id nos eventos de clique, no lugar. Devolve quantos marcou.

    As sessões do gerador ficam contíguas na lista, então o vizinho de um evento
    é o evento anterior/seguinte do mesmo user_pseudo_id."""
    anterior: list[dict | None] = [None] * len(eventos)
    seguinte: list[dict | None] = [None] * len(eventos)
    ultimo: dict[str, int] = {}
    for i, e in enumerate(eventos):
        j = ultimo.get(e.get("user_pseudo_id"))
        if j is not None:
            anterior[i], seguinte[j] = eventos[j], e
        ultimo[e.get("user_pseudo_id")] = i
    marcados = 0
    for i, e in enumerate(eventos):
        valor = elemento(e, anterior[i], seguinte[i])
        if valor is not None:
            e.setdefault("params", {})["element_id"] = valor
            marcados += 1
    return marcados
