"""Catálogo da landing hipotética DadosPro.

Tudo o que é regra de negócio do gerador mora aqui: eventos, produtos,
preços, canais, dispositivos e textos da página. jornadas.py só descreve
o comportamento do visitante.

Os "20 eventos" do enunciado são 22 nomes, porque o engajamento de mídia
conta como um item só e tem três nomes (start, progress, complete).
"""

from __future__ import annotations

EVENTOS = (
    "page_view", "scroll", "click", "site_search",
    "video_start", "video_progress", "video_complete", "file_download",
    "view_item_list", "select_item", "view_item", "add_to_cart", "remove_from_cart",
    "view_cart", "begin_checkout", "add_shipping_info", "add_payment_info",
    "purchase", "refund",
    "generate_lead", "sign_up", "login",
)

PLANOS = (
    {"item_id": "PLANO-BASICO", "item_name": "Plano Básico", "item_category": "plano", "price": 297.0},
    {"item_id": "PLANO-PRO", "item_name": "Plano Pro", "item_category": "plano", "price": 597.0},
    {"item_id": "PLANO-PREMIUM", "item_name": "Plano Premium", "item_category": "plano", "price": 997.0},
)
PESOS_PLANO = (0.35, 0.45, 0.20)
PREMIUM = "PLANO-PREMIUM"
BUMP = {"item_id": "BUMP-MENTORIA", "item_name": "Mentoria em grupo", "item_category": "order_bump", "price": 147.0}

FRETE = {"PAC": 24.90, "SEDEX": 49.90}
PESOS_FRETE = (0.6, 0.4)
ALIQUOTA_ISS = 0.05
DESCONTO_PIX = 0.05
MOEDA = "BRL"
PAGAMENTOS = ("pix", "cartao_avista", "cartao_parcelado")
PESOS_PAGAMENTO = (0.40, 0.20, 0.40)

LISTA = {"item_list_id": "tabela_planos", "item_list_name": "Tabela de planos"}

# peso: participação no tráfego; fator_compra: multiplica a propensão de compra;
# fator_reembolso: multiplica a chance de pedir reembolso
CANAIS = (
    {"source": "direct", "medium": "(none)", "campaign": None,
     "referrer": None, "peso": 0.20, "fator_compra": 1.0, "fator_reembolso": 0.8},
    {"source": "google", "medium": "cpc", "campaign": "formacao_dados",
     "referrer": "https://www.google.com/", "peso": 0.30, "fator_compra": 1.2, "fator_reembolso": 1.0},
    {"source": "google", "medium": "organic", "campaign": None,
     "referrer": "https://www.google.com/", "peso": 0.20, "fator_compra": 1.0, "fator_reembolso": 0.7},
    {"source": "instagram", "medium": "paid_social", "campaign": "lancamento_nov",
     "referrer": "https://l.instagram.com/", "peso": 0.25, "fator_compra": 0.6, "fator_reembolso": 2.5},
    {"source": "newsletter", "medium": "email", "campaign": "ebook_nutricao",
     "referrer": None, "peso": 0.05, "fator_compra": 1.5, "fator_reembolso": 0.5},
)
NEWSLETTER = CANAIS[4]

DISPOSITIVOS = (
    {"category": "mobile", "os": "Android", "browser": "Chrome", "peso": 0.38, "fator_compra": 0.8, "fator_scroll": 1.1},
    {"category": "mobile", "os": "iOS", "browser": "Safari", "peso": 0.22, "fator_compra": 0.9, "fator_scroll": 1.1},
    {"category": "desktop", "os": "Windows", "browser": "Chrome", "peso": 0.25, "fator_compra": 1.15, "fator_scroll": 0.95},
    {"category": "desktop", "os": "macOS", "browser": "Safari", "peso": 0.10, "fator_compra": 1.2, "fator_scroll": 0.95},
    {"category": "tablet", "os": "iOS", "browser": "Safari", "peso": 0.05, "fator_compra": 1.0, "fator_scroll": 1.0},
)

VIDEO = {"video_title": "VSL Formação em Análise de Dados", "video_provider": "self_hosted", "video_duration": 240}
RETENCAO_VIDEO = ((10, 0.90), (25, 0.80), (50, 0.70), (75, 0.75))   # chance de passar do marco anterior a este
P_VIDEO_COMPLETO = 0.80

# termo -> quantidade de respostas no FAQ (0 = lacuna de conteúdo)
BUSCAS_FAQ = (
    ("certificado", 1), ("parcelar", 1), ("reembolso", 1), ("apostila", 1), ("acesso", 1),
    ("linux", 0), ("presencial", 0), ("bolsa", 0), ("estagio", 0), ("power bi", 0),
)
SAIDAS = (
    ("Instagram", "https://instagram.com/dadospro"),
    ("YouTube", "https://youtube.com/@dadospro"),
    ("WhatsApp", "https://wa.me/5548999999999"),
    ("LinkedIn", "https://linkedin.com/company/dadospro"),
)
EMENTA = {
    "file_name": "ementa-formacao-dados.pdf",
    "file_extension": "pdf",
    "link_url": "https://loja.exemplo/arquivos/ementa-formacao-dados.pdf",
}
LEAD_SOURCE = "ebook_primeiro_pipeline"

BASE_URL = "https://loja.exemplo"
PAGINAS = {
    "landing": BASE_URL + "/",
    "checkout": BASE_URL + "/checkout",
    "obrigado": BASE_URL + "/obrigado",
    "membros": BASE_URL + "/membros",
}
TITULO = "Formação em Análise de Dados"

# peso de cada hora do dia (UTC) no início de uma sessão
PESOS_HORA = (1, 1, 1, 1, 1, 1, 2, 3, 5, 6, 6, 6, 6, 6, 6, 6, 6, 6, 7, 8, 9, 9, 7, 4)
